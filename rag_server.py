"""RAG MCP服务器"""
import asyncio
import json
import os
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# 导入RAG服务
from src.core.database import init_database, close_database
from src.services.document_service import document_service
from src.services.embedding_service import embedding_service
from src.services.search_service import search_service
from src.models.rag_models import DocumentCreate, QueryRequest
from src.utils.logging import get_structured_logger

load_dotenv()

# 创建MCP服务器
mcp = FastMCP("RAG-Knowledge-Base")
logger = get_structured_logger(__name__)

# 初始化标志
_initialized = False


async def ensure_initialized():
    """确保服务已初始化"""
    global _initialized
    if not _initialized:
        await init_database()
        await embedding_service.initialize()
        _initialized = True
        logger.info("RAG服务初始化完成")


@mcp.tool()
async def add_document(title: str, content: str, file_type: str = "txt", metadata: dict = None) -> Dict[str, Any]:
    """
    向知识库添加文档
    
    参数:
    title: 文档标题
    content: 文档内容
    file_type: 文件类型 (txt, pdf, docx, md等)
    metadata: 文档元数据 (可选)
    
    返回:
    包含文档ID和处理状态的字典
    """
    await ensure_initialized()
    
    try:
        # 创建文档
        document_data = DocumentCreate(
            title=title,
            content=content,
            file_type=file_type,
            metadata=metadata or {}
        )
        
        document = await document_service.create_document(document_data)
        
        # 异步处理文档（分块和嵌入）
        processing_success = await embedding_service.process_document(document.id)
        
        return {
            "success": True,
            "document_id": document.id,
            "title": document.title,
            "processing_success": processing_success,
            "message": f"文档 '{title}' 已成功添加到知识库"
        }
        
    except Exception as e:
        logger.error("添加文档失败", title=title, error=str(e))
        return {
            "success": False,
            "error": str(e),
            "message": f"添加文档 '{title}' 失败"
        }


@mcp.tool()
async def search_knowledge(
    query: str, 
    search_type: str = "semantic", 
    max_results: int = 5,
    similarity_threshold: float = 0.7
) -> Dict[str, Any]:
    """
    在知识库中搜索相关信息
    
    参数:
    query: 搜索查询
    search_type: 搜索类型 (semantic, fulltext, hybrid)
    max_results: 最大结果数量
    similarity_threshold: 相似度阈值 (仅用于语义搜索)
    
    返回:
    搜索结果列表
    """
    await ensure_initialized()
    
    try:
        # 创建查询请求
        query_request = QueryRequest(
            query=query,
            search_type=search_type,
            max_results=min(max_results, 20),  # 限制最大结果数
            similarity_threshold=similarity_threshold
        )
        
        # 执行搜索
        response = await search_service.search(query_request)
        
        # 格式化结果
        formatted_results = []
        for result in response.results:
            formatted_result = {
                "document_title": result.document_title,
                "content": result.content,
                "similarity_score": round(result.similarity_score, 3),
                "metadata": result.metadata
            }
            formatted_results.append(formatted_result)
        
        return {
            "success": True,
            "query": query,
            "search_type": search_type,
            "total_results": response.total_results,
            "execution_time_ms": response.execution_time_ms,
            "results": formatted_results
        }
        
    except Exception as e:
        logger.error("搜索失败", query=query, error=str(e))
        return {
            "success": False,
            "error": str(e),
            "message": f"搜索查询 '{query}' 失败"
        }


@mcp.tool()
async def get_document_info(document_id: int) -> Dict[str, Any]:
    """
    获取文档信息
    
    参数:
    document_id: 文档ID
    
    返回:
    文档详细信息
    """
    await ensure_initialized()
    
    try:
        document = await document_service.get_document_by_id(document_id)
        
        if not document:
            return {
                "success": False,
                "message": f"未找到ID为 {document_id} 的文档"
            }
        
        return {
            "success": True,
            "document": document.to_dict()
        }
        
    except Exception as e:
        logger.error("获取文档信息失败", document_id=document_id, error=str(e))
        return {
            "success": False,
            "error": str(e),
            "message": f"获取文档 {document_id} 信息失败"
        }


@mcp.tool()
async def list_documents(offset: int = 0, limit: int = 10, search_query: str = None) -> Dict[str, Any]:
    """
    列出知识库中的文档
    
    参数:
    offset: 偏移量
    limit: 限制数量
    search_query: 搜索查询 (可选)
    
    返回:
    文档列表
    """
    await ensure_initialized()
    
    try:
        documents, total_count = await document_service.list_documents(
            offset=offset,
            limit=min(limit, 50),  # 限制最大数量
            search_query=search_query
        )
        
        document_list = []
        for doc in documents:
            doc_info = {
                "id": doc.id,
                "title": doc.title,
                "file_type": doc.file_type,
                "file_size": doc.file_size,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "indexed": doc.indexed_at is not None
            }
            document_list.append(doc_info)
        
        return {
            "success": True,
            "documents": document_list,
            "total_count": total_count,
            "offset": offset,
            "limit": limit
        }
        
    except Exception as e:
        logger.error("列出文档失败", error=str(e))
        return {
            "success": False,
            "error": str(e),
            "message": "列出文档失败"
        }


