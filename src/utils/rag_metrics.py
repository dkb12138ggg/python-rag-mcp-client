"""RAG相关的监控指标"""
from prometheus_client import Counter, Histogram, Gauge, Summary
from typing import Dict, Any
import time

# RAG文档相关指标
RAG_DOCUMENTS_TOTAL = Gauge('rag_documents_total', 'Total number of documents in RAG system')
RAG_DOCUMENTS_INDEXED = Gauge('rag_documents_indexed', 'Number of indexed documents')
RAG_CHUNKS_TOTAL = Gauge('rag_chunks_total', 'Total number of document chunks')
RAG_CHUNKS_EMBEDDED = Gauge('rag_chunks_embedded', 'Number of embedded chunks')

# RAG搜索相关指标
RAG_SEARCH_REQUESTS_TOTAL = Counter('rag_search_requests_total', 'Total search requests', ['search_type', 'status'])
RAG_SEARCH_DURATION = Histogram('rag_search_duration_seconds', 'Search request duration', ['search_type'])
RAG_SEARCH_RESULTS_COUNT = Histogram('rag_search_results_count', 'Number of search results returned', ['search_type'])

# RAG嵌入相关指标
RAG_EMBEDDING_REQUESTS_TOTAL = Counter('rag_embedding_requests_total', 'Total embedding requests', ['status'])
RAG_EMBEDDING_DURATION = Histogram('rag_embedding_duration_seconds', 'Embedding creation duration')
RAG_EMBEDDING_TOKENS_TOTAL = Counter('rag_embedding_tokens_total', 'Total tokens processed for embeddings')

# RAG文档处理指标
RAG_DOCUMENT_PROCESSING_TOTAL = Counter('rag_document_processing_total', 'Total document processing requests', ['status'])
RAG_DOCUMENT_PROCESSING_DURATION = Histogram('rag_document_processing_duration_seconds', 'Document processing duration')
RAG_DOCUMENT_SIZE_BYTES = Histogram('rag_document_size_bytes', 'Document size in bytes', buckets=[1024, 10240, 102400, 1048576, 10485760])

# RAG数据库相关指标
RAG_DB_CONNECTIONS_ACTIVE = Gauge('rag_db_connections_active', 'Active database connections')
RAG_DB_QUERY_DURATION = Histogram('rag_db_query_duration_seconds', 'Database query duration', ['operation'])
RAG_DB_OPERATIONS_TOTAL = Counter('rag_db_operations_total', 'Total database operations', ['operation', 'status'])

# RAG缓存指标
RAG_CACHE_HITS_TOTAL = Counter('rag_cache_hits_total', 'Total cache hits', ['cache_type'])
RAG_CACHE_MISSES_TOTAL = Counter('rag_cache_misses_total', 'Total cache misses', ['cache_type'])
RAG_CACHE_SIZE = Gauge('rag_cache_size', 'Current cache size', ['cache_type'])

# RAG错误指标
RAG_ERRORS_TOTAL = Counter('rag_errors_total', 'Total RAG errors', ['service', 'error_type'])


class RAGMetricsCollector:
    """RAG指标收集器"""
    
    def __init__(self):
        self._search_start_times = {}
        self._processing_start_times = {}
    
    def record_search_start(self, request_id: str, search_type: str) -> None:
        """记录搜索开始"""
        self._search_start_times[request_id] = {
            'start_time': time.time(),
            'search_type': search_type
        }
    
    def record_search_complete(self, request_id: str, results_count: int, success: bool = True) -> None:
        """记录搜索完成"""
        if request_id not in self._search_start_times:
            return
        
        start_info = self._search_start_times.pop(request_id)
        duration = time.time() - start_info['start_time']
        search_type = start_info['search_type']
        
        # 记录指标
        RAG_SEARCH_DURATION.labels(search_type=search_type).observe(duration)
        RAG_SEARCH_REQUESTS_TOTAL.labels(
            search_type=search_type, 
            status='success' if success else 'error'
        ).inc()
        RAG_SEARCH_RESULTS_COUNT.labels(search_type=search_type).observe(results_count)
    
    def record_search_error(self, request_id: str, error_type: str) -> None:
        """记录搜索错误"""
        if request_id in self._search_start_times:
            start_info = self._search_start_times.pop(request_id)
            search_type = start_info['search_type']
            RAG_SEARCH_REQUESTS_TOTAL.labels(search_type=search_type, status='error').inc()
        
        RAG_ERRORS_TOTAL.labels(service='search', error_type=error_type).inc()
    
    def record_document_processing_start(self, document_id: int) -> None:
        """记录文档处理开始"""
        self._processing_start_times[document_id] = time.time()
    
    def record_document_processing_complete(self, document_id: int, success: bool = True) -> None:
        """记录文档处理完成"""
        if document_id not in self._processing_start_times:
            return
        
        start_time = self._processing_start_times.pop(document_id)
        duration = time.time() - start_time
        
        RAG_DOCUMENT_PROCESSING_DURATION.observe(duration)
        RAG_DOCUMENT_PROCESSING_TOTAL.labels(
            status='success' if success else 'error'
        ).inc()
    
    def record_document_size(self, size_bytes: int) -> None:
        """记录文档大小"""
        RAG_DOCUMENT_SIZE_BYTES.observe(size_bytes)
    
    def record_embedding_request(self, token_count: int, duration: float, success: bool = True) -> None:
        """记录嵌入请求"""
        RAG_EMBEDDING_REQUESTS_TOTAL.labels(
            status='success' if success else 'error'
        ).inc()
        RAG_EMBEDDING_DURATION.observe(duration)
        if success:
            RAG_EMBEDDING_TOKENS_TOTAL.inc(token_count)
    
    def record_db_operation(self, operation: str, duration: float, success: bool = True) -> None:
        """记录数据库操作"""
        RAG_DB_QUERY_DURATION.labels(operation=operation).observe(duration)
        RAG_DB_OPERATIONS_TOTAL.labels(
            operation=operation,
            status='success' if success else 'error'
        ).inc()
    
    def record_cache_hit(self, cache_type: str) -> None:
        """记录缓存命中"""
        RAG_CACHE_HITS_TOTAL.labels(cache_type=cache_type).inc()
    
    def record_cache_miss(self, cache_type: str) -> None:
        """记录缓存未命中"""
        RAG_CACHE_MISSES_TOTAL.labels(cache_type=cache_type).inc()
    
    def update_document_stats(self, stats: Dict[str, Any]) -> None:
        """更新文档统计"""
        if 'documents' in stats:
            doc_stats = stats['documents']
            RAG_DOCUMENTS_TOTAL.set(doc_stats.get('total', 0))
            RAG_DOCUMENTS_INDEXED.set(doc_stats.get('indexed', 0))
        
        if 'chunks' in stats:
            chunk_stats = stats['chunks']
            RAG_CHUNKS_TOTAL.set(chunk_stats.get('total', 0))
            RAG_CHUNKS_EMBEDDED.set(chunk_stats.get('embedded', 0))
    
    def update_db_connections(self, active_connections: int) -> None:
        """更新数据库连接数"""
        RAG_DB_CONNECTIONS_ACTIVE.set(active_connections)
    
    def update_cache_size(self, cache_type: str, size: int) -> None:
        """更新缓存大小"""
        RAG_CACHE_SIZE.labels(cache_type=cache_type).set(size)
    
    def record_error(self, service: str, error_type: str) -> None:
        """记录错误"""
        RAG_ERRORS_TOTAL.labels(service=service, error_type=error_type).inc()


# 全局指标收集器实例
rag_metrics = RAGMetricsCollector()