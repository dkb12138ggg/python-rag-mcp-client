"""MCP生产客户端包"""

__version__ = "0.2.0"
__description__ = "Production-ready MCP multi-server client with connection pooling and async processing"

from src.services.mcp_service import MCPService
from src.core.connection_pool import MCPConnectionPool
from src.config.settings import settings

__all__ = [
    "MCPService",
    "MCPConnectionPool", 
    "settings"
]