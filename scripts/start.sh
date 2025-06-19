#!/bin/bash

# MCP生产客户端启动脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查依赖
check_dependencies() {
    log_info "检查依赖..."
    
    # 检查Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3未找到，请先安装Python 3.11+"
        exit 1
    fi
    
    # 检查Python版本
    python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    required_version="3.11"
    if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
        log_error "Python版本过低: $python_version，需要3.11+"
        exit 1
    fi
    
    # 检查uv
    if ! command -v uv &> /dev/null; then
        log_warn "uv未找到，尝试安装..."
        pip install uv
    fi
    
    log_info "依赖检查完成"
}

# 设置环境
setup_environment() {
    log_info "设置环境..."
    
    # 检查.env文件
    if [ ! -f .env ]; then
        if [ -f .env.example ]; then
            log_warn ".env文件不存在，从.env.example复制"
            cp .env.example .env
            log_warn "请编辑.env文件设置正确的配置"
        else
            log_error ".env和.env.example文件都不存在"
            exit 1
        fi
    fi
    
    # 创建虚拟环境
    if [ ! -d "venv" ]; then
        log_info "创建虚拟环境..."
        python3 -m venv venv
    fi
    
    # 激活虚拟环境
    source venv/bin/activate
    
    # 安装依赖
    log_info "安装依赖..."
    if command -v uv &> /dev/null; then
        uv pip install -r pyproject.toml
    else
        pip install -e .
    fi
    
    log_info "环境设置完成"
}

# 检查配置
check_configuration() {
    log_info "检查配置..."
    
    # 检查MCP配置文件
    if [ ! -f mcp.json ]; then
        log_error "mcp.json配置文件不存在"
        exit 1
    fi
    
    # 检查环境变量
    source .env
    if [ -z "$OPENAI_API_KEY" ]; then
        log_error "OPENAI_API_KEY未设置"
        exit 1
    fi
    
    log_info "配置检查完成"
}

# 启动服务
start_service() {
    log_info "启动MCP生产客户端..."
    
    # 激活虚拟环境
    source venv/bin/activate
    
    # 加载环境变量
    source .env
    
    # 创建日志目录
    mkdir -p logs
    
    # 启动服务
    python -m src.api.main
}

# Docker模式启动
start_docker() {
    log_info "使用Docker启动..."
    
    # 检查Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker未找到，请先安装Docker"
        exit 1
    fi
    
    # 检查docker-compose
    if ! command -v docker-compose &> /dev/null; then
        log_error "docker-compose未找到，请先安装docker-compose"
        exit 1
    fi
    
    # 检查.env文件
    if [ ! -f .env ]; then
        log_error ".env文件不存在，请从.env.example复制并配置"
        exit 1
    fi
    
    # 启动服务
    docker-compose up -d
    
    log_info "Docker服务启动完成"
    log_info "API服务: http://localhost:8000"
    log_info "Prometheus: http://localhost:9090"
    log_info "Grafana: http://localhost:3000"
}

# 停止Docker服务
stop_docker() {
    log_info "停止Docker服务..."
    docker-compose down
    log_info "Docker服务已停止"
}

# 显示帮助
show_help() {
    echo "MCP生产客户端启动脚本"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  start       启动服务（本地模式）"
    echo "  docker      使用Docker启动"
    echo "  stop        停止Docker服务"
    echo "  check       检查环境和配置"
    echo "  help        显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 start     # 本地启动"
    echo "  $0 docker    # Docker启动"
    echo "  $0 stop      # 停止Docker服务"
}

# 主函数
main() {
    case "$1" in
        start)
            check_dependencies
            setup_environment
            check_configuration
            start_service
            ;;
        docker)
            start_docker
            ;;
        stop)
            stop_docker
            ;;
        check)
            check_dependencies
            check_configuration
            log_info "环境和配置检查完成"
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "无效选项: $1"
            show_help
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"