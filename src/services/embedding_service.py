"""嵌入和向量化服务"""
import asyncio
import re
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

import numpy as np
from openai import AsyncOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
import tiktoken

from src.config.settings import settings
from src.utils.logging import get_structured_logger
from src.utils.cache import cache_manager
from src.services.document_service import document_service
from src.models.rag_models import Document, DocumentChunk

logger = get_structured_logger(__name__)


class EmbeddingService:
    """嵌入和向量化服务"""
    
    def __init__(self):
        self.openai_client: Optional[AsyncOpenAI] = None
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.rag.chunk_size,
            chunk_overlap=settings.rag.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", " ", ""],
        )
        
        # 初始化tokenizer用于计算token数量
        try:
            self.tokenizer = tiktoken.encoding_for_model("gpt-4")
        except KeyError:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
    
    async def initialize(self) -> None:
        """初始化服务"""
        if self.openai_client is None:
            self.openai_client = AsyncOpenAI(
                api_key=settings.openai.api_key,
                base_url=settings.openai.base_url,
                timeout=settings.openai.timeout
            )
            logger.info("嵌入服务初始化完成")
    
    async def create_embedding(self, text: str) -> List[float]:
        """为单个文本创建嵌入向量"""
        if not self.openai_client:
            await self.initialize()
        
        # 检查缓存
        cache_key = f"embedding:{hash(text)}"
        if settings.rag.enable_cache:
            cached = await cache_manager.get(cache_key)
            if cached:
                return cached
        
        try:
            # 清理和预处理文本
            cleaned_text = self._preprocess_text(text)
            
            # 调用OpenAI API
            response = await self.openai_client.embeddings.create(
                model=settings.rag.embedding_model,
                input=cleaned_text
            )
            
            embedding = response.data[0].embedding
            
            # 缓存结果
            if settings.rag.enable_cache:
                await cache_manager.set(cache_key, embedding, ttl=settings.rag.cache_ttl)
            
            return embedding
            
        except Exception as e:
            logger.error("创建嵌入失败", text_length=len(text), error=str(e))
            raise
    
    async def create_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """批量创建嵌入向量"""
        if not self.openai_client:
            await self.initialize()
        
        if not texts:
            return []
        
        try:
            # 预处理所有文本
            cleaned_texts = [self._preprocess_text(text) for text in texts]
            
            # 批量调用OpenAI API
            response = await self.openai_client.embeddings.create(
                model=settings.rag.embedding_model,
                input=cleaned_texts
            )
            
            embeddings = [data.embedding for data in response.data]
            
            logger.info("批量创建嵌入完成", count=len(embeddings))
            
            return embeddings
            
        except Exception as e:
            logger.error("批量创建嵌入失败", text_count=len(texts), error=str(e))
            raise
    
    def split_text_into_chunks(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """将文本分割成块"""
        try:
            # 使用langchain的文本分割器
            chunks = self.text_splitter.split_text(text)
            
            # 为每个块添加元数据
            chunk_dicts = []
            for i, chunk in enumerate(chunks):
                chunk_dict = {
                    "index": i,
                    "content": chunk,
                    "token_count": len(self.tokenizer.encode(chunk)),
                    "char_count": len(chunk),
                    "metadata": metadata or {}
                }
                chunk_dicts.append(chunk_dict)
            
            logger.info("文本分块完成", total_chunks=len(chunk_dicts), original_length=len(text))
            
            return chunk_dicts
            
        except Exception as e:
            logger.error("文本分块失败", text_length=len(text), error=str(e))
            raise
    
    async def process_document(self, document_id: int) -> bool:
        """处理文档：分块并创建嵌入"""
        try:
            # 获取文档
            document = await document_service.get_document_by_id(document_id)
            if not document:
                logger.warning("文档不存在", document_id=document_id)
                return False
            
            # 检查是否已经处理过
            if document.indexed_at:
                logger.info("文档已处理过", document_id=document_id)
                return True
            
            logger.info("开始处理文档", document_id=document_id, title=document.title)
            
            # 分割文本
            chunks_data = self.split_text_into_chunks(
                document.content, 
                metadata={
                    "document_id": document_id,
                    "title": document.title,
                    "file_type": document.file_type,
                    "source_url": document.source_url
                }
            )
            
            if not chunks_data:
                logger.warning("文档分块为空", document_id=document_id)
                return False
            
            # 提取所有块的文本
            chunk_texts = [chunk["content"] for chunk in chunks_data]
            
            # 批量创建嵌入
            embeddings = await self.create_embeddings_batch(chunk_texts)
            
            # 保存块和嵌入到数据库
            for chunk_data, embedding in zip(chunks_data, embeddings):
                await document_service.add_document_chunk(
                    document_id=document_id,
                    chunk_index=chunk_data["index"],
                    content=chunk_data["content"],
                    metadata=chunk_data["metadata"],
                    embedding=embedding
                )
            
            # 标记文档为已索引
            await document_service.mark_document_indexed(document_id)
            
            logger.info(
                "文档处理完成",
                document_id=document_id,
                chunks_count=len(chunks_data),
                embeddings_count=len(embeddings)
            )
            
            return True
            
        except Exception as e:
            logger.error("处理文档失败", document_id=document_id, error=str(e))
            raise
    
    async def reprocess_document(self, document_id: int) -> bool:
        """重新处理文档（删除旧块，重新分块和嵌入）"""
        try:
            document = await document_service.get_document_by_id(document_id)
            if not document:
                return False
            
            logger.info("重新处理文档", document_id=document_id)
            
            # 删除现有块（通过级联删除自动处理）
            # 这里可以添加更细粒度的控制
            
            # 重新处理
            return await self.process_document(document_id)
            
        except Exception as e:
            logger.error("重新处理文档失败", document_id=document_id, error=str(e))
            raise
    
    async def update_chunk_embedding(self, chunk_id: int, text: str) -> bool:
        """更新单个块的嵌入"""
        try:
            embedding = await self.create_embedding(text)
            success = await document_service.update_chunk_embedding(chunk_id, embedding)
            
            if success:
                logger.info("更新块嵌入成功", chunk_id=chunk_id)
            else:
                logger.warning("更新块嵌入失败，块不存在", chunk_id=chunk_id)
            
            return success
            
        except Exception as e:
            logger.error("更新块嵌入失败", chunk_id=chunk_id, error=str(e))
            raise
    
    def _preprocess_text(self, text: str) -> str:
        """预处理文本"""
        # 移除多余的空白字符
        text = re.sub(r'\s+', ' ', text)
        
        # 移除特殊字符（根据需要调整）
        text = re.sub(r'[^\w\s\u4e00-\u9fff.,!?;:()\-\[\]{}"\']', '', text)
        
        # 截断过长的文本（避免超过模型限制）
        max_tokens = 8000  # 留一些余量
        tokens = self.tokenizer.encode(text)
        if len(tokens) > max_tokens:
            tokens = tokens[:max_tokens]
            text = self.tokenizer.decode(tokens)
            logger.warning("文本被截断", original_tokens=len(self.tokenizer.encode(text)), max_tokens=max_tokens)
        
        return text.strip()
    
    def calculate_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """计算两个嵌入向量的余弦相似度"""
        try:
            # 转换为numpy数组
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)
            
            # 计算余弦相似度
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            similarity = dot_product / (norm1 * norm2)
            return float(similarity)
            
        except Exception as e:
            logger.error("计算相似度失败", error=str(e))
            return 0.0
    
    async def get_embedding_stats(self) -> Dict[str, Any]:
        """获取嵌入统计信息"""
        try:
            doc_stats = await document_service.get_document_stats()
            
            return {
                "total_documents": doc_stats["documents"]["total"],
                "indexed_documents": doc_stats["documents"]["indexed"],
                "total_chunks": doc_stats["chunks"]["total"],
                "embedded_chunks": doc_stats["chunks"]["embedded"],
                "embedding_model": settings.rag.embedding_model,
                "embedding_dimensions": settings.rag.embedding_dimensions,
                "chunk_size": settings.rag.chunk_size,
                "chunk_overlap": settings.rag.chunk_overlap,
            }
            
        except Exception as e:
            logger.error("获取嵌入统计失败", error=str(e))
            return {}
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            if not self.openai_client:
                await self.initialize()
            
            # 测试创建嵌入
            test_embedding = await self.create_embedding("test")
            
            return {
                "status": "healthy",
                "embedding_model": settings.rag.embedding_model,
                "embedding_dimensions": len(test_embedding),
                "text_splitter_chunk_size": settings.rag.chunk_size,
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# 全局服务实例
embedding_service = EmbeddingService()