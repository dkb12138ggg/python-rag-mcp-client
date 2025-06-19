"""错误处理和重试机制"""
import asyncio
import traceback
from typing import Any, Dict, Optional, Union, Callable, Type
from enum import Enum
from dataclasses import dataclass
from functools import wraps

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    retry_if_result,
    RetryError
)
from circuitbreaker import circuit, CircuitBreakerError

from src.utils.logging import get_structured_logger
from src.utils.metrics import metrics

logger = get_structured_logger(__name__)


class ErrorType(Enum):
    """错误类型枚举"""
    CONNECTION_ERROR = "connection_error"
    TIMEOUT_ERROR = "timeout_error"
    AUTHENTICATION_ERROR = "authentication_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    VALIDATION_ERROR = "validation_error"
    TOOL_EXECUTION_ERROR = "tool_execution_error"
    OPENAI_API_ERROR = "openai_api_error"
    INTERNAL_ERROR = "internal_error"
    CIRCUIT_BREAKER_ERROR = "circuit_breaker_error"


@dataclass
class ErrorInfo:
    """错误信息"""
    error_type: ErrorType
    message: str
    details: Optional[Dict[str, Any]] = None
    traceback: Optional[str] = None
    component: str = "unknown"
    recoverable: bool = True


class MCPException(Exception):
    """MCP自定义异常基类"""
    
    def __init__(self, error_info: ErrorInfo):
        self.error_info = error_info
        super().__init__(error_info.message)


class ConnectionException(MCPException):
    """连接异常"""
    pass


class TimeoutException(MCPException):
    """超时异常"""
    pass


class AuthenticationException(MCPException):
    """认证异常"""
    pass


class RateLimitException(MCPException):
    """限流异常"""
    pass


class ValidationException(MCPException):
    """验证异常"""
    pass


class ToolExecutionException(MCPException):
    """工具执行异常"""
    pass


class OpenAIAPIException(MCPException):
    """OpenAI API异常"""
    pass


def is_retriable_error(exception: Exception) -> bool:
    """判断异常是否可重试"""
    if isinstance(exception, MCPException):
        return exception.error_info.recoverable
    
    # 特定异常类型的重试逻辑
    retriable_types = (
        ConnectionError,
        TimeoutError,
        asyncio.TimeoutError,
        ConnectionException,
        TimeoutException,
    )
    
    return isinstance(exception, retriable_types)


def create_retry_decorator(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
    component: str = "unknown"
):
    """创建重试装饰器"""
    
    def decorator(func: Callable):
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
            retry=retry_if_exception_type((
                ConnectionError,
                TimeoutError,
                asyncio.TimeoutError,
                ConnectionException,
                TimeoutException,
            )),
            reraise=True
        )
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except RetryError as e:
                # 记录重试失败
                original_error = e.last_attempt.exception()
                logger.error(
                    "重试失败",
                    component=component,
                    function=func.__name__,
                    attempts=max_attempts,
                    error=str(original_error)
                )
                metrics.record_error("retry_failed", component)
                raise original_error
            except Exception as e:
                logger.error(
                    "函数执行失败",
                    component=component,
                    function=func.__name__,
                    error=str(e)
                )
                metrics.record_error(type(e).__name__, component)
                raise
        
        return wrapper
    return decorator


def create_circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: int = 30,
    expected_exception: Type[Exception] = Exception,
    component: str = "unknown"
):
    """创建断路器装饰器"""
    
    def decorator(func: Callable):
        @circuit(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            expected_exception=expected_exception
        )
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except CircuitBreakerError as e:
                logger.warning(
                    "断路器打开",
                    component=component,
                    function=func.__name__,
                    reason=str(e)
                )
                metrics.record_error("circuit_breaker_open", component)
                raise MCPException(ErrorInfo(
                    error_type=ErrorType.CIRCUIT_BREAKER_ERROR,
                    message=f"服务暂时不可用: {str(e)}",
                    component=component,
                    recoverable=False
                ))
            except Exception as e:
                logger.error(
                    "断路器包装函数失败",
                    component=component,
                    function=func.__name__,
                    error=str(e)
                )
                raise
        
        return wrapper
    return decorator


async def handle_error(
    error: Exception,
    component: str,
    context: Optional[Dict[str, Any]] = None,
    user_friendly: bool = True
) -> ErrorInfo:
    """统一错误处理"""
    
    # 获取错误追踪信息
    error_traceback = traceback.format_exc()
    
    # 分类错误
    if isinstance(error, MCPException):
        error_info = error.error_info
    elif isinstance(error, (ConnectionError, ConnectionException)):
        error_info = ErrorInfo(
            error_type=ErrorType.CONNECTION_ERROR,
            message="连接服务器失败，请稍后重试",
            component=component,
            recoverable=True
        )
    elif isinstance(error, (TimeoutError, asyncio.TimeoutError, TimeoutException)):
        error_info = ErrorInfo(
            error_type=ErrorType.TIMEOUT_ERROR,
            message="请求超时，请稍后重试",
            component=component,
            recoverable=True
        )
    elif isinstance(error, (AuthenticationException,)):
        error_info = ErrorInfo(
            error_type=ErrorType.AUTHENTICATION_ERROR,
            message="认证失败，请检查API密钥",
            component=component,
            recoverable=False
        )
    elif isinstance(error, (RateLimitException,)):
        error_info = ErrorInfo(
            error_type=ErrorType.RATE_LIMIT_ERROR,
            message="请求频率过高，请稍后重试",
            component=component,
            recoverable=True
        )
    elif isinstance(error, (ValidationException,)):
        error_info = ErrorInfo(
            error_type=ErrorType.VALIDATION_ERROR,
            message="请求参数无效",
            component=component,
            recoverable=False
        )
    else:
        error_info = ErrorInfo(
            error_type=ErrorType.INTERNAL_ERROR,
            message="内部服务器错误" if user_friendly else str(error),
            component=component,
            recoverable=False
        )
    
    # 添加详细信息
    error_info.details = context or {}
    error_info.traceback = error_traceback
    
    # 记录错误
    logger.error(
        "处理错误",
        error_type=error_info.error_type.value,
        component=component,
        message=error_info.message,
        recoverable=error_info.recoverable,
        context=context
    )
    
    # 记录指标
    metrics.record_error(error_info.error_type.value, component)
    
    return error_info


class ErrorHandler:
    """错误处理器"""
    
    def __init__(self, component: str):
        self.component = component
    
    async def handle_connection_error(self, error: Exception, server_name: str) -> ErrorInfo:
        """处理连接错误"""
        context = {"server_name": server_name}
        return await handle_error(error, self.component, context)
    
    async def handle_tool_execution_error(
        self,
        error: Exception,
        tool_name: str,
        server_name: str,
        arguments: Dict[str, Any]
    ) -> ErrorInfo:
        """处理工具执行错误"""
        context = {
            "tool_name": tool_name,
            "server_name": server_name,
            "arguments": arguments
        }
        return await handle_error(error, self.component, context)
    
    async def handle_openai_error(self, error: Exception, model: str) -> ErrorInfo:
        """处理OpenAI API错误"""
        context = {"model": model}
        
        # 特殊处理OpenAI错误
        error_message = str(error)
        if "rate limit" in error_message.lower():
            error_info = ErrorInfo(
                error_type=ErrorType.RATE_LIMIT_ERROR,
                message="OpenAI API请求频率限制",
                component=self.component,
                recoverable=True,
                details=context
            )
        elif "authentication" in error_message.lower() or "unauthorized" in error_message.lower():
            error_info = ErrorInfo(
                error_type=ErrorType.AUTHENTICATION_ERROR,
                message="OpenAI API认证失败",
                component=self.component,
                recoverable=False,
                details=context
            )
        else:
            error_info = ErrorInfo(
                error_type=ErrorType.OPENAI_API_ERROR,
                message=f"OpenAI API错误: {error_message}",
                component=self.component,
                recoverable=True,
                details=context
            )
        
        # 记录错误
        logger.error(
            "OpenAI API错误",
            error_type=error_info.error_type.value,
            model=model,
            message=error_message
        )
        
        metrics.record_error(error_info.error_type.value, self.component)
        
        return error_info


# 常用装饰器
connection_retry = create_retry_decorator(max_attempts=3, component="connection")
tool_execution_retry = create_retry_decorator(max_attempts=2, component="tool_execution")
openai_retry = create_retry_decorator(max_attempts=3, component="openai")

connection_circuit_breaker = create_circuit_breaker(
    failure_threshold=5,
    recovery_timeout=30,
    component="connection"
)

tool_circuit_breaker = create_circuit_breaker(
    failure_threshold=3,
    recovery_timeout=60,
    component="tool_execution"
)