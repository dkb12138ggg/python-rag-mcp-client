"""文档管理服务"""
import hashlib
import asyncio
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from sqlalchemy import select, func, desc, asc, text
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import db_manager
from src.models.rag_models import Document, DocumentChunk, DocumentCreate, DocumentUpdate
from src.utils.logging import get_structured_logger
from src.utils.cache import cache_manager
from src.config.settings import settings

logger = get_structured_logger(__name__)


class DocumentService:
    """文档管理服务"""
    
    def __init__(self):
        self.cache_ttl = settings.rag.cache_ttl
    
    async def create_document(
        self, 
        document_data: DocumentCreate,
        file_content: Optional[bytes] = None
    ) -> Document:
        """创建新文档"""
        async with db_manager.get_session() as session:
            # 计算文件哈希
            file_hash = None
            file_size = None
            if file_content:
                file_hash = hashlib.sha256(file_content).hexdigest()
                file_size = len(file_content)
                
                # 检查是否已存在相同哈希的文档
                existing = await self._get_document_by_hash(session, file_hash)
                if existing:
                    logger.info("文档已存在", file_hash=file_hash[:16], document_id=existing.id)
                    return existing
            
            # 创建新文档
            document = Document(
                title=document_data.title,
                content=document_data.content,
                metadata=document_data.metadata,
                file_type=document_data.file_type,
                file_size=file_size,
                file_hash=file_hash,
                source_url=document_data.source_url,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            session.add(document)
            await session.flush()  # 获取ID
            
            logger.info(
                "创建文档",
                document_id=document.id,
                title=document.title,
                file_type=document.file_type,
                file_size=file_size
            )
            
            # 清除相关缓存
            await self._clear_document_caches()
            
            return document
    
    async def get_document_by_id(self, document_id: int) -> Optional[Document]:
        """根据ID获取文档"""
        cache_key = f"document:{document_id}"
        
        # 尝试从缓存获取
        if settings.rag.enable_cache:
            cached = await cache_manager.get(cache_key)
            if cached:
                return cached
        
        async with db_manager.get_session() as session:
            stmt = select(Document).options(
                selectinload(Document.chunks)
            ).where(Document.id == document_id)
            
            result = await session.execute(stmt)
            document = result.scalar_one_or_none()
            
            # 缓存结果
            if document and settings.rag.enable_cache:
                await cache_manager.set(cache_key, document, ttl=self.cache_ttl)
            
            return document
    
    async def _get_document_by_hash(self, session: AsyncSession, file_hash: str) -> Optional[Document]:
        """根据文件哈希获取文档"""
        stmt = select(Document).where(Document.file_hash == file_hash)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def update_document(
        self, 
        document_id: int, 
        document_data: DocumentUpdate
    ) -> Optional[Document]:
        """更新文档"""
        async with db_manager.get_session() as session:
            stmt = select(Document).where(Document.id == document_id)
            result = await session.execute(stmt)
            document = result.scalar_one_or_none()
            
            if not document:
                return None
            
            # 更新字段
            update_fields = document_data.dict(exclude_unset=True)
            for field, value in update_fields.items():
                setattr(document, field, value)
            
            document.updated_at = datetime.utcnow()
            
            logger.info("更新文档", document_id=document_id, updated_fields=list(update_fields.keys()))
            
            # 清除缓存
            await self._clear_document_caches(document_id)
            
            return document
    
    async def delete_document(self, document_id: int) -> bool:
        """删除文档"""
        async with db_manager.get_session() as session:
            stmt = select(Document).where(Document.id == document_id)
            result = await session.execute(stmt)
            document = result.scalar_one_or_none()
            
            if not document:
                return False
            
            await session.delete(document)
            
            logger.info("删除文档", document_id=document_id, title=document.title)
            
            # 清除缓存
            await self._clear_document_caches(document_id)
            
            return True
    
    async def list_documents(
        self,
        offset: int = 0,
        limit: int = 50,
        order_by: str = "created_at",
        order_direction: str = "desc",
        search_query: Optional[str] = None,
        file_type: Optional[str] = None
    ) -> Tuple[List[Document], int]:
        """获取文档列表"""
        async with db_manager.get_session() as session:
            # 构建查询
            stmt = select(Document)
            count_stmt = select(func.count(Document.id))
            
            # 添加搜索条件
            if search_query:
                search_filter = Document.title.ilike(f"%{search_query}%")
                stmt = stmt.where(search_filter)
                count_stmt = count_stmt.where(search_filter)
            
            if file_type:
                type_filter = Document.file_type == file_type
                stmt = stmt.where(type_filter)
                count_stmt = count_stmt.where(type_filter)
            
            # 添加排序
            order_column = getattr(Document, order_by, Document.created_at)
            if order_direction.lower() == "desc":
                stmt = stmt.order_by(desc(order_column))
            else:
                stmt = stmt.order_by(asc(order_column))
            
            # 添加分页
            stmt = stmt.offset(offset).limit(limit)
            
            # 执行查询
            result = await session.execute(stmt)
            documents = result.scalars().all()
            
            # 获取总数
            count_result = await session.execute(count_stmt)
            total_count = count_result.scalar()
            
            return list(documents), total_count
    
    async def get_document_chunks(
        self, 
        document_id: int,
        include_embeddings: bool = False
    ) -> List[DocumentChunk]:
        """获取文档的所有块"""
        async with db_manager.get_session() as session:
            stmt = select(DocumentChunk).where(
                DocumentChunk.document_id == document_id
            ).order_by(DocumentChunk.chunk_index)
            
            result = await session.execute(stmt)
            chunks = result.scalars().all()
            
            return list(chunks)
    
    async def add_document_chunk(
        self,
        document_id: int,
        chunk_index: int,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None
    ) -> DocumentChunk:
        """为文档添加块"""
        async with db_manager.get_session() as session:
            chunk = DocumentChunk(
                document_id=document_id,
                chunk_index=chunk_index,
                content=content,
                metadata=metadata or {},
                embedding=embedding,
                created_at=datetime.utcnow()
            )
            
            session.add(chunk)
            await session.flush()
            
            logger.debug(
                "添加文档块",
                document_id=document_id,
                chunk_id=chunk.id,
                chunk_index=chunk_index,
                has_embedding=embedding is not None
            )
            
            # 清除相关缓存
            await self._clear_document_caches(document_id)
            
            return chunk
    
    async def update_chunk_embedding(
        self,
        chunk_id: int,
        embedding: List[float]
    ) -> bool:
        """更新块的嵌入向量"""
        async with db_manager.get_session() as session:
            stmt = select(DocumentChunk).where(DocumentChunk.id == chunk_id)
            result = await session.execute(stmt)
            chunk = result.scalar_one_or_none()
            
            if not chunk:
                return False
            
            chunk.embedding = embedding
            
            logger.debug("更新块嵌入", chunk_id=chunk_id, document_id=chunk.document_id)
            
            return True
    
    async def mark_document_indexed(self, document_id: int) -> bool:
        """标记文档为已索引"""
        async with db_manager.get_session() as session:
            stmt = select(Document).where(Document.id == document_id)
            result = await session.execute(stmt)
            document = result.scalar_one_or_none()
            
            if not document:
                return False
            
            document.indexed_at = datetime.utcnow()
            
            logger.info("标记文档已索引", document_id=document_id)
            
            # 清除缓存
            await self._clear_document_caches(document_id)
            
            return True
    
    async def get_document_stats(self) -> Dict[str, Any]:
        """获取文档统计信息"""
        cache_key = "document_stats"
        
        # 尝试从缓存获取
        if settings.rag.enable_cache:
            cached = await cache_manager.get(cache_key)
            if cached:
                return cached
        
        async with db_manager.get_session() as session:
            # 文档统计
            doc_stats_stmt = select(
                func.count(Document.id).label("total_documents"),
                func.count(Document.indexed_at).label("indexed_documents"),
                func.sum(Document.file_size).label("total_size"),
                func.avg(Document.file_size).label("avg_size"),
                func.count(func.distinct(Document.file_type)).label("unique_file_types")
            )
            
            doc_result = await session.execute(doc_stats_stmt)
            doc_stats = doc_result.first()
            
            # 块统计
            chunk_stats_stmt = select(
                func.count(DocumentChunk.id).label("total_chunks"),
                func.count(DocumentChunk.embedding).label("embedded_chunks")
            )
            
            chunk_result = await session.execute(chunk_stats_stmt)
            chunk_stats = chunk_result.first()
            
            # 文件类型分布
            type_dist_stmt = select(
                Document.file_type,
                func.count(Document.id).label("count")
            ).group_by(Document.file_type)
            
            type_result = await session.execute(type_dist_stmt)
            type_distribution = {row.file_type or "unknown": row.count for row in type_result}
            
            stats = {
                "documents": {
                    "total": doc_stats.total_documents or 0,
                    "indexed": doc_stats.indexed_documents or 0,
                    "unindexed": (doc_stats.total_documents or 0) - (doc_stats.indexed_documents or 0),
                    "total_size_bytes": int(doc_stats.total_size or 0),
                    "avg_size_bytes": int(doc_stats.avg_size or 0),
                    "unique_file_types": doc_stats.unique_file_types or 0,
                },
                "chunks": {
                    "total": chunk_stats.total_chunks or 0,
                    "embedded": chunk_stats.embedded_chunks or 0,
                    "unembedded": (chunk_stats.total_chunks or 0) - (chunk_stats.embedded_chunks or 0),
                },
                "file_type_distribution": type_distribution,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            # 缓存结果
            if settings.rag.enable_cache:
                await cache_manager.set(cache_key, stats, ttl=300)  # 5分钟缓存
            
            return stats
    
    async def search_documents_fulltext(
        self,
        query: str,
        limit: int = 10
    ) -> List[Tuple[Document, float]]:
        """全文搜索文档"""
        async with db_manager.get_session() as session:
            # 使用PostgreSQL的全文搜索
            stmt = text("""
                SELECT d.*, ts_rank(d.search_vector, plainto_tsquery('english', :query)) as rank
                FROM documents d
                WHERE d.search_vector @@ plainto_tsquery('english', :query)
                ORDER BY rank DESC
                LIMIT :limit
            """)
            
            result = await session.execute(stmt, {"query": query, "limit": limit})
            rows = result.fetchall()
            
            documents_with_scores = []
            for row in rows:
                # 重新获取完整的Document对象
                doc_stmt = select(Document).where(Document.id == row.id)
                doc_result = await session.execute(doc_stmt)
                document = doc_result.scalar_one()
                documents_with_scores.append((document, float(row.rank)))
            
            return documents_with_scores
    
    async def _clear_document_caches(self, document_id: Optional[int] = None) -> None:
        """清除文档相关缓存"""
        if not settings.rag.enable_cache:
            return
        
        tasks = []
        
        # 清除统计缓存
        tasks.append(cache_manager.delete("document_stats"))
        
        # 清除特定文档缓存
        if document_id:
            tasks.append(cache_manager.delete(f"document:{document_id}"))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            stats = await self.get_document_stats()
            return {
                "status": "healthy",
                "document_count": stats["documents"]["total"],
                "indexed_documents": stats["documents"]["indexed"],
                "chunk_count": stats["chunks"]["total"],
                "embedded_chunks": stats["chunks"]["embedded"]
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# 全局服务实例
document_service = DocumentService()