"""生产级FastAPI应用程序"""
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any, List

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel

from src.services.mcp_service import MCPService, QueryRequest, QueryResponse
from src.api.rag_endpoints import rag_router
from src.config.settings import settings
from src.utils.logging import setup_logging, get_structured_logger

# 设置日志
setup_logging()
logger = get_structured_logger(__name__)

# Prometheus指标
REQUEST_COUNT = Counter('mcp_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('mcp_request_duration_seconds', 'Request duration')
ACTIVE_CONNECTIONS = Gauge('mcp_active_connections', 'Active MCP connections')
ERROR_COUNT = Counter('mcp_errors_total', 'Total errors', ['error_type'])

# 限流器
limiter = Limiter(key_func=get_remote_address)

# 全局服务实例
mcp_service: MCPService = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用程序生命周期管理"""
    global mcp_service
    
    logger.info("启动MCP生产服务")
    
    # 初始化服务
    mcp_service = MCPService()
    await mcp_service.initialize()
    
    logger.info("MCP生产服务启动完成")
    
    yield
    
    # 关闭服务
    logger.info("关闭MCP生产服务")
    if mcp_service:
        await mcp_service.shutdown()
    logger.info("MCP生产服务关闭完成")


# 创建FastAPI应用
app = FastAPI(
    title="MCP Production Client",
    description="生产级MCP多服务器客户端",
    version="0.2.0",
    lifespan=lifespan
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境中应该限制特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加限流
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 包含RAG路由
app.include_router(rag_router)


# Pydantic模型
class QueryRequestModel(BaseModel):
    query: str
    user_id: str = None
    session_id: str = None
    max_tokens: int = None
    timeout: int = None


class QueryResponseModel(BaseModel):
    content: str
    tools_used: List[Dict[str, Any]]
    execution_time: float
    request_id: str
    status: str = "success"
    error: str = None


# 依赖项
async def get_mcp_service() -> MCPService:
    """获取MCP服务实例"""
    if not mcp_service:
        raise HTTPException(status_code=503, detail="服务未初始化")
    return mcp_service


# 中间件
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """指标收集中间件"""
    start_time = asyncio.get_event_loop().time()
    
    try:
        response = await call_next(request)
        
        # 记录指标
        duration = asyncio.get_event_loop().time() - start_time
        REQUEST_DURATION.observe(duration)
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code
        ).inc()
        
        return response
        
    except Exception as e:
        # 记录错误指标
        ERROR_COUNT.labels(error_type=type(e).__name__).inc()
        raise


# API路由
@app.post("/query", response_model=QueryResponseModel)
@limiter.limit(f"{settings.api.rate_limit_per_minute}/minute")
async def process_query(
    request: Request,
    query_request: QueryRequestModel,
    service: MCPService = Depends(get_mcp_service)
):
    """处理查询请求"""
    try:
        logger.info(
            "接收查询请求",
            user_id=query_request.user_id,
            session_id=query_request.session_id,
            query_length=len(query_request.query)
        )
        
        # 转换请求
        mcp_request = QueryRequest(
            query=query_request.query,
            user_id=query_request.user_id,
            session_id=query_request.session_id,
            max_tokens=query_request.max_tokens,
            timeout=query_request.timeout
        )
        
        # 处理查询
        response = await service.process_query(mcp_request)
        
        return QueryResponseModel(**response.__dict__)
        
    except Exception as e:
        logger.error("查询处理失败", error=str(e))
        ERROR_COUNT.labels(error_type=type(e).__name__).inc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tools")
async def get_available_tools(service: MCPService = Depends(get_mcp_service)):
    """获取可用工具列表"""
    try:
        tools = await service.get_available_tools()
        return {"tools": tools, "count": len(tools)}
    except Exception as e:
        logger.error("获取工具列表失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status")
async def get_server_status(service: MCPService = Depends(get_mcp_service)):
    """获取服务器状态"""
    try:
        status = await service.get_server_status()
        return status
    except Exception as e:
        logger.error("获取服务器状态失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check(service: MCPService = Depends(get_mcp_service)):
    """健康检查端点"""
    try:
        health = await service.health_check()
        
        # 更新连接数指标
        if 'connection_pool' in health:
            ACTIVE_CONNECTIONS.set(health['connection_pool'].get('active_connections', 0))
        
        if health.get('status') == 'healthy':
            return health
        else:
            raise HTTPException(status_code=503, detail=health)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("健康检查失败", error=str(e))
        raise HTTPException(status_code=503, detail={"status": "unhealthy", "error": str(e)})


@app.get("/metrics")
async def get_metrics():
    """Prometheus指标端点"""
    return generate_latest()


@app.get("/")
async def root():
    """根端点"""
    return {
        "name": "MCP Production Client",
        "version": "0.2.0",
        "description": "生产级MCP多服务器客户端",
        "endpoints": {
            "query": "/query",
            "tools": "/tools", 
            "status": "/status",
            "health": "/health",
            "metrics": "/metrics",
            "rag": "/rag"
        }
    }


# 异常处理器
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    logger.error(
        "未处理的异常",
        path=request.url.path,
        method=request.method,
        error=str(exc)
    )
    ERROR_COUNT.labels(error_type=type(exc).__name__).inc()
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "内部服务器错误",
            "error": str(exc),
            "path": request.url.path
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    logger.info(
        "启动API服务器",
        host=settings.api.host,
        port=settings.api.port,
        workers=settings.api.workers
    )
    
    uvicorn.run(
        "src.api.main:app",
        host=settings.api.host,
        port=settings.api.port,
        workers=settings.api.workers,
        log_level=settings.logging.level.lower(),
        reload=settings.debug
    )