@mcp.tool()
async def delete_document(document_id: int) -> Dict[str, Any]:
    """
    从知识库删除文档
    
    参数:
    document_id: 文档ID
    
    返回:
    删除操作结果
    """
    await ensure_initialized()
    
    try:
        success = await document_service.delete_document(document_id)
        
        if success:
            return {
                "success": True,
                "message": f"文档 {document_id} 已成功删除"
            }
        else:
            return {
                "success": False,
                "message": f"未找到ID为 {document_id} 的文档"
            }
        
    except Exception as e:
        logger.error("删除文档失败", document_id=document_id, error=str(e))
        return {
            "success": False,
            "error": str(e),
            "message": f"删除文档 {document_id} 失败"
        }


@mcp.tool()
async def get_knowledge_stats() -> Dict[str, Any]:
    """
    获取知识库统计信息
    
    返回:
    知识库统计数据
    """
    await ensure_initialized()
    
    try:
        doc_stats = await document_service.get_document_stats()
        search_stats = await search_service.get_search_stats()
        embedding_stats = await embedding_service.get_embedding_stats()
        
        return {
            "success": True,
            "statistics": {
                "documents": doc_stats.get("documents", {}),
                "chunks": doc_stats.get("chunks", {}),
                "file_types": doc_stats.get("file_type_distribution", {}),
                "search": search_stats,
                "embeddings": embedding_stats,
                "updated_at": doc_stats.get("updated_at")
            }
        }
        
    except Exception as e:
        logger.error("获取统计信息失败", error=str(e))
        return {
            "success": False,
            "error": str(e),
            "message": "获取统计信息失败"
        }


@mcp.tool()
async def reprocess_document(document_id: int) -> Dict[str, Any]:
    """
    重新处理文档（重新分块和嵌入）
    
    参数:
    document_id: 文档ID
    
    返回:
    处理结果
    """
    await ensure_initialized()
    
    try:
        success = await embedding_service.reprocess_document(document_id)
        
        return {
            "success": success,
            "message": f"文档 {document_id} 重新处理{'成功' if success else '失败'}"
        }
        
    except Exception as e:
        logger.error("重新处理文档失败", document_id=document_id, error=str(e))
        return {
            "success": False,
            "error": str(e),
            "message": f"重新处理文档 {document_id} 失败"
        }


@mcp.tool()
async def find_similar_documents(document_id: int, max_results: int = 5) -> Dict[str, Any]:
    """
    查找相似文档
    
    参数:
    document_id: 文档ID
    max_results: 最大结果数量
    
    返回:
    相似文档列表
    """
    await ensure_initialized()
    
    try:
        similar_docs = await search_service.search_similar_documents(
            document_id, 
            min(max_results, 10)
        )
        
        formatted_results = []
        for result in similar_docs:
            formatted_result = {
                "document_id": result.document_id,
                "document_title": result.document_title,
                "similarity_score": round(result.similarity_score, 3),
                "content_preview": result.content[:200] + "..." if len(result.content) > 200 else result.content
            }
            formatted_results.append(formatted_result)
        
        return {
            "success": True,
            "document_id": document_id,
            "similar_documents": formatted_results,
            "total_found": len(formatted_results)
        }
        
    except Exception as e:
        logger.error("查找相似文档失败", document_id=document_id, error=str(e))
        return {
            "success": False,
            "error": str(e),
            "message": f"查找文档 {document_id} 的相似文档失败"
        }


@mcp.tool()
async def health_check() -> Dict[str, Any]:
    """
    RAG系统健康检查
    
    返回:
    系统健康状态
    """
    try:
        await ensure_initialized()
        
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
            "success": True,
            "overall_status": overall_status,
            "services": {
                "document_service": doc_health,
                "embedding_service": embedding_health,
                "search_service": search_health
            }
        }
        
    except Exception as e:
        logger.error("健康检查失败", error=str(e))
        return {
            "success": False,
            "overall_status": "unhealthy",
            "error": str(e)
        }


# 清理函数
async def cleanup():
    """清理资源"""
    try:
        await close_database()
        logger.info("RAG服务清理完成")
    except Exception as e:
        logger.error("清理失败", error=str(e))


# 运行服务器
if __name__ == "__main__":
    import signal
    import sys
    
    def signal_handler(signum, frame):
        logger.info("接收到退出信号，开始清理...")
        asyncio.create_task(cleanup())
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 使用stdio协议运行
    mcp.run(transport="stdio")