"""数据库连接和会话管理"""
import asyncio
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from sqlalchemy import event
from sqlalchemy.engine import Engine

from src.config.settings import settings
from src.utils.logging import get_structured_logger

logger = get_structured_logger(__name__)


class Base(DeclarativeBase):
    """SQLAlchemy基础模型类"""
    pass


class DatabaseManager:
    """数据库连接管理器"""
    
    def __init__(self):
        self.engine: Optional[Engine] = None
        self.session_factory: Optional[async_sessionmaker] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """初始化数据库连接"""
        if self._initialized:
            return
        
        logger.info("初始化数据库连接")
        
        # 创建异步引擎
        self.engine = create_async_engine(
            settings.postgres.database_url,
            # 连接池配置
            pool_size=settings.postgres.pool_size,
            max_overflow=settings.postgres.max_overflow,
            pool_timeout=settings.postgres.pool_timeout,
            pool_recycle=settings.postgres.pool_recycle,
            pool_pre_ping=True,  # 连接前ping检查
            # 其他配置
            echo=settings.debug,  # 开发环境下打印SQL
            echo_pool=settings.debug,  # 开发环境下打印连接池信息
            future=True,
        )
        
        # 创建会话工厂
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=True,
            autocommit=False,
        )
        
        # 注册事件监听器
        self._register_event_listeners()
        
        # 测试连接
        await self._test_connection()
        
        self._initialized = True
        logger.info("数据库连接初始化完成")
    
    def _register_event_listeners(self) -> None:
        """注册数据库事件监听器"""
        
        @event.listens_for(self.engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            """连接时设置数据库参数（如果需要）"""
            pass
        
        @event.listens_for(self.engine.sync_engine, "checkout")
        def checkout_listener(dbapi_connection, connection_record, connection_proxy):
            """连接检出时的处理"""
            logger.debug("数据库连接检出", connection_id=id(dbapi_connection))
        
        @event.listens_for(self.engine.sync_engine, "checkin")
        def checkin_listener(dbapi_connection, connection_record):
            """连接归还时的处理"""
            logger.debug("数据库连接归还", connection_id=id(dbapi_connection))
    
    async def _test_connection(self) -> None:
        """测试数据库连接"""
        try:
            async with self.get_session() as session:
                result = await session.execute("SELECT 1")
                row = result.fetchone()
                if row[0] != 1:
                    raise Exception("数据库连接测试失败")
            logger.info("数据库连接测试成功")
        except Exception as e:
            logger.error("数据库连接测试失败", error=str(e))
            raise
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """获取数据库会话上下文管理器"""
        if not self._initialized:
            await self.initialize()
        
        if not self.session_factory:
            raise RuntimeError("数据库未初始化")
        
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    
    async def get_session_direct(self) -> AsyncSession:
        """直接获取数据库会话（需要手动管理）"""
        if not self._initialized:
            await self.initialize()
        
        if not self.session_factory:
            raise RuntimeError("数据库未初始化")
        
        return self.session_factory()
    
    async def health_check(self) -> dict:
        """数据库健康检查"""
        try:
            if not self._initialized:
                return {"status": "uninitialized", "error": "数据库未初始化"}
            
            # 测试连接
            start_time = asyncio.get_event_loop().time()
            async with self.get_session() as session:
                await session.execute("SELECT 1")
            response_time = (asyncio.get_event_loop().time() - start_time) * 1000
            
            # 获取连接池信息
            pool = self.engine.pool
            pool_info = {
                "size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
                "total": pool.size() + pool.overflow(),
            }
            
            return {
                "status": "healthy",
                "response_time_ms": round(response_time, 2),
                "pool_info": pool_info,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def get_pool_metrics(self) -> dict:
        """获取连接池指标"""
        if not self.engine:
            return {}
        
        pool = self.engine.pool
        return {
            "pool_size": pool.size(),
            "checked_in_connections": pool.checkedin(),
            "checked_out_connections": pool.checkedout(),
            "overflow_connections": pool.overflow(),
            "total_connections": pool.size() + pool.overflow(),
        }
    
    async def close(self) -> None:
        """关闭数据库连接"""
        if self.engine:
            logger.info("关闭数据库连接")
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None
            self._initialized = False
            logger.info("数据库连接已关闭")


# 全局数据库管理器实例
db_manager = DatabaseManager()


# 便捷函数
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话的便捷函数"""
    async with db_manager.get_session() as session:
        yield session


async def init_database() -> None:
    """初始化数据库的便捷函数"""
    await db_manager.initialize()


async def close_database() -> None:
    """关闭数据库的便捷函数"""
    await db_manager.close()