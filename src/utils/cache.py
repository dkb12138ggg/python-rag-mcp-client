"""缓存系统"""
import asyncio
import json
import time
from typing import Any, Dict, Optional, Union
from dataclasses import dataclass
from abc import ABC, abstractmethod

import redis.asyncio as redis
from src.config.settings import settings
from src.utils.logging import get_structured_logger

logger = get_structured_logger(__name__)


@dataclass
class CacheEntry:
    """缓存条目"""
    value: Any
    timestamp: float
    ttl: int
    key: str


class CacheBackend(ABC):
    """缓存后端抽象基类"""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """设置缓存"""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除缓存"""
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        pass
    
    @abstractmethod
    async def clear(self) -> bool:
        """清空缓存"""
        pass


class MemoryCache(CacheBackend):
    """内存缓存"""
    
    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._start_cleanup()
    
    def _start_cleanup(self):
        """启动清理任务"""
        self._cleanup_task = asyncio.create_task(self._cleanup_expired())
    
    async def _cleanup_expired(self):
        """清理过期缓存"""
        while True:
            try:
                await asyncio.sleep(60)  # 每分钟清理一次
                current_time = time.time()
                
                async with self._lock:
                    expired_keys = []
                    for key, entry in self._cache.items():
                        if current_time - entry.timestamp > entry.ttl:
                            expired_keys.append(key)
                    
                    for key in expired_keys:
                        del self._cache[key]
                    
                    if expired_keys:
                        logger.debug("清理过期缓存", count=len(expired_keys))
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("缓存清理失败", error=str(e))
    
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        async with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            
            # 检查是否过期
            if time.time() - entry.timestamp > entry.ttl:
                del self._cache[key]
                return None
            
            return entry.value
    
    async def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """设置缓存"""
        try:
            async with self._lock:
                self._cache[key] = CacheEntry(
                    value=value,
                    timestamp=time.time(),
                    ttl=ttl,
                    key=key
                )
            return True
        except Exception as e:
            logger.error("设置缓存失败", key=key, error=str(e))
            return False
    
    async def delete(self, key: str) -> bool:
        """删除缓存"""
        try:
            async with self._lock:
                if key in self._cache:
                    del self._cache[key]
                    return True
                return False
        except Exception as e:
            logger.error("删除缓存失败", key=key, error=str(e))
            return False
    
    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        return await self.get(key) is not None
    
    async def clear(self) -> bool:
        """清空缓存"""
        try:
            async with self._lock:
                self._cache.clear()
            return True
        except Exception as e:
            logger.error("清空缓存失败", error=str(e))
            return False
    
    async def shutdown(self):
        """关闭缓存"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass


class RedisCache(CacheBackend):
    """Redis缓存"""
    
    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._connected = False
    
    async def _ensure_connected(self):
        """确保Redis连接"""
        if not self._connected:
            try:
                self._redis = redis.Redis(
                    host=settings.redis.host,
                    port=settings.redis.port,
                    db=settings.redis.db,
                    password=settings.redis.password,
                    max_connections=settings.redis.max_connections,
                    decode_responses=True
                )
                await self._redis.ping()
                self._connected = True
                logger.info("Redis连接成功")
            except Exception as e:
                logger.error("Redis连接失败", error=str(e))
                raise
    
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        try:
            await self._ensure_connected()
            value = await self._redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error("获取Redis缓存失败", key=key, error=str(e))
            return None
    
    async def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """设置缓存"""
        try:
            await self._ensure_connected()
            serialized_value = json.dumps(value, ensure_ascii=False)
            await self._redis.setex(key, ttl, serialized_value)
            return True
        except Exception as e:
            logger.error("设置Redis缓存失败", key=key, error=str(e))
            return False
    
    async def delete(self, key: str) -> bool:
        """删除缓存"""
        try:
            await self._ensure_connected()
            result = await self._redis.delete(key)
            return result > 0
        except Exception as e:
            logger.error("删除Redis缓存失败", key=key, error=str(e))
            return False
    
    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        try:
            await self._ensure_connected()
            return await self._redis.exists(key) > 0
        except Exception as e:
            logger.error("检查Redis键存在失败", key=key, error=str(e))
            return False
    
    async def clear(self) -> bool:
        """清空缓存"""
        try:
            await self._ensure_connected()
            await self._redis.flushdb()
            return True
        except Exception as e:
            logger.error("清空Redis缓存失败", error=str(e))
            return False
    
    async def shutdown(self):
        """关闭Redis连接"""
        if self._redis:
            await self._redis.close()
            self._connected = False


class CacheManager:
    """缓存管理器"""
    
    def __init__(self):
        self._backend: Optional[CacheBackend] = None
        self._initialized = False
    
    async def initialize(self):
        """初始化缓存"""
        if self._initialized:
            return
        
        try:
            # 尝试使用Redis
            self._backend = RedisCache()
            await self._backend._ensure_connected()
            logger.info("使用Redis缓存")
        except Exception as e:
            logger.warning("Redis不可用，使用内存缓存", error=str(e))
            self._backend = MemoryCache()
        
        self._initialized = True
    
    async def get_tools_cache(self, server_name: str) -> Optional[list]:
        """获取工具缓存"""
        if not self._initialized:
            await self.initialize()
        
        key = f"tools:{server_name}"
        return await self._backend.get(key)
    
    async def set_tools_cache(self, server_name: str, tools: list, ttl: int = 300) -> bool:
        """设置工具缓存"""
        if not self._initialized:
            await self.initialize()
        
        key = f"tools:{server_name}"
        return await self._backend.set(key, tools, ttl)
    
    async def get_query_cache(self, query_hash: str) -> Optional[dict]:
        """获取查询缓存"""
        if not self._initialized:
            await self.initialize()
        
        key = f"query:{query_hash}"
        return await self._backend.get(key)
    
    async def set_query_cache(self, query_hash: str, response: dict, ttl: int = 60) -> bool:
        """设置查询缓存"""
        if not self._initialized:
            await self.initialize()
        
        key = f"query:{query_hash}"
        return await self._backend.set(key, response, ttl)
    
    async def get_connection_status(self, server_name: str) -> Optional[dict]:
        """获取连接状态缓存"""
        if not self._initialized:
            await self.initialize()
        
        key = f"status:{server_name}"
        return await self._backend.get(key)
    
    async def set_connection_status(self, server_name: str, status: dict, ttl: int = 30) -> bool:
        """设置连接状态缓存"""
        if not self._initialized:
            await self.initialize()
        
        key = f"status:{server_name}"
        return await self._backend.set(key, status, ttl)
    
    async def clear_server_cache(self, server_name: str) -> bool:
        """清空服务器相关缓存"""
        if not self._initialized:
            await self.initialize()
        
        keys = [
            f"tools:{server_name}",
            f"status:{server_name}"
        ]
        
        success = True
        for key in keys:
            result = await self._backend.delete(key)
            success = success and result
        
        return success
    
    async def shutdown(self):
        """关闭缓存"""
        if self._backend:
            await self._backend.shutdown()


# 全局缓存管理器实例
cache_manager = CacheManager()