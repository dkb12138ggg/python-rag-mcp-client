# AI模型配置指南

本指南详细介绍如何配置和更换不同的AI模型和API服务，让您可以根据需求选择最适合的AI服务提供商。

## 一、支持的AI服务

### 1. OpenAI官方API
- **模型**：gpt-4, gpt-4-turbo, gpt-3.5-turbo等
- **嵌入模型**：text-embedding-ada-002, text-embedding-3-small, text-embedding-3-large
- **优势**：性能最佳，功能最全
- **缺点**：价格较高，需要海外网络

### 2. Azure OpenAI Service
- **模型**：与OpenAI相同的模型
- **优势**：企业级支持，符合合规要求
- **缺点**：需要申请白名单

### 3. 国内AI服务
- **阿里云通义千问**：qwen-turbo, qwen-plus, qwen-max
- **百度文心一言**：ernie-bot, ernie-bot-turbo
- **腾讯混元**：hunyuan-lite, hunyuan-standard, hunyuan-pro
- **字节跳动豆包**：doubao-lite, doubao-pro
- **智谱AI**：glm-4, glm-3-turbo

### 4. 开源模型服务
- **Ollama**：本地部署开源模型
- **LM Studio**：本地模型管理工具
- **vLLM**：高性能推理服务
- **Text Generation WebUI**：开源Web界面

## 二、配置方法

### 1. OpenAI官方API配置

#### 基础配置
```bash
# .env文件配置
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4
OPENAI_MAX_TOKENS=1000
OPENAI_TIMEOUT=30

# RAG嵌入模型配置
RAG_EMBEDDING_MODEL=text-embedding-ada-002
RAG_EMBEDDING_DIMENSIONS=1536
```

#### 支持的模型列表
```bash
# 文本生成模型
OPENAI_MODEL=gpt-4                    # 最强模型
OPENAI_MODEL=gpt-4-turbo             # 更快的GPT-4
OPENAI_MODEL=gpt-3.5-turbo           # 经济实用
OPENAI_MODEL=gpt-3.5-turbo-16k       # 长上下文版本

# 嵌入模型
RAG_EMBEDDING_MODEL=text-embedding-ada-002      # 1536维
RAG_EMBEDDING_MODEL=text-embedding-3-small      # 1536维，更便宜
RAG_EMBEDDING_MODEL=text-embedding-3-large      # 3072维，更准确
```

### 2. Azure OpenAI Service配置

```bash
# Azure OpenAI配置
OPENAI_API_KEY=your-azure-api-key
OPENAI_BASE_URL=https://your-resource.openai.azure.com/openai/deployments/your-deployment-name
OPENAI_MODEL=gpt-4  # 这里是你在Azure中部署的模型名称

# 特殊配置（如果需要）
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-15-preview
```

### 3. 国内AI服务配置

#### 阿里云通义千问
```bash
# 通义千问配置
OPENAI_API_KEY=sk-your-dashscope-api-key
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=qwen-max
OPENAI_MAX_TOKENS=2000
OPENAI_TIMEOUT=30

# 嵌入模型
RAG_EMBEDDING_MODEL=text-embedding-v1
RAG_EMBEDDING_DIMENSIONS=1536
```

#### 百度文心一言
```bash
# 文心一言配置（需要转换接口）
OPENAI_API_KEY=your-baidu-api-key
OPENAI_BASE_URL=https://your-proxy-service/v1  # 需要代理服务转换接口
OPENAI_MODEL=ernie-bot-turbo
```

#### 智谱AI
```bash
# 智谱AI配置
OPENAI_API_KEY=your-zhipuai-api-key
OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
OPENAI_MODEL=glm-4
```

#### 月之暗面Kimi
```bash
# Kimi配置
OPENAI_API_KEY=your-moonshot-api-key
OPENAI_BASE_URL=https://api.moonshot.cn/v1
OPENAI_MODEL=moonshot-v1-8k
```

### 4. 本地模型配置（Ollama）

#### 安装Ollama
```bash
# Linux/macOS
curl -fsSL https://ollama.com/install.sh | sh

# 启动服务
ollama serve
```

