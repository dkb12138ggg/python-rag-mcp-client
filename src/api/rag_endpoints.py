"""RAG相关API端点"""
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.core.database import init_database
from src.services.document_service import document_service
from src.services.embedding_service import embedding_service
from src.services.search_service import search_service
from src.models.rag_models import (
    DocumentCreate, DocumentUpdate, DocumentResponse, 
    QueryRequest, QueryResponse, SearchResult
)
from src.utils.logging import get_structured_logger
from src.config.settings import settings

logger = get_structured_logger(__name__)

# 创建路由器
rag_router = APIRouter(prefix="/rag", tags=["RAG"])

# 初始化标志
_rag_initialized = False


async def ensure_rag_initialized():
    """确保RAG服务已初始化"""
    global _rag_initialized
    if not _rag_initialized:
        await init_database()
        await embedding_service.initialize()
        _rag_initialized = True
        logger.info("RAG API服务初始化完成")


# 请求模型
class FileUploadRequest(BaseModel):
    """文件上传请求"""
    title: str = Field(..., min_length=1, max_length=255)
    file_type: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BulkDeleteRequest(BaseModel):
    """批量删除请求"""
    document_ids: List[int] = Field(..., min_items=1, max_items=50)


# 响应模型
class ApiResponse(BaseModel):
    """通用API响应"""
    success: bool
    message: Optional[str] = None
    data: Optional[Any] = None
    error: Optional[str] = None


class DocumentListResponse(BaseModel):
    """文档列表响应"""
    documents: List[DocumentResponse]
    total_count: int
    offset: int
    limit: int


class StatsResponse(BaseModel):
    """统计信息响应"""
    documents: Dict[str, Any]
    chunks: Dict[str, Any]
    file_type_distribution: Dict[str, int]
    search_stats: Dict[str, Any]
    embedding_stats: Dict[str, Any]
    updated_at: str


# 文档管理端点
@rag_router.post("/documents", response_model=ApiResponse)
async def create_document(document: DocumentCreate):
    """创建新文档"""
    await ensure_rag_initialized()
    
    try:
        # 创建文档
        created_doc = await document_service.create_document(document)
        
        # 异步处理文档（分块和嵌入）
        asyncio.create_task(embedding_service.process_document(created_doc.id))
        
        return ApiResponse(
            success=True,
            message=f"文档 '{document.title}' 创建成功",
            data={"document_id": created_doc.id, "title": created_doc.title}
        )
        
    except Exception as e:
        logger.error("创建文档失败", title=document.title, error=str(e))
        raise HTTPException(status_code=500, detail=f"创建文档失败: {str(e)}")


@rag_router.post("/documents/upload", response_model=ApiResponse)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    metadata: str = Form("{}"),
):
    """上传文档文件"""
    await ensure_rag_initialized()
    
    try:
        # 检查文件大小
        file_content = await file.read()
        if len(file_content) > settings.rag.max_file_size:
            raise HTTPException(
                status_code=413, 
                detail=f"文件大小超出限制 ({settings.rag.max_file_size} bytes)"
            )
        
        # 检查文件类型
        file_type = file.filename.split('.')[-1].lower() if file.filename else "unknown"
        if file_type not in settings.rag.supported_file_types:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型: {file_type}"
            )
        
        # 解析元数据
        import json
        try:
            parsed_metadata = json.loads(metadata)
        except json.JSONDecodeError:
            parsed_metadata = {}
        
        # 创建文档
        content = file_content.decode('utf-8', errors='ignore')
        document_data = DocumentCreate(
            title=title,
            content=content,
            file_type=file_type,
            metadata=parsed_metadata
        )
        
        created_doc = await document_service.create_document(document_data, file_content)
        
        # 异步处理文档
        asyncio.create_task(embedding_service.process_document(created_doc.id))
        
        return ApiResponse(
            success=True,
            message=f"文件 '{file.filename}' 上传成功",
            data={
                "document_id": created_doc.id,
                "title": created_doc.title,
                "file_size": len(file_content)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("上传文档失败", filename=file.filename, error=str(e))
        raise HTTPException(status_code=500, detail=f"上传文档失败: {str(e)}")


@rag_router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search_query: Optional[str] = Query(None),
    file_type: Optional[str] = Query(None),
    order_by: str = Query("created_at"),
    order_direction: str = Query("desc", regex="^(asc|desc)$")
):
    """获取文档列表"""
    await ensure_rag_initialized()
    
    try:
        documents, total_count = await document_service.list_documents(
            offset=offset,
            limit=limit,
            search_query=search_query,
            file_type=file_type,
            order_by=order_by,
            order_direction=order_direction
        )
        
        document_responses = [DocumentResponse.from_orm(doc) for doc in documents]
        
        return DocumentListResponse(
            documents=document_responses,
            total_count=total_count,
            offset=offset,
            limit=limit
        )
        
    except Exception as e:
        logger.error("获取文档列表失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取文档列表失败: {str(e)}")


@rag_router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: int):
    """获取单个文档"""
    await ensure_rag_initialized()
    
    try:
        document = await document_service.get_document_by_id(document_id)
        if not document:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        return DocumentResponse.from_orm(document)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取文档失败", document_id=document_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"获取文档失败: {str(e)}")


