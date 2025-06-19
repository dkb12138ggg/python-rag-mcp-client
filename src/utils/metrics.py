"""指标收集和监控"""
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from contextlib import contextmanager
from prometheus_client import Counter, Histogram, Gauge, Info

from src.utils.logging import get_structured_logger

logger = get_structured_logger(__name__)


@dataclass
class MetricsCollector:
    """指标收集器"""
    
    # 请求指标
    requests_total: Counter = field(
        default_factory=lambda: Counter(
            'mcp_requests_total',
            'Total number of requests',
            ['method', 'endpoint', 'status', 'user_id']
        )
    )
    
    request_duration: Histogram = field(
        default_factory=lambda: Histogram(
            'mcp_request_duration_seconds',
            'Request duration in seconds',
            ['method', 'endpoint']
        )
    )
    
    # 连接池指标
    connection_pool_size: Gauge = field(
        default_factory=lambda: Gauge(
            'mcp_connection_pool_size',
            'Current connection pool size',
            ['server_name']
        )
    )
    
    active_connections: Gauge = field(
        default_factory=lambda: Gauge(
            'mcp_active_connections',
            'Number of active connections',
            ['server_name']
        )
    )
    
    connection_errors: Counter = field(
        default_factory=lambda: Counter(
            'mcp_connection_errors_total',
            'Total connection errors',
            ['server_name', 'error_type']
        )
    )
    
    # 工具调用指标
    tool_calls_total: Counter = field(
        default_factory=lambda: Counter(
            'mcp_tool_calls_total',
            'Total tool calls',
            ['server_name', 'tool_name', 'status']
        )
    )
    
    tool_call_duration: Histogram = field(
        default_factory=lambda: Histogram(
            'mcp_tool_call_duration_seconds',
            'Tool call duration in seconds',
            ['server_name', 'tool_name']
        )
    )
    
    # OpenAI指标
    openai_requests: Counter = field(
        default_factory=lambda: Counter(
            'mcp_openai_requests_total',
            'Total OpenAI API requests',
            ['model', 'status']
        )
    )
    
    openai_tokens: Counter = field(
        default_factory=lambda: Counter(
            'mcp_openai_tokens_total',
            'Total OpenAI tokens used',
            ['model', 'type']  # prompt_tokens, completion_tokens
        )
    )
    
    # 错误指标
    errors_total: Counter = field(
        default_factory=lambda: Counter(
            'mcp_errors_total',
            'Total errors',
            ['error_type', 'component']
        )
    )
    
    # 系统指标
    concurrent_requests: Gauge = field(
        default_factory=lambda: Gauge(
            'mcp_concurrent_requests',
            'Current number of concurrent requests'
        )
    )
    
    # 应用信息
    app_info: Info = field(
        default_factory=lambda: Info(
            'mcp_app_info',
            'Application information'
        )
    )
    
    def __post_init__(self):
        """初始化后设置应用信息"""
        self.app_info.info({
            'version': '0.2.0',
            'name': 'MCP Production Client',
            'description': 'Production-ready MCP multi-server client'
        })
    
    @contextmanager
    def time_request(self, method: str, endpoint: str):
        """计时请求执行时间"""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.request_duration.labels(method=method, endpoint=endpoint).observe(duration)
    
    @contextmanager
    def time_tool_call(self, server_name: str, tool_name: str):
        """计时工具调用执行时间"""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.tool_call_duration.labels(
                server_name=server_name,
                tool_name=tool_name
            ).observe(duration)
    
    def record_request(self, method: str, endpoint: str, status: str, user_id: str = None):
        """记录请求"""
        self.requests_total.labels(
            method=method,
            endpoint=endpoint,
            status=status,
            user_id=user_id or 'anonymous'
        ).inc()
    
    def record_tool_call(self, server_name: str, tool_name: str, status: str):
        """记录工具调用"""
        self.tool_calls_total.labels(
            server_name=server_name,
            tool_name=tool_name,
            status=status
        ).inc()
    
    def record_connection_error(self, server_name: str, error_type: str):
        """记录连接错误"""
        self.connection_errors.labels(
            server_name=server_name,
            error_type=error_type
        ).inc()
    
    def record_openai_request(self, model: str, status: str, prompt_tokens: int = 0, completion_tokens: int = 0):
        """记录OpenAI请求"""
        self.openai_requests.labels(model=model, status=status).inc()
        
        if prompt_tokens > 0:
            self.openai_tokens.labels(model=model, type='prompt').inc(prompt_tokens)
        if completion_tokens > 0:
            self.openai_tokens.labels(model=model, type='completion').inc(completion_tokens)
    
    def record_error(self, error_type: str, component: str):
        """记录错误"""
        self.errors_total.labels(error_type=error_type, component=component).inc()
    
    def update_connection_pool_metrics(self, server_name: str, pool_size: int, active_count: int):
        """更新连接池指标"""
        self.connection_pool_size.labels(server_name=server_name).set(pool_size)
        self.active_connections.labels(server_name=server_name).set(active_count)
    
    def set_concurrent_requests(self, count: int):
        """设置并发请求数"""
        self.concurrent_requests.set(count)


# 全局指标收集器实例
metrics = MetricsCollector()


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self):
        self.stats = {
            'requests_per_second': 0.0,
            'avg_response_time': 0.0,
            'error_rate': 0.0,
            'connection_pool_utilization': 0.0
        }
        self._request_times = []
        self._request_count = 0
        self._error_count = 0
        self._last_reset = time.time()
    
    def record_request(self, duration: float, error: bool = False):
        """记录请求性能数据"""
        self._request_times.append(duration)
        self._request_count += 1
        if error:
            self._error_count += 1
        
        # 保持最近100个请求的数据
        if len(self._request_times) > 100:
            self._request_times.pop(0)
        
        self._update_stats()
    
    def _update_stats(self):
        """更新统计数据"""
        now = time.time()
        time_window = now - self._last_reset
        
        if time_window > 0:
            self.stats['requests_per_second'] = self._request_count / time_window
        
        if self._request_times:
            self.stats['avg_response_time'] = sum(self._request_times) / len(self._request_times)
        
        if self._request_count > 0:
            self.stats['error_rate'] = self._error_count / self._request_count
        
        # 每60秒重置一次计数器
        if time_window > 60:
            self.reset()
    
    def reset(self):
        """重置统计数据"""
        self._request_count = 0
        self._error_count = 0
        self._last_reset = time.time()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        return self.stats.copy()


# 全局性能监控器实例
performance_monitor = PerformanceMonitor()