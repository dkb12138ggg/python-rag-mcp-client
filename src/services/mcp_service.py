"""生产级MCP服务"""
import json
import asyncio
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from openai import AsyncOpenAI

from src.core.connection_pool import MCPConnectionPool, ConnectionInfo
from src.config.settings import settings
from src.utils.logging import get_structured_logger

logger = get_structured_logger(__name__)


@dataclass
class QueryRequest:
    """查询请求"""
    query: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    max_tokens: Optional[int] = None
    timeout: Optional[int] = None


@dataclass
class QueryResponse:
    """查询响应"""
    content: str
    tools_used: List[Dict[str, Any]]
    execution_time: float
    request_id: str
    status: str = "success"
    error: Optional[str] = None


class MCPService:
    """生产级MCP服务"""
    
    def __init__(self):
        self.connection_pool = MCPConnectionPool()
        self.openai_client: Optional[AsyncOpenAI] = None
        self._request_counter = 0
        self._concurrent_requests = 0
        self._max_concurrent = settings.api.max_concurrent_requests
    
    async def initialize(self) -> None:
        """初始化服务"""
        logger.info("初始化MCP服务")
        
        # 初始化OpenAI客户端
        self.openai_client = AsyncOpenAI(
            api_key=settings.openai.api_key,
            base_url=settings.openai.base_url,
            timeout=settings.openai.timeout
        )
        
        # 初始化连接池
        await self.connection_pool.initialize()
        
        logger.info("MCP服务初始化完成")
    
    async def process_query(self, request: QueryRequest) -> QueryResponse:
        """处理查询请求"""
        import time
        start_time = time.time()
        
        # 并发控制
        if self._concurrent_requests >= self._max_concurrent:
            raise Exception(f"超过最大并发请求数限制: {self._max_concurrent}")
        
        self._concurrent_requests += 1
        self._request_counter += 1
        request_id = f"req_{self._request_counter}_{start_time}"
        
        try:
            logger.info(
                "开始处理查询",
                request_id=request_id,
                user_id=request.user_id,
                query_length=len(request.query)
            )
            
            # 检查服务状态
            if not self.connection_pool.pools:
                raise Exception("没有可用的MCP服务器连接")
            
            # 检查是否是RAG相关查询，如果是则优先使用RAG搜索
            rag_context = await self._try_rag_search(request.query)
            
            # 构建消息
            if rag_context:
                # 包含RAG上下文的消息
                context_message = f"基于知识库搜索到的相关信息:\n{rag_context}\n\n用户问题: {request.query}"
                messages = [{"role": "user", "content": context_message}]
                logger.info("使用RAG上下文增强查询", context_length=len(rag_context))
            else:
                messages = [{"role": "user", "content": request.query}]
            
            # 获取所有可用工具
            available_tools = await self.connection_pool.get_all_tools()
            if not available_tools:
                return QueryResponse(
                    content="错误: 没有可用的工具",
                    tools_used=[],
                    execution_time=time.time() - start_time,
                    request_id=request_id,
                    status="error",
                    error="no_tools_available"
                )
            
            # 调用OpenAI API
            max_tokens = request.max_tokens or settings.openai.max_tokens
            completion = await self.openai_client.chat.completions.create(
                model=settings.openai.model,
                max_tokens=max_tokens,
                messages=messages,
                tools=available_tools,
                timeout=request.timeout or settings.openai.timeout
            )
            
            # 处理响应
            response = await self._process_completion_response(
                completion, messages, available_tools, request_id
            )
            
            response.execution_time = time.time() - start_time
            response.request_id = request_id
            
            logger.info(
                "查询处理完成",
                request_id=request_id,
                execution_time=response.execution_time,
                tools_used_count=len(response.tools_used)
            )
            
            return response
            
        except Exception as e:
            logger.error(
                "查询处理失败",
                request_id=request_id,
                error=str(e),
                execution_time=time.time() - start_time
            )
            return QueryResponse(
                content=f"处理查询时发生错误: {str(e)}",
                tools_used=[],
                execution_time=time.time() - start_time,
                request_id=request_id,
                status="error",
                error=str(e)
            )
        finally:
            self._concurrent_requests -= 1
    
    async def _process_completion_response(
        self,
        completion: Any,
        messages: List[Dict[str, Any]],
        available_tools: List[Dict[str, Any]],
        request_id: str
    ) -> QueryResponse:
        """处理OpenAI完成响应"""
        tools_used = []
        final_content = []
        
        assistant_message = completion.choices[0].message
        
        # 处理工具调用
        if assistant_message.tool_calls:
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)
                
                logger.debug(
                    "执行工具调用",
                    request_id=request_id,
                    tool_name=tool_name,
                    tool_args=tool_args
                )
                
                # 找到对应的工具和服务器
                tool_info = None
                for tool in available_tools:
                    if tool["function"]["name"] == tool_name:
                        tool_info = tool
                        break
                
                if tool_info:
                    server_name = tool_info["server_name"]
                    original_name = tool_info["original_name"]
                    
                    try:
                        # 执行工具调用
                        result = await self._execute_tool_call(
                            server_name, original_name, tool_args, request_id
                        )
                        
                        tools_used.append({
                            "tool_name": original_name,
                            "server_name": server_name,
                            "arguments": tool_args,
                            "result": result.content[0].text if result.content else "No content",
                            "status": "success"
                        })
                        
                        # 将工具调用结果添加到消息历史
                        messages.extend([
                            {"role": "assistant", "content": None, "tool_calls": [tool_call]},
                            {"role": "tool", "tool_call_id": tool_call.id, 
                             "content": result.content[0].text if result.content else "No content"}
                        ])
                        
                        # 获取工具调用后的后续响应
                        follow_up_completion = await self.openai_client.chat.completions.create(
                            model=settings.openai.model,
                            max_tokens=settings.openai.max_tokens,
                            messages=messages,
                        )
                        
                        follow_up_content = follow_up_completion.choices[0].message.content
                        if follow_up_content:
                            final_content.append(str(follow_up_content))
                        
                    except Exception as e:
                        error_msg = f"工具调用失败: {str(e)}"
                        logger.error(
                            "工具调用执行失败",
                            request_id=request_id,
                            tool_name=original_name,
                            server_name=server_name,
                            error=str(e)
                        )
                        
                        tools_used.append({
                            "tool_name": original_name,
                            "server_name": server_name,
                            "arguments": tool_args,
                            "result": error_msg,
                            "status": "error",
                            "error": str(e)
                        })
                        
                        final_content.append(error_msg)
                else:
                    error_msg = f"未找到工具: {tool_name}"
                    logger.warning("工具未找到", request_id=request_id, tool_name=tool_name)
                    final_content.append(error_msg)
        else:
            # 无工具调用时，直接返回助手消息内容
            content = assistant_message.content
            final_content.append(str(content) if content else "")
        
        return QueryResponse(
            content="\n".join(final_content),
            tools_used=tools_used,
            execution_time=0,  # 将在上层设置
            request_id=request_id
        )
    
    async def _execute_tool_call(
        self,
        server_name: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        request_id: str
    ) -> Any:
        """执行工具调用"""
        connection = await self.connection_pool.get_connection(server_name)
        if not connection:
            raise Exception(f"无法获取服务器 {server_name} 的连接")
        
        try:
            result = await connection.session.call_tool(tool_name, tool_args)
            await self.connection_pool.return_connection(server_name, connection)
            return result
        except Exception as e:
            await self.connection_pool.return_connection(server_name, connection, error=e)
            raise
    
    async def _try_rag_search(self, query: str) -> Optional[str]:
        """尝试使用RAG搜索获取相关上下文"""
        try:
            # 检查是否有RAG服务器可用
            if "rag-knowledge-base" not in self.connection_pool.pools:
                return None
            
            # 获取RAG连接
            connection = await self.connection_pool.get_connection("rag-knowledge-base")
            if not connection:
                return None
            
            try:
                # 调用RAG搜索工具
                result = await connection.session.call_tool("search_knowledge", {
                    "query": query,
                    "search_type": "semantic",
                    "max_results": 3,  # 限制结果数量以避免上下文过长
                    "similarity_threshold": 0.7
                })
                
                await self.connection_pool.return_connection("rag-knowledge-base", connection)
                
                # 解析搜索结果
                if result.content and len(result.content) > 0:
                    search_data = json.loads(result.content[0].text) if result.content[0].text else {}
                    
                    if search_data.get("success") and search_data.get("results"):
                        # 构建上下文字符串
                        context_parts = []
                        for result_item in search_data["results"][:3]:  # 最多3个结果
                            title = result_item.get("document_title", "未知文档")
                            content = result_item.get("content", "")[:500]  # 截断过长内容
                            score = result_item.get("similarity_score", 0)
                            
                            context_parts.append(f"文档: {title} (相似度: {score:.2f})\n内容: {content}")
                        
                        return "\n\n".join(context_parts)
                
                return None
                
            except Exception as e:
                await self.connection_pool.return_connection("rag-knowledge-base", connection, error=e)
                logger.warning("RAG搜索失败", error=str(e))
                return None
                
        except Exception as e:
            logger.warning("尝试RAG搜索时出错", error=str(e))
            return None
    
    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """获取可用工具列表"""
        return await self.connection_pool.get_all_tools()
    
    async def get_server_status(self) -> Dict[str, Any]:
        """获取服务器状态"""
        return {
            "servers": list(self.connection_pool.server_configs.keys()),
            "connection_pool_metrics": self.connection_pool.get_metrics(),
            "concurrent_requests": self._concurrent_requests,
            "total_requests": self._request_counter
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            # 检查连接池状态
            metrics = self.connection_pool.get_metrics()
            
            # 检查OpenAI连接
            openai_status = "healthy"
            try:
                # 简单的API测试
                test_messages = [{"role": "user", "content": "test"}]
                await self.openai_client.chat.completions.create(
                    model=settings.openai.model,
                    max_tokens=1,
                    messages=test_messages
                )
            except Exception as e:
                openai_status = f"unhealthy: {str(e)}"
            
            return {
                "status": "healthy" if metrics["active_connections"] > 0 else "unhealthy",
                "connection_pool": metrics,
                "openai_status": openai_status,
                "concurrent_requests": self._concurrent_requests,
                "total_requests": self._request_counter
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def shutdown(self) -> None:
        """关闭服务"""
        logger.info("关闭MCP服务")
        await self.connection_pool.shutdown()
        logger.info("MCP服务关闭完成")