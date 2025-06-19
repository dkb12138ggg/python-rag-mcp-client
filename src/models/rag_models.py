"""RAG相关数据模型"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, JSON, 
    ForeignKey, Boolean, Float, ARRAY, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
import uuid

from src.core.database import Base


class Document(Base):
    """文档表"""
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False, index=True)
    content = Column(Text, nullable=False)
    metadata = Column(JSON, default={})
    file_type = Column(String(50), index=True)
    file_size = Column(Integer)
    file_hash = Column(String(64), unique=True, index=True)
    source_url = Column(Text)
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    indexed_at = Column(DateTime, nullable=True)
    
    # 关系
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Document(id={self.id}, title='{self.title}', file_type='{self.file_type}')>"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "metadata": self.metadata,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "file_hash": self.file_hash,
            "source_url": self.source_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "indexed_at": self.indexed_at.isoformat() if self.indexed_at else None,
            "chunk_count": len(self.chunks) if self.chunks else 0,
        }


class DocumentChunk(Base):
    """文档块表"""
    __tablename__ = "document_chunks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    metadata = Column(JSON, default={})
    
    # 向量嵌入（1536维度，适用于OpenAI text-embedding-ada-002）
    embedding = Column(Vector(1536), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    document = relationship("Document", back_populates="chunks")
    
    # 唯一约束：每个文档的块索引唯一
    __table_args__ = (
        UniqueConstraint('document_id', 'chunk_index', name='uq_document_chunk'),
    )
    
    def __repr__(self):
        return f"<DocumentChunk(id={self.id}, document_id={self.document_id}, chunk_index={self.chunk_index})>"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "metadata": self.metadata,
            "has_embedding": self.embedding is not None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class QueryHistory(Base):
    """查询历史表"""
    __tablename__ = "query_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    query_text = Column(Text, nullable=False)
    query_embedding = Column(Vector(1536), nullable=True)
    user_id = Column(String(255), index=True)
    session_id = Column(String(255), index=True)
    
    # 查询结果
    results = Column(JSON, default={})
    matched_chunks = Column(ARRAY(Integer), default=[])
    similarity_scores = Column(ARRAY(Float), default=[])
    
    # 性能指标
    execution_time_ms = Column(Integer)
    total_chunks_searched = Column(Integer)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    def __repr__(self):
        return f"<QueryHistory(id={self.id}, user_id='{self.user_id}', query_length={len(self.query_text)})>"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "query_text": self.query_text,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "results": self.results,
            "matched_chunks": self.matched_chunks,
            "similarity_scores": self.similarity_scores,
            "execution_time_ms": self.execution_time_ms,
            "total_chunks_searched": self.total_chunks_searched,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# Pydantic模型（用于API）
from pydantic import BaseModel, Field
from typing import Union


class DocumentCreate(BaseModel):
    """创建文档的请求模型"""
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    file_type: Optional[str] = None
    source_url: Optional[str] = None


class DocumentUpdate(BaseModel):
    """更新文档的请求模型"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    content: Optional[str] = Field(None, min_length=1)
    metadata: Optional[Dict[str, Any]] = None
    source_url: Optional[str] = None


class DocumentResponse(BaseModel):
    """文档响应模型"""
    id: int
    title: str
    content: str
    metadata: Dict[str, Any]
    file_type: Optional[str]
    file_size: Optional[int]
    file_hash: Optional[str]
    source_url: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    indexed_at: Optional[str]
    chunk_count: int = 0
    
    class Config:
        from_attributes = True


class DocumentChunkResponse(BaseModel):
    """文档块响应模型"""
    id: int
    document_id: int
    chunk_index: int
    content: str
    metadata: Dict[str, Any]
    has_embedding: bool
    created_at: Optional[str]
    
    class Config:
        from_attributes = True


class QueryRequest(BaseModel):
    """查询请求模型"""
    query: str = Field(..., min_length=1)
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    similarity_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_results: Optional[int] = Field(None, ge=1, le=100)
    search_type: str = Field(default="semantic", regex="^(semantic|fulltext|hybrid)$")


class SearchResult(BaseModel):
    """搜索结果模型"""
    chunk_id: int
    document_id: int
    document_title: str
    content: str
    similarity_score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class QueryResponse(BaseModel):
    """查询响应模型"""
    query: str
    results: List[SearchResult]
    total_results: int
    execution_time_ms: int
    search_type: str
    request_id: Optional[str] = None