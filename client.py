import asyncio
import json
import os
from typing import Optional, List, Dict, Any
from contextlib import AsyncExitStack
import time
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client

from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()  # 从 .env 文件加载环境变量

class MCPClient:
    def __init__(self):
        # 初始化会话和客户端对象
        self.sessions: List[ClientSession] = []
        self.session_contexts: List[Any] = []
        self.stream_contexts: List[Any] = []
        self.exit_stack = AsyncExitStack()
        self.openai = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"), 
            base_url=os.getenv("OPENAI_BASE_URL")
        )

    def load_server_config(self, config_path: str) -> List[Dict[str, Any]]:
        """从配置文件加载服务器配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
                # 支持新的 mcpServers 对象格式
                if 'mcpServers' in config:
                    servers = []
                    for name, server_config in config['mcpServers'].items():
                        server = {
                            'name': name,
                            **server_config
                        }
                        servers.append(server)
                    return servers
                
                # 兼容旧的 servers 数组格式
                elif 'servers' in config:
                    return config.get('servers', [])
                
                else:
                    print("配置文件格式错误：缺少 'mcpServers' 或 'servers' 字段")
                    return []
                    
        except FileNotFoundError:
            print(f"配置文件 {config_path} 未找到")
            return []
        except json.JSONDecodeError as e:
            print(f"配置文件 {config_path} 格式错误: {e}")
            return []

    async def connect_to_sse_server(self, server_url: str, server_name: str):
        """连接到使用 SSE 传输的 MCP 服务器"""
        try:
            # 存储上下文管理器以保持其活动
            streams_context = sse_client(url=server_url)
            # 进入 SSE 流上下文，获取流列表
            streams = await streams_context.__aenter__()

            # 创建客户端会话上下文，并进入该上下文
            session_context = ClientSession(*streams)
            session: ClientSession = await session_context.__aenter__()

            # 调用 initialize 方法进行初始化
            await session.initialize()

            # 存储上下文和会话
            self.stream_contexts.append(streams_context)
            self.session_contexts.append(session_context)
            self.sessions.append(session)

            # 列出可用工具以验证连接
            response = await session.list_tools()
            tools = response.tools
            print(f"✓ 已连接到 SSE 服务器 '{server_name}' ({server_url})")
            print(f"  可用工具: {[tool.name for tool in tools]}")
            
        except Exception as e:
            print(f"✗ 连接 SSE 服务器 '{server_name}' 失败: {e}")

    async def connect_to_stdio_server(self, command: str, args: List[str], server_name: str):
        """连接到使用 stdio 传输的 MCP 服务器"""
        try:
            # 创建 StdioServerParameters
            from mcp import StdioServerParameters
            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=None
            )
            
            # 存储上下文管理器以保持其活动
            streams_context = stdio_client(server_params)
            # 进入 stdio 流上下文，获取流列表
            streams = await streams_context.__aenter__()

            # 创建客户端会话上下文，并进入该上下文
            session_context = ClientSession(*streams)
            session: ClientSession = await session_context.__aenter__()

            # 调用 initialize 方法进行初始化
            await session.initialize()

            # 存储上下文和会话
            self.stream_contexts.append(streams_context)
            self.session_contexts.append(session_context)
            self.sessions.append(session)

            # 列出可用工具以验证连接
            response = await session.list_tools()
            tools = response.tools
            print(f"✓ 已连接到 stdio 服务器 '{server_name}' ({command} {' '.join(args)})")
            print(f"  可用工具: {[tool.name for tool in tools]}")
            
        except Exception as e:
            print(f"✗ 连接 stdio 服务器 '{server_name}' 失败: {e}")

    async def connect_to_servers(self):
        """根据环境变量配置连接到多个服务器"""
        config_path = os.getenv("MCP_SERVER_URL", "mcp.json")
        print(f"从配置文件加载服务器配置: {config_path}")
        
        servers = self.load_server_config(config_path)
        if not servers:
            print("未找到服务器配置，请检查配置文件")
            return

        print(f"找到 {len(servers)} 个服务器配置")
        
        # 并发连接所有服务器
        connection_tasks = []
        for server in servers:
            server_type = server.get('type')
            server_name = server.get('name', 'unknown')
            
            if server_type == 'sse':
                url = server.get('url')
                if url:
                    task = self.connect_to_sse_server(url, server_name)
                    connection_tasks.append(task)
                else:
                    print(f"SSE 服务器 '{server_name}' 缺少 URL 配置")
                    
            elif server_type == 'stdio':
                command = server.get('command')
                args = server.get('args', [])
                if command:
                    task = self.connect_to_stdio_server(command, args, server_name)
                    connection_tasks.append(task)
                else:
                    print(f"stdio 服务器 '{server_name}' 缺少命令配置")
            else:
                print(f"未知的服务器类型: {server_type}")

        # 等待所有连接完成
        if connection_tasks:
            await asyncio.gather(*connection_tasks, return_exceptions=True)

    async def cleanup(self):
        """正确清理所有会话和流"""
        # 退出所有客户端会话上下文
        for session_context in self.session_contexts:
            try:
                await session_context.__aexit__(None, None, None)
            except Exception as e:
                print(f"清理会话时出错: {e}")
        
        # 退出所有流上下文
        for stream_context in self.stream_contexts:
            try:
                await stream_context.__aexit__(None, None, None)
            except Exception as e:
                print(f"清理流时出错: {e}")

    async def get_all_tools(self) -> List[Dict[str, Any]]:
        """获取所有连接服务器的工具"""
        all_tools = []
        for i, session in enumerate(self.sessions):
            try:
                response = await session.list_tools()
                for tool in response.tools:
                    all_tools.append({
                        "type": "function",
                        "function": {
                            "name": f"{tool.name}_server_{i}",  # 添加服务器索引避免重名
                            "description": f"[服务器 {i}] {tool.description}",
                            "parameters": tool.inputSchema
                        },
                        "original_name": tool.name,
                        "server_index": i
                    })
            except Exception as e:
                print(f"获取服务器 {i} 工具列表失败: {e}")
        return all_tools

    async def process_query(self, query: str) -> str:
        """使用 OpenAI API 和可用工具处理查询"""
        if not self.sessions:
            return "错误: 没有可用的服务器连接"

        # 构建初始消息列表，包含用户输入
        messages = [{
            "role": "user",
            "content": query
        }]

        # 获取并封装所有可用工具信息
        available_tools = await self.get_all_tools()
        
        if not available_tools:
            return "错误: 没有可用的工具"

        # 调用 OpenAI Chat 完成接口，发送用户消息和工具列表
        completion = await self.openai.chat.completions.create(
            model=os.getenv("OPENAI_MODEL"),
            max_tokens=1000,
            messages=messages,
            tools=available_tools
        )

        tool_results = []  # 存储工具调用结果
        final_text = []    # 存储最终返回文本
        assistant_message = completion.choices[0].message

        # 处理工具调用
        if assistant_message.tool_calls:
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                # 找到对应的工具和服务器
                tool_info = None
                for tool in available_tools:
                    if tool["function"]["name"] == tool_name:
                        tool_info = tool
                        break

                if tool_info:
                    server_index = tool_info["server_index"]
                    original_name = tool_info["original_name"]
                    session = self.sessions[server_index]

                    try:
                        # 执行工具调用并记录结果
                        result = await session.call_tool(original_name, tool_args)
                        tool_results.append({"call": tool_name, "result": result})
                        final_text.append(f"[调用工具 {original_name} (服务器 {server_index})，参数: {tool_args}]")

                        # 将工具调用上下文添加回消息列表
                        messages.extend([
                            {"role": "assistant", "content": None, "tool_calls": [tool_call]},
                            {"role": "tool", "tool_call_id": tool_call.id, "content": result.content[0].text}
                        ])

                        # 获取工具调用后的后续响应
                        completion = await self.openai.chat.completions.create(
                            model=os.getenv("OPENAI_MODEL"),
                            max_tokens=1000,
                            messages=messages,
                        )
                        # 处理返回内容是否为结构化数据
                        if isinstance(completion.choices[0].message.content, (dict, list)):
                            final_text.append(str(completion.choices[0].message.content))
                        else:
                            final_text.append(completion.choices[0].message.content)
                    except Exception as e:
                        final_text.append(f"工具调用失败: {e}")
                else:
                    final_text.append(f"未找到工具: {tool_name}")
        else:
            # 无工具调用时，直接返回助手消息内容
            content = assistant_message.content
            final_text.append(str(content) if isinstance(content, (dict, list)) else content)

        return "\n".join(final_text)

    async def chat_loop(self):
        """运行交互式聊天循环"""
        print("\nMCP 多服务器客户端已启动！")
        print(f"已连接 {len(self.sessions)} 个服务器")
        print("输入您的查询或输入 'quit' 退出。")

        while True:
            try:
                query = input("\n查询: ").strip()
                if query.lower() == 'quit':
                    break
                response = await self.process_query(query)
                print("\n" + response)
            except Exception as e:
                print(f"\n错误: {str(e)}")


async def main():
    # 程序入口
    client = MCPClient()
    try:
        await client.connect_to_servers()
        if client.sessions:
            await client.chat_loop()
        else:
            print("没有成功连接到任何服务器，程序退出")
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())  