#### 下载模型
```bash
# 下载模型
ollama pull llama2
ollama pull qwen:7b
ollama pull baichuan2:7b
```

#### 配置环境变量
```bash
# Ollama配置
OPENAI_API_KEY=ollama  # 任意值即可
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_MODEL=llama2
OPENAI_MAX_TOKENS=2000
OPENAI_TIMEOUT=60

# 本地嵌入模型
RAG_EMBEDDING_MODEL=mxbai-embed-large
RAG_EMBEDDING_DIMENSIONS=1024
```

## 三、高级配置

### 1. 多模型配置

可以配置多个不同的模型用于不同场景：

```python
# src/config/model_config.py
MODEL_CONFIGS = {
    "chat": {
        "api_key": os.getenv("OPENAI_API_KEY"),
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4",
        "max_tokens": 1000
    },
    "embedding": {
        "api_key": os.getenv("OPENAI_API_KEY"),
        "base_url": "https://api.openai.com/v1",
        "model": "text-embedding-ada-002"
    },
    "summary": {
        "api_key": os.getenv("QWEN_API_KEY"),
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-turbo",
        "max_tokens": 500
    }
}
```

### 2. 负载均衡配置

配置多个API服务进行负载均衡：

```bash
# 主服务
OPENAI_API_KEY=primary-key
OPENAI_BASE_URL=https://api.openai.com/v1

# 备用服务
OPENAI_BACKUP_API_KEY=backup-key
OPENAI_BACKUP_BASE_URL=https://backup-api.com/v1

# 负载均衡配置
OPENAI_LOAD_BALANCE=true
OPENAI_FAILOVER_ENABLED=true
```

### 3. 性能优化配置

```bash
# 连接池配置
OPENAI_MAX_CONNECTIONS=20
OPENAI_MAX_KEEPALIVE_CONNECTIONS=5
OPENAI_KEEPALIVE_EXPIRY=30

# 重试配置
OPENAI_MAX_RETRIES=3
OPENAI_RETRY_DELAY=1
OPENAI_EXPONENTIAL_BACKOFF=true

# 缓存配置
OPENAI_ENABLE_CACHE=true
OPENAI_CACHE_TTL=3600
```

## 四、模型选择建议

### 1. 根据场景选择

#### 通用对话
- **高质量需求**：GPT-4 > 通义千问Max > 文心一言4.0
- **性价比平衡**：GPT-3.5-turbo > 通义千问Plus > 智谱GLM-4
- **快速响应**：通义千问Turbo > 文心一言Turbo > 豆包Lite

#### 代码生成
- **首选**：GPT-4 > Claude-3 > 通义千问Max
- **备选**：智谱GLM-4 > 文心一言4.0

#### 文档分析
- **长文档**：GPT-4-turbo > 通义千问Max > Kimi
- **短文档**：GPT-3.5-turbo > 通义千问Plus

#### 创意写作
- **最佳**：GPT-4 > Claude-3 > 文心一言4.0
- **实用**：通义千问Plus > 混元Pro

### 2. 根据预算选择

#### 高预算（性能优先）
```bash
# 主力模型
OPENAI_MODEL=gpt-4
RAG_EMBEDDING_MODEL=text-embedding-3-large

# 每1000tokens约$0.03-0.06
```

#### 中等预算（平衡性价比）
```bash
# 主力模型
OPENAI_MODEL=gpt-3.5-turbo
RAG_EMBEDDING_MODEL=text-embedding-ada-002

# 每1000tokens约$0.001-0.002
```

#### 低预算（成本优先）
```bash
# 国产模型
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=qwen-turbo
RAG_EMBEDDING_MODEL=text-embedding-v1

# 每1000tokens约￥0.001-0.002
```

#### 零成本（本地部署）
```bash
# Ollama本地模型
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_MODEL=llama2
RAG_EMBEDDING_MODEL=mxbai-embed-large
```

### 3. 根据延迟要求选择

#### 低延迟需求（<2秒）
- **国内服务**：通义千问、文心一言、混元
- **本地模型**：Ollama + 小参数模型
- **CDN加速**：使用国内代理服务

