"""MCP服务器连接池管理"""
import asyncio
import json
import time
from contextlib import AsyncExitStack
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from tenacity import retry, stop_after_attempt, wait_exponential
from circuitbreaker import circuit

from src.config.settings import settings
from src.utils.logging import get_structured_logger

logger = get_structured_logger(__name__)


class ConnectionStatus(Enum):
    """连接状态枚举"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"
    CIRCUIT_OPEN = "circuit_open"


@dataclass
class ServerConfig:
    """服务器配置"""
    name: str
    type: str  # 'sse' or 'stdio'
    url: Optional[str] = None
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Optional[Dict[str, str]] = None


@dataclass
class ConnectionInfo:
    """连接信息"""
    session: ClientSession
    session_context: Any
    stream_context: Any
    status: ConnectionStatus = ConnectionStatus.CONNECTED
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    error_count: int = 0
    tools_cache: Optional[List[Dict[str, Any]]] = None


class MCPConnectionPool:
    """MCP服务器连接池"""
    
    def __init__(self):
        self.pools: Dict[str, List[ConnectionInfo]] = {}
        self.server_configs: Dict[str, ServerConfig] = {}
        self._lock = asyncio.Lock()
        self._health_check_task: Optional[asyncio.Task] = None
        self._metrics = {
            'total_connections': 0,
            'active_connections': 0,
            'failed_connections': 0,
            'requests_served': 0,
            'connection_errors': 0,
        }
    
    async def initialize(self) -> None:
        """初始化连接池"""
        logger.info("初始化MCP连接池")
        
        # 加载服务器配置
        await self._load_server_configs()
        
        # 创建初始连接
        await self._create_initial_connections()
        
        # 启动健康检查
        if settings.mcp.health_check_interval > 0:
            self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        logger.info(
            "连接池初始化完成",
            servers=len(self.server_configs),
            total_connections=self._metrics['total_connections']
        )
    
    async def _load_server_configs(self) -> None:
        """加载服务器配置"""
        try:
            with open(settings.mcp.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 支持新的 mcpServers 对象格式
            if 'mcpServers' in config:
                for name, server_config in config['mcpServers'].items():
                    self.server_configs[name] = ServerConfig(
                        name=name,
                        type=server_config.get('type'),
                        url=server_config.get('url'),
                        command=server_config.get('command'),
                        args=server_config.get('args', []),
                        env=server_config.get('env')
                    )
            
            # 兼容旧的 servers 数组格式
            elif 'servers' in config:
                for server_config in config['servers']:
                    name = server_config.get('name')
                    if name:
                        self.server_configs[name] = ServerConfig(**server_config)
            
            logger.info("服务器配置加载完成", count=len(self.server_configs))
            
        except Exception as e:
            logger.error("加载服务器配置失败", error=str(e))
            raise
    
    async def _create_initial_connections(self) -> None:
        """为每个服务器创建初始连接"""
        tasks = []
        for server_name in self.server_configs:
            # 为每个服务器创建最小连接数
            for _ in range(min(2, settings.mcp.max_connections_per_server)):
                task = self._create_connection(server_name)
                tasks.append(task)
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error("创建初始连接失败", error=str(result))
    
    @retry(
        stop=stop_after_attempt(settings.mcp.max_reconnect_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    @circuit(failure_threshold=5, recovery_timeout=30, expected_exception=Exception)
    async def _create_connection(self, server_name: str) -> Optional[ConnectionInfo]:
        """创建单个连接"""
        server_config = self.server_configs.get(server_name)
        if not server_config:
            logger.error("服务器配置未找到", server=server_name)
            return None
        
        try:
            logger.debug("创建连接", server=server_name, type=server_config.type)
            
            if server_config.type == 'sse':
                return await self._create_sse_connection(server_config)
            elif server_config.type == 'stdio':
                return await self._create_stdio_connection(server_config)
            else:
                logger.error("不支持的服务器类型", server=server_name, type=server_config.type)
                return None
                
        except Exception as e:
            self._metrics['connection_errors'] += 1
            logger.error("创建连接失败", server=server_name, error=str(e))
            raise
    
    async def _create_sse_connection(self, config: ServerConfig) -> ConnectionInfo:
        """创建SSE连接"""
        stream_context = sse_client(url=config.url)
        streams = await stream_context.__aenter__()
        
        session_context = ClientSession(*streams)
        session = await session_context.__aenter__()
        
        await session.initialize()
        
        # 缓存工具列表
        tools_response = await session.list_tools()
        tools_cache = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema
                },
                "original_name": tool.name,
                "server_name": config.name
            }
            for tool in tools_response.tools
        ]
        
        connection = ConnectionInfo(
            session=session,
            session_context=session_context,
            stream_context=stream_context,
            tools_cache=tools_cache
        )
        
        self._metrics['total_connections'] += 1
        self._metrics['active_connections'] += 1
        
        logger.info(
            "SSE连接创建成功",
            server=config.name,
            url=config.url,
            tools_count=len(tools_cache)
        )
        
        return connection
    
    async def _create_stdio_connection(self, config: ServerConfig) -> ConnectionInfo:
        """创建stdio连接"""
        server_params = StdioServerParameters(
            command=config.command,
            args=config.args,
            env=config.env
        )
        
        stream_context = stdio_client(server_params)
        streams = await stream_context.__aenter__()
        
        session_context = ClientSession(*streams)
        session = await session_context.__aenter__()
        
        await session.initialize()
        
        # 缓存工具列表
        tools_response = await session.list_tools()
        tools_cache = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema
                },
                "original_name": tool.name,
                "server_name": config.name
            }
            for tool in tools_response.tools
        ]
        
        connection = ConnectionInfo(
            session=session,
            session_context=session_context,
            stream_context=stream_context,
            tools_cache=tools_cache
        )
        
        self._metrics['total_connections'] += 1
        self._metrics['active_connections'] += 1
        
        logger.info(
            "stdio连接创建成功",
            server=config.name,
            command=f"{config.command} {' '.join(config.args)}",
            tools_count=len(tools_cache)
        )
        
        return connection
    
    async def get_connection(self, server_name: str) -> Optional[ConnectionInfo]:
        """获取连接"""
        async with self._lock:
            # 从池中获取可用连接
            pool = self.pools.get(server_name, [])
            
            # 找到可用的连接
            for connection in pool:
                if connection.status == ConnectionStatus.CONNECTED:
                    connection.last_used = time.time()
                    return connection
            
            # 如果没有可用连接，创建新连接
            if len(pool) < settings.mcp.max_connections_per_server:
                connection = await self._create_connection(server_name)
                if connection:
                    if server_name not in self.pools:
                        self.pools[server_name] = []
                    self.pools[server_name].append(connection)
                    return connection
            
            logger.warning("无法获取连接", server=server_name)
            return None
    
    async def return_connection(self, server_name: str, connection: ConnectionInfo, 
                              error: Optional[Exception] = None) -> None:
        """归还连接"""
        if error:
            connection.error_count += 1
            connection.status = ConnectionStatus.FAILED
            logger.warning("连接出现错误", server=server_name, error=str(error))
        else:
            connection.status = ConnectionStatus.CONNECTED
    
    async def _health_check_loop(self) -> None:
        """健康检查循环"""
        while True:
            try:
                await asyncio.sleep(settings.mcp.health_check_interval)
                await self._perform_health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("健康检查失败", error=str(e))
    
    async def _perform_health_check(self) -> None:
        """执行健康检查"""
        async with self._lock:
            for server_name, pool in self.pools.items():
                healthy_connections = []
                
                for connection in pool:
                    try:
                        # 简单的健康检查：调用list_tools
                        await connection.session.list_tools()
                        connection.status = ConnectionStatus.CONNECTED
                        healthy_connections.append(connection)
                    except Exception as e:
                        logger.warning("连接健康检查失败", server=server_name, error=str(e))
                        connection.status = ConnectionStatus.FAILED
                        await self._cleanup_connection(connection)
                
                self.pools[server_name] = healthy_connections
        
        logger.debug("健康检查完成", active_connections=self._metrics['active_connections'])
    
    async def _cleanup_connection(self, connection: ConnectionInfo) -> None:
        """清理连接"""
        try:
            await connection.session_context.__aexit__(None, None, None)
            await connection.stream_context.__aexit__(None, None, None)
            self._metrics['active_connections'] -= 1
        except Exception as e:
            logger.error("清理连接失败", error=str(e))
    
    async def get_all_tools(self) -> List[Dict[str, Any]]:
        """获取所有工具"""
        all_tools = []
        
        for server_name in self.server_configs:
            connection = await self.get_connection(server_name)
            if connection and connection.tools_cache:
                all_tools.extend(connection.tools_cache)
        
        return all_tools
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取连接池指标"""
        return self._metrics.copy()
    
    async def shutdown(self) -> None:
        """关闭连接池"""
        logger.info("关闭连接池")
        
        # 停止健康检查
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # 清理所有连接
        async with self._lock:
            for server_name, pool in self.pools.items():
                for connection in pool:
                    await self._cleanup_connection(connection)
        
        logger.info("连接池关闭完成")