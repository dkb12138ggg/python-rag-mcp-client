# MCP生产级客户端文档

欢迎使用MCP生产级客户端！这是一个功能强大的AI服务平台，提供完整的MCP工具调用和RAG知识库功能。

## 📚 文档目录

### 新手入门
1. **[项目说明](项目说明.md)** - 了解项目的基本功能和特性
2. **[部署指南](部署指南.md)** - 从零开始部署项目
3. **[API调用示例](API调用示例.md)** - 学习如何使用API

### 高级配置
4. **[AI模型配置](AI模型配置.md)** - 配置和更换不同的AI服务

## 🚀 快速开始

### 最简单的部署方式（Docker）

1. **克隆项目**
   ```bash
   git clone <项目地址>
   cd python-mcp-server-client
   ```

2. **配置环境变量**
   ```bash
   cp .env.example .env
   # 编辑.env文件，至少设置OPENAI_API_KEY
   ```

3. **启动服务**
   ```bash
   ./scripts/start.sh docker
   ```

4. **访问服务**
   - API文档：http://localhost:8000/docs
   - Grafana监控：http://localhost:3000

### 第一次API调用

```bash
# 健康检查
curl http://localhost:8000/health

# 发送查询
curl -X POST "http://localhost:8000/query" \
-H "Content-Type: application/json" \
-d '{"query": "今天天气如何？"}'

# 上传文档到知识库
curl -X POST "http://localhost:8000/rag/documents/upload" \
-F "file=@你的文档.pdf" \
-F "title=测试文档"

# 搜索知识库
curl -X POST "http://localhost:8000/rag/search" \
-H "Content-Type: application/json" \
-d '{"query": "搜索内容"}'
```

## 🔧 主要功能

### MCP工具调用
- 连接多个MCP服务器
- 智能工具路由和负载均衡
- 实时状态监控

### RAG知识库
- 支持多种文档格式（PDF、Word、Markdown、TXT）
- 智能文档分块和向量化
- 高性能语义搜索

### 监控和运维
- Prometheus指标收集
- Grafana可视化面板
- 完整的日志记录
- 健康检查端点

## 🛠️ 系统要求

- **Python**: 3.11+
- **内存**: 4GB以上（推荐8GB）
- **存储**: 20GB可用空间
- **数据库**: PostgreSQL + pgvector
- **缓存**: Redis

## 📖 详细文档

### 1. 项目说明
了解项目的核心功能、技术架构和应用场景。适合想要全面了解项目的用户。

[查看项目说明 →](项目说明.md)

### 2. 部署指南
详细的部署步骤，包括本地开发环境和生产环境部署。支持Docker和手动部署两种方式。

[查看部署指南 →](部署指南.md)

### 3. API调用示例
完整的API使用教程，包括Python和JavaScript客户端示例，以及错误处理和性能优化建议。

[查看API调用示例 →](API调用示例.md)

### 4. AI模型配置
如何配置和更换不同的AI服务，支持OpenAI、国产AI服务和本地模型。

[查看AI模型配置 →](AI模型配置.md)

## 🤝 支持和反馈

如果您在使用过程中遇到问题或有任何建议，请：

1. 查看相关文档是否有解决方案
2. 检查[常见问题](部署指南.md#故障排除)
3. 提交Issue或联系技术支持

## 📄 许可证

本项目采用MIT许可证，详情请查看LICENSE文件。

---

*最后更新：2024年12月*