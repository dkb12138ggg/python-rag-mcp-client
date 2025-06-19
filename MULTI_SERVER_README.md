# MCP 多服务器客户端使用指南

## 概述

这个 MCP 客户端支持同时连接多个 MCP 服务器，包括 SSE 和 stdio 两种传输方式。客户端通过读取配置文件来管理多个服务器连接。

## 环境变量配置

在项目根目录创建 `.env` 文件，配置以下环境变量：

```bash
# OpenAI API 配置
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4

# MCP 服务器配置文件路径（可选，默认为 mcp.json）
MCP_SERVER_URL=mcp.json

# 如果使用 agentdocs-server，需要配置 Serper API
SERPER_API_KEY=your_serper_api_key_here
```

## 服务器配置文件

### 当前配置示例

```json
{
  "mcpServers": {
    "bing-cn-mcp-server": {
      "type": "sse",
      "url": "https://mcp.api-inference.modelscope.cn/sse/ba6676de33e042"
    },
    "mcp-trends-hub": {
      "type": "sse",
      "url": "https://mcp.api-inference.modelscope.cn/sse/3fd71ee022c74f"
    },
    "local-math-server": {
      "type": "stdio",
      "command": "python",
      "args": ["server.py"]
    },
    "agentdocs-server": {
      "type": "stdio",
      "command": "python",
      "args": ["main.py"]
    }
  }
}
```

### 配置文件格式说明

配置文件使用 JSON 格式，支持新的 `mcpServers` 对象格式，同时兼容旧的 `servers` 数组格式。

#### SSE 服务器配置
```json
{
  "name": "服务器名称",
  "type": "sse",
  "url": "SSE 服务器的 URL"
}
```

#### stdio 服务器配置
```json
{
  "name": "服务器名称",
  "type": "stdio",
  "command": "可执行命令",
  "args": ["命令参数列表"]
}
```

## 可用服务器和工具

### 1. 本地数学服务器 (local-math-server)
- **类型**: stdio
- **文件**: `server.py`
- **工具**:
  - `add` - 两数相加
  - `subtract` - 两数相减
  - `multiply` - 两数相乘

### 2. 文档搜索服务器 (agentdocs-server)
- **类型**: stdio
- **文件**: `main.py`
- **工具**:
  - `get_docs` - 搜索AI库文档
- **支持的库**: langchain, llama-index, autogen, agno, openai-agents-sdk, mcp-doc, camel-ai, crew-ai
- **需要**: SERPER_API_KEY 环境变量

### 3. 必应搜索服务器 (bing-cn-mcp-server)
- **类型**: SSE (远程)
- **工具**:
  - `bing_search` - 网络搜索
  - `fetch_webpage` - 获取网页内容

### 4. 趋势数据服务器 (mcp-trends-hub)
- **类型**: SSE (远程)
- **工具**: 各种平台的热点趋势数据
  - `get-weibo-trending` - 微博热搜
  - `get-zhihu-trending` - 知乎热榜
  - `get-douban-rank` - 豆瓣排行
  - 等等...

## 使用方法

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件并配置必要的环境变量。

### 3. 配置服务器

编辑 `mcp.json` 文件，添加您要连接的 MCP 服务器配置。

### 4. 运行客户端

```bash
export MCP_SERVER_URL=mcp.json
python client.py
```

## 功能特性

### 多服务器支持
- 同时连接多个 MCP 服务器
- 支持 SSE 和 stdio 两种传输方式
- 并发连接，提高启动速度

### 工具管理
- 自动收集所有服务器的工具
- 工具名称自动添加服务器索引避免冲突
- 智能路由工具调用到正确的服务器

### 错误处理
- 连接失败时继续尝试其他服务器
- 工具调用失败时提供详细错误信息
- 优雅的资源清理

### 交互式聊天
- 支持自然语言查询
- 自动选择合适的工具
- 实时显示工具调用过程

## 工具调用机制

客户端会自动为每个工具添加服务器索引后缀，例如：
- 原工具名：`add`
- 客户端中的名称：`add_server_0`

当 AI 选择调用工具时，客户端会：
1. 解析工具名称，确定目标服务器
2. 使用原始工具名称调用对应服务器
3. 返回执行结果

## 示例查询

### 数学计算
```
查询: 计算 15 + 25
[调用工具 add (服务器 0)，参数: {'a': 15, 'b': 25}]
结果: 40
```

### 文档搜索
```
查询: 搜索 langchain 中关于 agent 的文档
[调用工具 get_docs (服务器 1)，参数: {'query': 'agent', 'library': 'langchain'}]
返回相关文档内容...
```

### 网络搜索
```
查询: 搜索最新的 AI 新闻
[调用工具 bing_search (服务器 2)，参数: {'query': '最新 AI 新闻'}]
返回搜索结果...
```

### 趋势数据
```
查询: 获取微博热搜
[调用工具 get-weibo-trending (服务器 3)]
返回微博热搜榜...
```

## 故障排除

### 连接问题
- 检查服务器 URL 是否正确
- 确认服务器是否正在运行
- 验证网络连接

### 配置问题
- 检查 JSON 格式是否正确
- 确认文件路径是否存在
- 验证环境变量设置

### 工具调用问题
- 查看工具参数是否正确
- 检查服务器日志
- 确认工具权限设置
- 对于 agentdocs-server，确保 SERPER_API_KEY 已配置

## 示例会话

```
MCP 多服务器客户端已启动！
✓ 已连接到 stdio 服务器 'local-math-server' (python server.py)
  可用工具: ['add', 'subtract', 'multiply']
✓ 已连接到 stdio 服务器 'agentdocs-server' (python main.py)
  可用工具: ['get_docs']
✓ 已连接到 SSE 服务器 'bing-cn-mcp-server' (https://mcp.api-inference.modelscope.cn/sse/ba6676de33e042)
  可用工具: ['bing_search', 'fetch_webpage']
✓ 已连接到 SSE 服务器 'mcp-trends-hub' (https://mcp.api-inference.modelscope.cn/sse/3fd71ee022c74f)
  可用工具: ['get-36kr-trending', 'get-9to5mac-news', ...]
已连接 4 个服务器
输入您的查询或输入 'quit' 退出。

查询: 计算 100 除以 5 再乘以 3
[调用工具 multiply (服务器 0)，参数: {'a': 20, 'b': 3}]
结果: 60

查询: 搜索 MCP 相关文档
[调用工具 get_docs (服务器 1)，参数: {'query': 'MCP', 'library': 'mcp-doc'}]
文档内容已成功获取...

查询: quit
``` 