#### 中等延迟（2-5秒）
- **OpenAI官方**：GPT-3.5-turbo
- **国产大模型**：通义千问Plus、智谱GLM-4

#### 高延迟可接受（>5秒）
- **OpenAI官方**：GPT-4, GPT-4-turbo
- **复杂任务**：需要多步推理的场景

## 五、故障排除

### 1. 常见问题

#### API密钥无效
```bash
# 检查API密钥格式
echo $OPENAI_API_KEY | wc -c  # OpenAI密钥通常51字符

# 测试API连接
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model":"gpt-3.5-turbo","messages":[{"role":"user","content":"test"}],"max_tokens":1}' \
     https://api.openai.com/v1/chat/completions
```

#### 网络连接问题
```bash
# 测试网络连接
curl -I https://api.openai.com/v1/models

# 使用代理
export https_proxy=http://proxy.company.com:8080
export http_proxy=http://proxy.company.com:8080
```

#### 模型不存在
```bash
# 列出可用模型
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     https://api.openai.com/v1/models
```

#### 配额超限
```bash
# 查看当前配额（OpenAI）
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     https://api.openai.com/v1/usage
```

### 2. 调试方法

#### 启用详细日志
```bash
# 环境变量
LOG_LEVEL=DEBUG
OPENAI_DEBUG=true

# 查看API调用日志
tail -f logs/mcp-client.log | grep -i openai
```

#### 测试配置
```python
# test_config.py
import os
from src.config.settings import settings

def test_openai_config():
    print(f"API Key: {settings.openai.api_key[:10]}...")
    print(f"Base URL: {settings.openai.base_url}")
    print(f"Model: {settings.openai.model}")
    print(f"Max Tokens: {settings.openai.max_tokens}")
    print(f"Timeout: {settings.openai.timeout}")

if __name__ == "__main__":
    test_openai_config()
```

### 3. 性能监控

#### 响应时间监控
```bash
# 查看Prometheus指标
curl http://localhost:8001/metrics | grep openai_request_duration
```

#### 错误率监控
```bash
# 查看错误日志
tail -f logs/mcp-client.log | grep -i error | grep -i openai
```

## 六、最佳实践

### 1. 安全配置
- 使用环境变量存储API密钥
- 定期轮换API密钥
- 设置适当的访问权限
- 不要在代码中硬编码密钥

### 2. 成本控制
- 设置合理的max_tokens限制
- 使用缓存减少重复请求
- 监控API使用量和成本
- 选择合适的模型平衡性能和成本

### 3. 可靠性保障
- 配置多个备用API服务
- 实现指数退避重试机制
- 设置合理的超时时间
- 监控服务可用性

### 4. 性能优化
- 使用连接池复用连接
- 合理设置并发限制
- 缓存频繁使用的结果
- 选择地理位置最近的服务

---

## 七、配置模板

### 开发环境配置
```bash
# 开发环境 - 使用OpenAI
OPENAI_API_KEY=sk-your-dev-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-3.5-turbo
OPENAI_MAX_TOKENS=1000
OPENAI_TIMEOUT=30

RAG_EMBEDDING_MODEL=text-embedding-ada-002
RAG_EMBEDDING_DIMENSIONS=1536
```

### 生产环境配置
```bash
# 生产环境 - 使用国产模型
OPENAI_API_KEY=sk-your-prod-key
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=qwen-max
OPENAI_MAX_TOKENS=2000
OPENAI_TIMEOUT=60

RAG_EMBEDDING_MODEL=text-embedding-v1
RAG_EMBEDDING_DIMENSIONS=1536

# 备用配置
OPENAI_BACKUP_API_KEY=sk-backup-key
OPENAI_BACKUP_BASE_URL=https://api.openai.com/v1
```

### 本地开发配置
```bash
# 本地开发 - 使用Ollama
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_MODEL=qwen:7b
OPENAI_MAX_TOKENS=2000
OPENAI_TIMEOUT=120

RAG_EMBEDDING_MODEL=mxbai-embed-large
RAG_EMBEDDING_DIMENSIONS=1024
```

通过以上配置，您可以根据不同的需求和场景选择最合适的AI模型和服务。记住要定期监控性能和成本，确保系统的稳定运行。