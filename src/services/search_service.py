"""语义搜索和检索服务"""
import asyncio
import time
from typing import List, Dict, Any, Optional, Tuple, Union
from enum import Enum

from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import db_manager
from src.models.rag_models import (
    Document, DocumentChunk, QueryHistory, 
    QueryRequest, SearchResult, QueryResponse
)
from src.services.embedding_service import embedding_service
from src.services.document_service import document_service
from src.utils.logging import get_structured_logger
from src.utils.cache import cache_manager
from src.utils.rag_metrics import rag_metrics
from src.config.settings import settings

logger = get_structured_logger(__name__)


class SearchType(str, Enum):
    """搜索类型"""
    SEMANTIC = "semantic"
    FULLTEXT = "fulltext"
    HYBRID = "hybrid"


class SearchService:
    """搜索和检索服务"""
    
    def __init__(self):
        self.similarity_threshold = settings.rag.similarity_threshold
        self.max_results = settings.rag.max_search_results
    
    async def search(self, query_request: QueryRequest) -> QueryResponse:
        """执行搜索"""
        start_time = time.time()
        request_id = f"search_{int(start_time * 1000)}"
        
        try:
            # 参数验证和默认值
            similarity_threshold = query_request.similarity_threshold or self.similarity_threshold
            max_results = min(query_request.max_results or self.max_results, 100)
            search_type = SearchType(query_request.search_type)
            
            # 记录搜索开始
            rag_metrics.record_search_start(request_id, search_type.value)
            
            logger.info(
                "开始搜索",
                query=query_request.query[:100],
                search_type=search_type,
                user_id=query_request.user_id,
                max_results=max_results
            )
            
            # 检查缓存
            cache_key = self._generate_cache_key(query_request, similarity_threshold, max_results)
            if settings.rag.enable_cache:
                cached_result = await cache_manager.get(cache_key)
                if cached_result:
                    rag_metrics.record_cache_hit("search")
                    rag_metrics.record_search_complete(request_id, len(cached_result.results), True)
                    logger.info("返回缓存结果", cache_key=cache_key[:50])
                    return cached_result
                else:
                    rag_metrics.record_cache_miss("search")
            
            # 执行搜索
            if search_type == SearchType.SEMANTIC:
                results = await self._semantic_search(query_request.query, similarity_threshold, max_results)
            elif search_type == SearchType.FULLTEXT:
                results = await self._fulltext_search(query_request.query, max_results)
            elif search_type == SearchType.HYBRID:
                results = await self._hybrid_search(query_request.query, similarity_threshold, max_results)
            else:
                raise ValueError(f"不支持的搜索类型: {search_type}")
            
            execution_time = int((time.time() - start_time) * 1000)
            
            # 构建响应
            response = QueryResponse(
                query=query_request.query,
                results=results,
                total_results=len(results),
                execution_time_ms=execution_time,
                search_type=search_type.value
            )
            
            # 缓存结果
            if settings.rag.enable_cache and results:
                await cache_manager.set(cache_key, response, ttl=settings.rag.cache_ttl)
            
            # 记录查询历史
            await self._save_query_history(query_request, response, execution_time)
            
            # 记录搜索完成指标
            rag_metrics.record_search_complete(request_id, len(results), True)
            
            logger.info(
                "搜索完成",
                query=query_request.query[:100],
                results_count=len(results),
                execution_time_ms=execution_time
            )
            
            return response
            
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            rag_metrics.record_search_error(request_id, type(e).__name__)
            logger.error(
                "搜索失败",
                query=query_request.query[:100],
                error=str(e),
                execution_time_ms=execution_time
            )
            raise
    
    async def _semantic_search(
        self, 
        query: str, 
        similarity_threshold: float, 
        max_results: int
    ) -> List[SearchResult]:
        """语义搜索"""
        try:
            # 创建查询嵌入
            query_embedding = await embedding_service.create_embedding(query)
            
            async with db_manager.get_session() as session:
                # 使用pgvector进行相似度搜索
                stmt = text("""
                    SELECT 
                        dc.id as chunk_id,
                        dc.document_id,
                        d.title as document_title,
                        dc.content,
                        dc.metadata,
                        1 - (dc.embedding <=> :query_embedding) as similarity_score
                    FROM document_chunks dc
                    JOIN documents d ON dc.document_id = d.id
                    WHERE dc.embedding IS NOT NULL
                        AND 1 - (dc.embedding <=> :query_embedding) >= :similarity_threshold
                    ORDER BY dc.embedding <=> :query_embedding
                    LIMIT :max_results
                """)
                
                result = await session.execute(stmt, {
                    "query_embedding": query_embedding,
                    "similarity_threshold": similarity_threshold,
                    "max_results": max_results
                })
                
                rows = result.fetchall()
                
                # 转换为SearchResult对象
                search_results = []
                for row in rows:
                    search_result = SearchResult(
                        chunk_id=row.chunk_id,
                        document_id=row.document_id,
                        document_title=row.document_title,
                        content=row.content,
                        similarity_score=float(row.similarity_score),
                        metadata=row.metadata or {}
                    )
                    search_results.append(search_result)
                
                return search_results
                
        except Exception as e:
            logger.error("语义搜索失败", error=str(e))
            raise
    
    async def _fulltext_search(self, query: str, max_results: int) -> List[SearchResult]:
        """全文搜索"""
        try:
            async with db_manager.get_session() as session:
                # 使用PostgreSQL全文搜索
                stmt = text("""
                    SELECT 
                        dc.id as chunk_id,
                        dc.document_id,
                        d.title as document_title,
                        dc.content,
                        dc.metadata,
                        ts_rank(to_tsvector('english', dc.content), plainto_tsquery('english', :query)) as similarity_score
                    FROM document_chunks dc
                    JOIN documents d ON dc.document_id = d.id
                    WHERE to_tsvector('english', dc.content) @@ plainto_tsquery('english', :query)
                    ORDER BY similarity_score DESC
                    LIMIT :max_results
                """)
                
                result = await session.execute(stmt, {
                    "query": query,
                    "max_results": max_results
                })
                
                rows = result.fetchall()
                
                # 转换为SearchResult对象
                search_results = []
                for row in rows:
                    search_result = SearchResult(
                        chunk_id=row.chunk_id,
                        document_id=row.document_id,
                        document_title=row.document_title,
                        content=row.content,
                        similarity_score=float(row.similarity_score),
                        metadata=row.metadata or {}
                    )
                    search_results.append(search_result)
                
                return search_results
                
        except Exception as e:
            logger.error("全文搜索失败", error=str(e))
            raise
    
    async def _hybrid_search(
        self, 
        query: str, 
        similarity_threshold: float, 
        max_results: int
    ) -> List[SearchResult]:
        """混合搜索（语义+全文）"""
        try:
            # 并行执行语义搜索和全文搜索
            semantic_task = self._semantic_search(query, similarity_threshold, max_results)
            fulltext_task = self._fulltext_search(query, max_results)
            
            semantic_results, fulltext_results = await asyncio.gather(semantic_task, fulltext_task)
            
            # 合并和去重结果
            combined_results = {}
            
            # 添加语义搜索结果（权重：0.7）
            for result in semantic_results:
                key = result.chunk_id
                combined_results[key] = SearchResult(
                    chunk_id=result.chunk_id,
                    document_id=result.document_id,
                    document_title=result.document_title,
                    content=result.content,
                    similarity_score=result.similarity_score * 0.7,
                    metadata=result.metadata
                )
            
            # 添加全文搜索结果（权重：0.3）
            for result in fulltext_results:
                key = result.chunk_id
                if key in combined_results:
                    # 如果已存在，则合并分数
                    combined_results[key].similarity_score += result.similarity_score * 0.3
                else:
                    # 新结果
                    combined_results[key] = SearchResult(
                        chunk_id=result.chunk_id,
                        document_id=result.document_id,
                        document_title=result.document_title,
                        content=result.content,
                        similarity_score=result.similarity_score * 0.3,
                        metadata=result.metadata
                    )
            
            # 按分数排序并限制结果数量
            sorted_results = sorted(
                combined_results.values(),
                key=lambda x: x.similarity_score,
                reverse=True
            )
            
            return sorted_results[:max_results]
            
        except Exception as e:
            logger.error("混合搜索失败", error=str(e))
            raise
    
    async def search_similar_documents(
        self, 
        document_id: int, 
        max_results: int = 10
    ) -> List[SearchResult]:
        """查找与指定文档相似的文档"""
        try:
            # 获取文档的第一个块作为查询
            chunks = await document_service.get_document_chunks(document_id)
            if not chunks or not chunks[0].embedding:
                return []
            
            query_embedding = chunks[0].embedding
            
            async with db_manager.get_session() as session:
                stmt = text("""
                    SELECT DISTINCT
                        dc.document_id,
                        d.title as document_title,
                        d.content,
                        AVG(1 - (dc.embedding <=> :query_embedding)) as avg_similarity
                    FROM document_chunks dc
                    JOIN documents d ON dc.document_id = d.id
                    WHERE dc.embedding IS NOT NULL
                        AND dc.document_id != :document_id
                    GROUP BY dc.document_id, d.title, d.content
                    HAVING AVG(1 - (dc.embedding <=> :query_embedding)) >= 0.5
                    ORDER BY avg_similarity DESC
                    LIMIT :max_results
                """)
                
                result = await session.execute(stmt, {
                    "query_embedding": query_embedding,
                    "document_id": document_id,
                    "max_results": max_results
                })
                
                rows = result.fetchall()
                
                # 转换为SearchResult对象
                search_results = []
                for row in rows:
                    search_result = SearchResult(
                        chunk_id=0,  # 不适用于文档级别搜索
                        document_id=row.document_id,
                        document_title=row.document_title,
                        content=row.content[:500] + "..." if len(row.content) > 500 else row.content,
                        similarity_score=float(row.avg_similarity),
                        metadata={}
                    )
                    search_results.append(search_result)
                
                return search_results
                
        except Exception as e:
            logger.error("相似文档搜索失败", document_id=document_id, error=str(e))
            raise
    
    async def _save_query_history(
        self, 
        query_request: QueryRequest, 
        response: QueryResponse, 
        execution_time: int
    ) -> None:
        """保存查询历史"""
        try:
            # 创建查询嵌入（仅用于语义搜索）
            query_embedding = None
            if query_request.search_type == "semantic":
                query_embedding = await embedding_service.create_embedding(query_request.query)
            
            async with db_manager.get_session() as session:
                query_history = QueryHistory(
                    query_text=query_request.query,
                    query_embedding=query_embedding,
                    user_id=query_request.user_id,
                    session_id=query_request.session_id,
                    results=response.dict(),
                    matched_chunks=[result.chunk_id for result in response.results],
                    similarity_scores=[result.similarity_score for result in response.results],
                    execution_time_ms=execution_time,
                    total_chunks_searched=response.total_results
                )
                
                session.add(query_history)
                
        except Exception as e:
            logger.warning("保存查询历史失败", error=str(e))
    
    def _generate_cache_key(
        self, 
        query_request: QueryRequest, 
        similarity_threshold: float, 
        max_results: int
    ) -> str:
        """生成缓存键"""
        key_parts = [
            "search",
            hash(query_request.query),
            query_request.search_type,
            str(similarity_threshold),
            str(max_results)
        ]
        return ":".join(map(str, key_parts))
    
    async def get_search_suggestions(self, partial_query: str, limit: int = 5) -> List[str]:
        """获取搜索建议"""
        try:
            async with db_manager.get_session() as session:
                # 基于历史查询提供建议
                stmt = select(QueryHistory.query_text).where(
                    QueryHistory.query_text.ilike(f"%{partial_query}%")
                ).distinct().order_by(
                    func.length(QueryHistory.query_text)
                ).limit(limit)
                
                result = await session.execute(stmt)
                suggestions = [row[0] for row in result.fetchall()]
                
                return suggestions
                
        except Exception as e:
            logger.error("获取搜索建议失败", error=str(e))
            return []
    
    async def get_search_stats(self) -> Dict[str, Any]:
        """获取搜索统计信息"""
        try:
            async with db_manager.get_session() as session:
                # 查询统计
                query_stats_stmt = select(
                    func.count(QueryHistory.id).label("total_queries"),
                    func.avg(QueryHistory.execution_time_ms).label("avg_execution_time"),
                    func.max(QueryHistory.execution_time_ms).label("max_execution_time"),
                    func.count(func.distinct(QueryHistory.user_id)).label("unique_users")
                ).where(
                    QueryHistory.created_at >= text("NOW() - INTERVAL '24 hours'")
                )
                
                query_result = await session.execute(query_stats_stmt)
                query_stats = query_result.first()
                
                # 搜索类型分布
                type_dist_stmt = select(
                    func.count().label("count")
                ).select_from(QueryHistory).where(
                    QueryHistory.created_at >= text("NOW() - INTERVAL '24 hours'")
                )
                
                type_result = await session.execute(type_dist_stmt)
                
                return {
                    "queries_24h": {
                        "total": query_stats.total_queries or 0,
                        "unique_users": query_stats.unique_users or 0,
                        "avg_execution_time_ms": float(query_stats.avg_execution_time or 0),
                        "max_execution_time_ms": query_stats.max_execution_time or 0,
                    },
                    "search_config": {
                        "similarity_threshold": self.similarity_threshold,
                        "max_results": self.max_results,
                        "embedding_model": settings.rag.embedding_model,
                    }
                }
                
        except Exception as e:
            logger.error("获取搜索统计失败", error=str(e))
            return {}
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            # 执行简单的测试搜索
            test_request = QueryRequest(query="test", search_type="semantic")
            test_response = await self.search(test_request)
            
            return {
                "status": "healthy",
                "test_search_time_ms": test_response.execution_time_ms,
                "similarity_threshold": self.similarity_threshold,
                "max_results": self.max_results
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# 全局服务实例
search_service = SearchService()