"""生产环境配置管理"""
import os
from typing import List, Dict, Any, Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class RedisSettings(BaseSettings):
    """Redis配置"""
    host: str = Field(default="localhost", env="REDIS_HOST")
    port: int = Field(default=6379, env="REDIS_PORT")
    db: int = Field(default=0, env="REDIS_DB")
    password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    max_connections: int = Field(default=20, env="REDIS_MAX_CONNECTIONS")


class OpenAISettings(BaseSettings):
    """OpenAI配置"""
    api_key: str = Field(env="OPENAI_API_KEY")
    base_url: str = Field(default="https://api.openai.com/v1", env="OPENAI_BASE_URL")
    model: str = Field(default="gpt-4", env="OPENAI_MODEL")
    max_tokens: int = Field(default=1000, env="OPENAI_MAX_TOKENS")
    timeout: int = Field(default=30, env="OPENAI_TIMEOUT")


class MCPConnectionSettings(BaseSettings):
    """MCP连接配置"""
    config_path: str = Field(default="mcp.json", env="MCP_SERVER_URL")
    max_connections_per_server: int = Field(default=5, env="MCP_MAX_CONNECTIONS_PER_SERVER")
    connection_timeout: int = Field(default=30, env="MCP_CONNECTION_TIMEOUT")
    reconnect_interval: int = Field(default=5, env="MCP_RECONNECT_INTERVAL")
    max_reconnect_attempts: int = Field(default=3, env="MCP_MAX_RECONNECT_ATTEMPTS")
    health_check_interval: int = Field(default=60, env="MCP_HEALTH_CHECK_INTERVAL")


class APISettings(BaseSettings):
    """API服务配置"""
    host: str = Field(default="0.0.0.0", env="API_HOST")
    port: int = Field(default=8000, env="API_PORT")
    workers: int = Field(default=1, env="API_WORKERS")
    max_concurrent_requests: int = Field(default=100, env="API_MAX_CONCURRENT_REQUESTS")
    request_timeout: int = Field(default=300, env="API_REQUEST_TIMEOUT")
    rate_limit_per_minute: int = Field(default=60, env="API_RATE_LIMIT_PER_MINUTE")


class LoggingSettings(BaseSettings):
    """日志配置"""
    level: str = Field(default="INFO", env="LOG_LEVEL")
    format: str = Field(default="json", env="LOG_FORMAT")  # json or text
    file_path: Optional[str] = Field(default=None, env="LOG_FILE_PATH")
    max_file_size: str = Field(default="100MB", env="LOG_MAX_FILE_SIZE")
    backup_count: int = Field(default=5, env="LOG_BACKUP_COUNT")


class PostgreSQLSettings(BaseSettings):
    """PostgreSQL配置"""
    host: str = Field(default="localhost", env="POSTGRES_HOST")
    port: int = Field(default=5432, env="POSTGRES_PORT")
    database: str = Field(default="mcp_rag", env="POSTGRES_DB")
    user: str = Field(default="mcp_user", env="POSTGRES_USER")
    password: str = Field(env="POSTGRES_PASSWORD")
    max_connections: int = Field(default=20, env="POSTGRES_MAX_CONNECTIONS")
    pool_size: int = Field(default=10, env="POSTGRES_POOL_SIZE")
    max_overflow: int = Field(default=20, env="POSTGRES_MAX_OVERFLOW")
    pool_timeout: int = Field(default=30, env="POSTGRES_POOL_TIMEOUT")
    pool_recycle: int = Field(default=3600, env="POSTGRES_POOL_RECYCLE")
    
    @property
    def database_url(self) -> str:
        """构建数据库URL"""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class RAGSettings(BaseSettings):
    """RAG配置"""
    # 嵌入模型配置
    embedding_model: str = Field(default="text-embedding-ada-002", env="RAG_EMBEDDING_MODEL")
    embedding_dimensions: int = Field(default=1536, env="RAG_EMBEDDING_DIMENSIONS")
    
    # 文本分块配置
    chunk_size: int = Field(default=1000, env="RAG_CHUNK_SIZE")
    chunk_overlap: int = Field(default=200, env="RAG_CHUNK_OVERLAP")
    
    # 搜索配置
    similarity_threshold: float = Field(default=0.7, env="RAG_SIMILARITY_THRESHOLD")
    max_search_results: int = Field(default=10, env="RAG_MAX_SEARCH_RESULTS")
    
    # 缓存配置
    enable_cache: bool = Field(default=True, env="RAG_ENABLE_CACHE")
    cache_ttl: int = Field(default=3600, env="RAG_CACHE_TTL")  # 1小时
    
    # 文档处理配置
    max_file_size: int = Field(default=10485760, env="RAG_MAX_FILE_SIZE")  # 10MB
    supported_file_types: List[str] = Field(default=["txt", "pdf", "docx", "md"], env="RAG_SUPPORTED_FILE_TYPES")


class MonitoringSettings(BaseSettings):
    """监控配置"""
    enable_prometheus: bool = Field(default=True, env="MONITORING_ENABLE_PROMETHEUS")
    prometheus_port: int = Field(default=8001, env="MONITORING_PROMETHEUS_PORT")
    enable_health_check: bool = Field(default=True, env="MONITORING_ENABLE_HEALTH_CHECK")


class Settings(BaseSettings):
    """主配置类"""
    # 环境设置
    environment: str = Field(default="development", env="ENVIRONMENT")
    debug: bool = Field(default=False, env="DEBUG")
    
    # 子配置
    redis: RedisSettings = RedisSettings()
    postgres: PostgreSQLSettings = PostgreSQLSettings()
    openai: OpenAISettings = OpenAISettings()
    mcp: MCPConnectionSettings = MCPConnectionSettings()
    api: APISettings = APISettings()
    logging: LoggingSettings = LoggingSettings()
    monitoring: MonitoringSettings = MonitoringSettings()
    rag: RAGSettings = RAGSettings()
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# 全局设置实例
settings = Settings()