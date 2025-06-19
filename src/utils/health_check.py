"""健康检查系统"""
import asyncio
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from src.utils.logging import get_structured_logger
from src.utils.cache import cache_manager

logger = get_structured_logger(__name__)


class HealthStatus(Enum):
    """健康状态枚举"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    component: str
    status: HealthStatus
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    response_time: float = 0.0


@dataclass
class SystemHealth:
    """系统健康状态"""
    overall_status: HealthStatus
    components: List[HealthCheckResult]
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "overall_status": self.overall_status.value,
            "timestamp": self.timestamp,
            "components": [
                {
                    "component": result.component,
                    "status": result.status.value,
                    "message": result.message,
                    "details": result.details,
                    "response_time": result.response_time,
                    "timestamp": result.timestamp
                }
                for result in self.components
            ]
        }


class HealthChecker:
    """健康检查器"""
    
    def __init__(self):
        self._last_check: Optional[SystemHealth] = None
        self._check_interval = 30  # 秒
        self._check_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self):
        """启动健康检查"""
        if self._running:
            return
        
        self._running = True
        self._check_task = asyncio.create_task(self._periodic_check())
        logger.info("健康检查启动")
    
    async def stop(self):
        """停止健康检查"""
        self._running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        logger.info("健康检查停止")
    
    async def _periodic_check(self):
        """定期健康检查"""
        while self._running:
            try:
                await self.check_system_health()
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("定期健康检查失败", error=str(e))
                await asyncio.sleep(self._check_interval)
    
    async def check_system_health(self) -> SystemHealth:
        """检查系统健康状态"""
        components = []
        
        # 并发执行所有健康检查
        check_tasks = [
            self._check_cache(),
            self._check_memory(),
            self._check_disk_space(),
            self._check_network(),
        ]
        
        results = await asyncio.gather(*check_tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, HealthCheckResult):
                components.append(result)
            elif isinstance(result, Exception):
                components.append(HealthCheckResult(
                    component="unknown",
                    status=HealthStatus.UNHEALTHY,
                    message=f"健康检查异常: {str(result)}"
                ))
        
        # 计算整体健康状态
        overall_status = self._calculate_overall_status(components)
        
        system_health = SystemHealth(
            overall_status=overall_status,
            components=components
        )
        
        self._last_check = system_health
        
        # 记录健康状态变化
        if overall_status != HealthStatus.HEALTHY:
            logger.warning("系统健康状态异常", status=overall_status.value)
        
        return system_health
    
    def _calculate_overall_status(self, components: List[HealthCheckResult]) -> HealthStatus:
        """计算整体健康状态"""
        if not components:
            return HealthStatus.UNKNOWN
        
        unhealthy_count = sum(1 for c in components if c.status == HealthStatus.UNHEALTHY)
        degraded_count = sum(1 for c in components if c.status == HealthStatus.DEGRADED)
        
        # 如果有任何组件不健康，整体状态为不健康
        if unhealthy_count > 0:
            return HealthStatus.UNHEALTHY
        
        # 如果有降级组件，整体状态为降级
        if degraded_count > 0:
            return HealthStatus.DEGRADED
        
        return HealthStatus.HEALTHY
    
    async def _check_cache(self) -> HealthCheckResult:
        """检查缓存健康状态"""
        start_time = time.time()
        
        try:
            # 尝试设置和获取测试键
            test_key = "health_check_test"
            test_value = {"timestamp": time.time()}
            
            await cache_manager.initialize()
            
            # 设置测试值
            set_success = await cache_manager._backend.set(test_key, test_value, 60)
            if not set_success:
                return HealthCheckResult(
                    component="cache",
                    status=HealthStatus.UNHEALTHY,
                    message="缓存设置失败",
                    response_time=time.time() - start_time
                )
            
            # 获取测试值
            retrieved_value = await cache_manager._backend.get(test_key)
            if retrieved_value != test_value:
                return HealthCheckResult(
                    component="cache",
                    status=HealthStatus.UNHEALTHY,
                    message="缓存读取不一致",
                    response_time=time.time() - start_time
                )
            
            # 清理测试键
            await cache_manager._backend.delete(test_key)
            
            response_time = time.time() - start_time
            
            if response_time > 1.0:  # 响应时间超过1秒视为降级
                return HealthCheckResult(
                    component="cache",
                    status=HealthStatus.DEGRADED,
                    message=f"缓存响应缓慢: {response_time:.2f}s",
                    response_time=response_time
                )
            
            return HealthCheckResult(
                component="cache",
                status=HealthStatus.HEALTHY,
                message="缓存正常",
                response_time=response_time
            )
            
        except Exception as e:
            return HealthCheckResult(
                component="cache",
                status=HealthStatus.UNHEALTHY,
                message=f"缓存检查失败: {str(e)}",
                response_time=time.time() - start_time
            )
    
    async def _check_memory(self) -> HealthCheckResult:
        """检查内存使用情况"""
        start_time = time.time()
        
        try:
            import psutil
            
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            status = HealthStatus.HEALTHY
            message = f"内存使用率: {memory_percent:.1f}%"
            
            if memory_percent > 90:
                status = HealthStatus.UNHEALTHY
                message = f"内存使用率过高: {memory_percent:.1f}%"
            elif memory_percent > 80:
                status = HealthStatus.DEGRADED
                message = f"内存使用率较高: {memory_percent:.1f}%"
            
            return HealthCheckResult(
                component="memory",
                status=status,
                message=message,
                details={
                    "memory_percent": memory_percent,
                    "total_gb": round(memory.total / (1024**3), 2),
                    "available_gb": round(memory.available / (1024**3), 2)
                },
                response_time=time.time() - start_time
            )
            
        except ImportError:
            return HealthCheckResult(
                component="memory",
                status=HealthStatus.UNKNOWN,
                message="psutil模块未安装，无法检查内存",
                response_time=time.time() - start_time
            )
        except Exception as e:
            return HealthCheckResult(
                component="memory",
                status=HealthStatus.UNHEALTHY,
                message=f"内存检查失败: {str(e)}",
                response_time=time.time() - start_time
            )
    
    async def _check_disk_space(self) -> HealthCheckResult:
        """检查磁盘空间"""
        start_time = time.time()
        
        try:
            import psutil
            
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            
            status = HealthStatus.HEALTHY
            message = f"磁盘使用率: {disk_percent:.1f}%"
            
            if disk_percent > 95:
                status = HealthStatus.UNHEALTHY
                message = f"磁盘空间不足: {disk_percent:.1f}%"
            elif disk_percent > 85:
                status = HealthStatus.DEGRADED
                message = f"磁盘空间较少: {disk_percent:.1f}%"
            
            return HealthCheckResult(
                component="disk",
                status=status,
                message=message,
                details={
                    "disk_percent": disk_percent,
                    "total_gb": round(disk.total / (1024**3), 2),
                    "free_gb": round(disk.free / (1024**3), 2)
                },
                response_time=time.time() - start_time
            )
            
        except ImportError:
            return HealthCheckResult(
                component="disk",
                status=HealthStatus.UNKNOWN,
                message="psutil模块未安装，无法检查磁盘",
                response_time=time.time() - start_time
            )
        except Exception as e:
            return HealthCheckResult(
                component="disk",
                status=HealthStatus.UNHEALTHY,
                message=f"磁盘检查失败: {str(e)}",
                response_time=time.time() - start_time
            )
    
    async def _check_network(self) -> HealthCheckResult:
        """检查网络连接"""
        start_time = time.time()
        
        try:
            import aiohttp
            
            # 测试网络连接
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get('https://httpbin.org/status/200') as response:
                    if response.status == 200:
                        response_time = time.time() - start_time
                        
                        if response_time > 3.0:
                            return HealthCheckResult(
                                component="network",
                                status=HealthStatus.DEGRADED,
                                message=f"网络响应缓慢: {response_time:.2f}s",
                                response_time=response_time
                            )
                        
                        return HealthCheckResult(
                            component="network",
                            status=HealthStatus.HEALTHY,
                            message="网络连接正常",
                            response_time=response_time
                        )
                    else:
                        return HealthCheckResult(
                            component="network",
                            status=HealthStatus.UNHEALTHY,
                            message=f"网络测试失败: HTTP {response.status}",
                            response_time=time.time() - start_time
                        )
                        
        except Exception as e:
            return HealthCheckResult(
                component="network",
                status=HealthStatus.UNHEALTHY,
                message=f"网络检查失败: {str(e)}",
                response_time=time.time() - start_time
            )
    
    def get_last_check(self) -> Optional[SystemHealth]:
        """获取最后一次检查结果"""
        return self._last_check


# 全局健康检查器实例
health_checker = HealthChecker()