@rag_router.put("/documents/{document_id}", response_model=ApiResponse)
async def update_document(document_id: int, document_data: DocumentUpdate):
    """更新文档"""
    await ensure_rag_initialized()
    
    try:
        updated_doc = await document_service.update_document(document_id, document_data)
        if not updated_doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        # 如果内容发生变化，重新处理文档
        if document_data.content is not None:
            asyncio.create_task(embedding_service.reprocess_document(document_id))
        
        return ApiResponse(
            success=True,
            message=f"文档 {document_id} 更新成功",
            data={"document_id": updated_doc.id, "title": updated_doc.title}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("更新文档失败", document_id=document_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"更新文档失败: {str(e)}")


@rag_router.delete("/documents/{document_id}", response_model=ApiResponse)
async def delete_document(document_id: int):
    """删除文档"""
    await ensure_rag_initialized()
    
    try:
        success = await document_service.delete_document(document_id)
        if not success:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        return ApiResponse(
            success=True,
            message=f"文档 {document_id} 删除成功"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("删除文档失败", document_id=document_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"删除文档失败: {str(e)}")


@rag_router.post("/documents/batch-delete", response_model=ApiResponse)
async def batch_delete_documents(request: BulkDeleteRequest):
    """批量删除文档"""
    await ensure_rag_initialized()
    
    try:
        deleted_count = 0
        failed_ids = []
        
        for doc_id in request.document_ids:
            try:
                success = await document_service.delete_document(doc_id)
                if success:
                    deleted_count += 1
                else:
                    failed_ids.append(doc_id)
            except Exception as e:
                logger.warning(f"删除文档 {doc_id} 失败", error=str(e))
                failed_ids.append(doc_id)
        
        message = f"成功删除 {deleted_count} 个文档"
        if failed_ids:
            message += f"，失败 {len(failed_ids)} 个文档 (IDs: {failed_ids})"
        
        return ApiResponse(
            success=True,
            message=message,
            data={"deleted_count": deleted_count, "failed_ids": failed_ids}
        )
        
    except Exception as e:
        logger.error("批量删除文档失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"批量删除文档失败: {str(e)}")


# 搜索端点
@rag_router.post("/search", response_model=QueryResponse)
async def search_documents(query_request: QueryRequest):
    """搜索文档"""
    await ensure_rag_initialized()
    
    try:
        response = await search_service.search(query_request)
        return response
        
    except Exception as e:
        logger.error("搜索失败", query=query_request.query, error=str(e))
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@rag_router.get("/search/suggestions")
async def get_search_suggestions(
    query: str = Query(..., min_length=1),
    limit: int = Query(5, ge=1, le=20)
):
    """获取搜索建议"""
    await ensure_rag_initialized()
    
    try:
        suggestions = await search_service.get_search_suggestions(query, limit)
        return {"suggestions": suggestions}
        
    except Exception as e:
        logger.error("获取搜索建议失败", query=query, error=str(e))
        raise HTTPException(status_code=500, detail=f"获取搜索建议失败: {str(e)}")


@rag_router.get("/documents/{document_id}/similar")
async def find_similar_documents(
    document_id: int,
    max_results: int = Query(10, ge=1, le=50)
):
    """查找相似文档"""
    await ensure_rag_initialized()
    
    try:
        similar_docs = await search_service.search_similar_documents(document_id, max_results)
        
        return {
            "document_id": document_id,
            "similar_documents": [
                {
                    "document_id": result.document_id,
                    "document_title": result.document_title,
                    "similarity_score": round(result.similarity_score, 3),
                    "content_preview": result.content[:200] + "..." if len(result.content) > 200 else result.content
                }
                for result in similar_docs
            ],
            "total_found": len(similar_docs)
        }
        
    except Exception as e:
        logger.error("查找相似文档失败", document_id=document_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"查找相似文档失败: {str(e)}")


# 管理端点
@rag_router.post("/documents/{document_id}/reprocess", response_model=ApiResponse)
async def reprocess_document(document_id: int):
    """重新处理文档"""
    await ensure_rag_initialized()
    
    try:
        success = await embedding_service.reprocess_document(document_id)
        
        return ApiResponse(
            success=success,
            message=f"文档 {document_id} 重新处理{'成功' if success else '失败'}"
        )
        
    except Exception as e:
        logger.error("重新处理文档失败", document_id=document_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"重新处理文档失败: {str(e)}")


@rag_router.get("/stats", response_model=StatsResponse)
async def get_rag_stats():
    """获取RAG统计信息"""
    await ensure_rag_initialized()
    
    try:
        doc_stats = await document_service.get_document_stats()
        search_stats = await search_service.get_search_stats()
        embedding_stats = await embedding_service.get_embedding_stats()
        
        return StatsResponse(
            documents=doc_stats.get("documents", {}),
            chunks=doc_stats.get("chunks", {}),
            file_type_distribution=doc_stats.get("file_type_distribution", {}),
            search_stats=search_stats,
            embedding_stats=embedding_stats,
            updated_at=doc_stats.get("updated_at", datetime.utcnow().isoformat())
        )
        
    except Exception as e:
        logger.error("获取RAG统计失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取RAG统计失败: {str(e)}")


@rag_router.get("/health")
async def rag_health_check():
    """RAG健康检查"""
    try:
        await ensure_rag_initialized()
        
        # 检查各个服务
        doc_health = await document_service.health_check()
        embedding_health = await embedding_service.health_check()
        search_health = await search_service.health_check()
        
        overall_status = "healthy"
        if (doc_health.get("status") != "healthy" or 
            embedding_health.get("status") != "healthy" or 
            search_health.get("status") != "healthy"):
            overall_status = "unhealthy"
        
        return {
            "status": overall_status,
            "services": {
                "document_service": doc_health,
                "embedding_service": embedding_health,
                "search_service": search_health
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error("RAG健康检查失败", error=str(e))
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )