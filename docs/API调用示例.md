# API调用示例

本文档提供了MCP生产级客户端API的详细调用示例，包括MCP工具调用和RAG知识库功能。

## 基础信息

### API地址
- **开发环境**：http://localhost:8000
- **生产环境**：https://your-domain.com

### 认证方式
目前版本不需要认证，但建议在生产环境中配置反向代理进行认证。

## 一、MCP工具调用

### 1. 基础查询

#### 发送普通查询
```bash
curl -X POST "http://localhost:8000/query" \
-H "Content-Type: application/json" \
-d '{
  "query": "北京今天的天气如何？",
  "user_id": "user123",
  "session_id": "session456"
}'
```

**响应示例：**
```json
{
  "content": "根据最新的天气信息，北京今天...",
  "tools_used": [
    {
      "tool_name": "weather_tool",
      "parameters": {"location": "北京"},
      "result": "..."
    }
  ],
  "execution_time": 2.5,
  "request_id": "req_123456789",
  "status": "success"
}
```

#### 发送复杂查询
```bash
curl -X POST "http://localhost:8000/query" \
-H "Content-Type: application/json" \
-d '{
  "query": "帮我搜索关于人工智能的最新趋势，并分析其发展前景",
  "user_id": "user123",
  "session_id": "session456",
  "max_tokens": 2000,
  "timeout": 60
}'
```

### 2. 获取可用工具

```bash
curl -X GET "http://localhost:8000/tools"
```

**响应示例：**
```json
{
  "tools": [
    {
      "name": "bing_search",
      "description": "搜索最新的网络信息",
      "parameters": {
        "query": "string",
        "count": "integer"
      }
    },
    {
      "name": "weather_tool",
      "description": "获取天气信息",
      "parameters": {
        "location": "string"
      }
    }
  ],
  "count": 2
}
```

### 3. 系统状态查询

#### 获取服务器状态
```bash
curl -X GET "http://localhost:8000/status"
```

#### 健康检查
```bash
curl -X GET "http://localhost:8000/health"
```

**响应示例：**
```json
{
  "status": "healthy",
  "timestamp": "2024-12-01T10:30:45Z",
  "services": {
    "mcp_connections": {
      "status": "healthy",
      "active_connections": 3,
      "total_servers": 5
    },
    "openai_api": {
      "status": "healthy",
      "response_time": 1.2
    }
  }
}
```

## 二、RAG知识库功能

### 1. 文档管理

#### 创建文档
```bash
curl -X POST "http://localhost:8000/rag/documents" \
-H "Content-Type: application/json" \
-d '{
  "title": "Python开发指南",
  "content": "Python是一种高级编程语言...",
  "file_type": "md",
  "metadata": {
    "author": "张三",
    "category": "技术文档"
  }
}'
```

#### 上传文档文件
```bash
curl -X POST "http://localhost:8000/rag/documents/upload" \
-H "Content-Type: multipart/form-data" \
-F "file=@/path/to/document.pdf" \
-F "title=技术文档" \
-F 'metadata={"author":"李四","category":"参考资料"}'
```

**响应示例：**
```json
{
  "success": true,
  "message": "文档 'Python开发指南' 创建成功",
  "data": {
    "document_id": 123,
    "title": "Python开发指南"
  }
}
```

#### 获取文档列表
```bash
curl -X GET "http://localhost:8000/rag/documents?offset=0&limit=10&search_query=Python"
```

**响应示例：**
```json
{
  "documents": [
    {
      "id": 123,
      "title": "Python开发指南",
      "file_type": "md",
      "created_at": "2024-12-01T10:00:00Z",
      "updated_at": "2024-12-01T10:00:00Z",
      "chunk_count": 15,
      "metadata": {
        "author": "张三",
        "category": "技术文档"
      }
    }
  ],
  "total_count": 1,
  "offset": 0,
  "limit": 10
}
```

#### 获取单个文档
```bash
curl -X GET "http://localhost:8000/rag/documents/123"
```

#### 更新文档
```bash
curl -X PUT "http://localhost:8000/rag/documents/123" \
-H "Content-Type: application/json" \
-d '{
  "title": "Python高级开发指南",
  "content": "更新后的内容...",
  "metadata": {
    "author": "张三",
    "category": "高级技术文档"
  }
}'
```

#### 删除文档
```bash
curl -X DELETE "http://localhost:8000/rag/documents/123"
```

#### 批量删除文档
```bash
curl -X POST "http://localhost:8000/rag/documents/batch-delete" \
-H "Content-Type: application/json" \
-d '{
  "document_ids": [123, 124, 125]
}'
```

### 2. 知识库搜索

#### 基础搜索
```bash
curl -X POST "http://localhost:8000/rag/search" \
-H "Content-Type: application/json" \
-d '{
  "query": "如何使用Python进行数据分析？",
  "max_results": 5,
  "similarity_threshold": 0.7
}'
```

**响应示例：**
```json
{
  "query": "如何使用Python进行数据分析？",
  "results": [
    {
      "document_id": 123,
      "document_title": "Python数据分析教程",
      "chunk_id": 456,
      "content": "Python在数据分析领域有着广泛的应用...",
      "similarity_score": 0.92,
      "metadata": {
        "author": "王五",
        "category": "数据分析"
      }
    }
  ],
  "total_results": 1,
  "execution_time": 0.5,
  "request_id": "search_789"
}
```

#### 高级搜索
```bash
curl -X POST "http://localhost:8000/rag/search" \
-H "Content-Type: application/json" \
-d '{
  "query": "机器学习算法比较",
  "max_results": 10,
  "similarity_threshold": 0.6,
  "filter_metadata": {
    "category": "机器学习"
  },
  "include_metadata": true,
  "return_embeddings": false
}'
```

#### 获取搜索建议
```bash
curl -X GET "http://localhost:8000/rag/search/suggestions?query=Python&limit=5"
```

**响应示例：**
```json
{
  "suggestions": [
    "Python数据分析",
    "Python机器学习",
    "Python Web开发",
    "Python爬虫",
    "Python自动化"
  ]
}
```

#### 查找相似文档
```bash
curl -X GET "http://localhost:8000/rag/documents/123/similar?max_results=5"
```

### 3. 文档管理

#### 重新处理文档
```bash
curl -X POST "http://localhost:8000/rag/documents/123/reprocess"
```

#### 获取统计信息
```bash
curl -X GET "http://localhost:8000/rag/stats"
```

**响应示例：**
```json
{
  "documents": {
    "total_count": 150,
    "total_size": 52428800,
    "average_size": 349525
  },
  "chunks": {
    "total_count": 1250,
    "average_per_document": 8.3
  },
  "file_type_distribution": {
    "pdf": 45,
    "md": 35,
    "txt": 40,
    "docx": 30
  },
  "search_stats": {
    "total_searches": 1250,
    "average_response_time": 0.45
  },
  "embedding_stats": {
    "total_embeddings": 1250,
    "embedding_model": "text-embedding-ada-002"
  },
  "updated_at": "2024-12-01T12:00:00Z"
}
```

### 4. 健康检查

#### RAG服务健康检查
```bash
curl -X GET "http://localhost:8000/rag/health"
```

## 三、Python客户端示例

### 1. 基础客户端类

```python
import httpx
import asyncio
from typing import Dict, Any, Optional, List

class MCPClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient()
    
    async def query(self, query: str, user_id: str = None, session_id: str = None, 
                   max_tokens: int = None, timeout: int = None) -> Dict[str, Any]:
        """发送查询请求"""
        data = {"query": query}
        if user_id:
            data["user_id"] = user_id
        if session_id:
            data["session_id"] = session_id
        if max_tokens:
            data["max_tokens"] = max_tokens
        if timeout:
            data["timeout"] = timeout
        
        response = await self.client.post(f"{self.base_url}/query", json=data)
        response.raise_for_status()
        return response.json()
    
    async def get_tools(self) -> Dict[str, Any]:
        """获取可用工具"""
        response = await self.client.get(f"{self.base_url}/tools")
        response.raise_for_status()
        return response.json()
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        response = await self.client.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()
    
    async def close(self):
        """关闭客户端"""
        await self.client.aclose()
```

### 2. RAG客户端类

```python
class RAGClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient()
    
    async def create_document(self, title: str, content: str, 
                            file_type: str = "txt", metadata: Dict = None) -> Dict[str, Any]:
        """创建文档"""
        data = {
            "title": title,
            "content": content,
            "file_type": file_type,
            "metadata": metadata or {}
        }
        response = await self.client.post(f"{self.base_url}/rag/documents", json=data)
        response.raise_for_status()
        return response.json()
    
    async def upload_document(self, file_path: str, title: str, 
                            metadata: Dict = None) -> Dict[str, Any]:
        """上传文档文件"""
        with open(file_path, 'rb') as f:
            files = {'file': f}
            data = {
                'title': title,
                'metadata': json.dumps(metadata or {})
            }
            response = await self.client.post(
                f"{self.base_url}/rag/documents/upload",
                files=files,
                data=data
            )
        response.raise_for_status()
        return response.json()
    
    async def search(self, query: str, max_results: int = 10, 
                    similarity_threshold: float = 0.7) -> Dict[str, Any]:
        """搜索文档"""
        data = {
            "query": query,
            "max_results": max_results,
            "similarity_threshold": similarity_threshold
        }
        response = await self.client.post(f"{self.base_url}/rag/search", json=data)
        response.raise_for_status()
        return response.json()
    
    async def list_documents(self, offset: int = 0, limit: int = 20) -> Dict[str, Any]:
        """获取文档列表"""
        params = {"offset": offset, "limit": limit}
        response = await self.client.get(f"{self.base_url}/rag/documents", params=params)
        response.raise_for_status()
        return response.json()
    
    async def delete_document(self, document_id: int) -> Dict[str, Any]:
        """删除文档"""
        response = await self.client.delete(f"{self.base_url}/rag/documents/{document_id}")
        response.raise_for_status()
        return response.json()
    
    async def close(self):
        """关闭客户端"""
        await self.client.aclose()
```

### 3. 使用示例

```python
async def main():
    # 创建客户端
    mcp_client = MCPClient()
    rag_client = RAGClient()
    
    try:
        # 1. 健康检查
        health = await mcp_client.health_check()
        print(f"服务状态: {health['status']}")
        
        # 2. 获取可用工具
        tools = await mcp_client.get_tools()
        print(f"可用工具数量: {tools['count']}")
        
        # 3. 发送查询
        response = await mcp_client.query(
            query="今天的天气如何？",
            user_id="user123",
            session_id="session456"
        )
        print(f"查询结果: {response['content']}")
        
        # 4. 创建文档
        doc_response = await rag_client.create_document(
            title="测试文档",
            content="这是一个测试文档的内容",
            file_type="txt",
            metadata={"author": "测试用户"}
        )
        print(f"文档创建成功: {doc_response['data']['document_id']}")
        
        # 5. 搜索文档
        search_response = await rag_client.search(
            query="测试",
            max_results=5
        )
        print(f"搜索到 {search_response['total_results']} 个结果")
        
        # 6. 获取文档列表
        docs = await rag_client.list_documents(limit=10)
        print(f"文档总数: {docs['total_count']}")
        
    finally:
        await mcp_client.close()
        await rag_client.close()

# 运行示例
if __name__ == "__main__":
    asyncio.run(main())
```

## 四、JavaScript客户端示例

### 1. 基础客户端

```javascript
class MCPClient {
    constructor(baseUrl = 'http://localhost:8000') {
        this.baseUrl = baseUrl;
    }
    
    async query(query, options = {}) {
        const response = await fetch(`${this.baseUrl}/query`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query,
                ...options
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    }
    
    async getTools() {
        const response = await fetch(`${this.baseUrl}/tools`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
    }
    
    async healthCheck() {
        const response = await fetch(`${this.baseUrl}/health`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
    }
}

// 使用示例
async function example() {
    const client = new MCPClient();
    
    try {
        // 健康检查
        const health = await client.healthCheck();
        console.log('服务状态:', health.status);
        
        // 发送查询
        const response = await client.query('北京今天的天气如何？', {
            user_id: 'user123',
            session_id: 'session456'
        });
        console.log('查询结果:', response.content);
        
    } catch (error) {
        console.error('错误:', error);
    }
}
```

## 五、错误处理

### 常见错误码
- **400 Bad Request**：请求参数错误
- **401 Unauthorized**：未授权访问
- **404 Not Found**：资源不存在
- **413 Payload Too Large**：文件过大
- **429 Too Many Requests**：请求过于频繁
- **500 Internal Server Error**：服务器内部错误
- **503 Service Unavailable**：服务不可用

### 错误响应格式
```json
{
  "detail": "错误描述",
  "error": "具体错误信息",
  "path": "/api/endpoint"
}
```

## 六、性能优化建议

### 1. 并发控制
- 控制并发请求数量，避免过载
- 使用连接池复用连接
- 实现请求队列和限流

### 2. 缓存策略
- 缓存频繁查询的结果
- 使用Redis或内存缓存
- 设置合理的缓存过期时间

### 3. 错误重试
- 实现指数退避重试
- 区分可重试和不可重试错误
- 设置最大重试次数

### 4. 监控和日志
- 记录请求响应时间
- 监控错误率和成功率
- 设置告警阈值

---

更多详细信息请参考：
- [项目说明](项目说明.md)
- [部署指南](部署指南.md)
- [AI模型配置](AI模型配置.md)