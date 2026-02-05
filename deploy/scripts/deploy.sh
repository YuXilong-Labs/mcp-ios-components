#!/bin/bash
# MCP iOS Components 快速部署脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$(dirname "$DEPLOY_DIR")"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查依赖
check_deps() {
    local missing=()
    command -v docker &>/dev/null || missing+=("docker")
    command -v docker-compose &>/dev/null || command -v "docker compose" &>/dev/null || missing+=("docker-compose")
    
    if [ ${#missing[@]} -ne 0 ]; then
        log_error "缺少依赖: ${missing[*]}"
        exit 1
    fi
}

# 初始化环境
init() {
    log_info "初始化部署环境..."
    
    cd "$DEPLOY_DIR"
    
    # 创建数据目录
    mkdir -p data/{pods,cache,keys}
    mkdir -p nginx/ssl
    
    # 复制配置文件
    if [ ! -f .env ]; then
        cp .env.example .env
        log_warn "已创建 .env 文件，请编辑填写实际配置"
    fi
    
    if [ ! -f components.yaml ]; then
        cp "$PROJECT_DIR/components.yaml.example" components.yaml
        log_info "已创建 components.yaml"
    fi
    
    log_info "初始化完成！"
    log_info "下一步："
    log_info "  1. 编辑 .env 文件配置环境变量"
    log_info "  2. 运行 $0 genkey <name> 生成 API Key"
    log_info "  3. 运行 $0 start 启动服务"
}

# 生成 API Key
genkey() {
    local name=${1:-"default"}
    log_info "生成 API Key: $name"
    
    cd "$DEPLOY_DIR"
    docker compose run --rm mcp python mcp_server.py --gen-key "$name"
}

# 列出 API Keys
listkeys() {
    cd "$DEPLOY_DIR"
    docker compose run --rm mcp python mcp_server.py --list-keys
}

# 启动服务
start() {
    log_info "启动服务..."
    cd "$DEPLOY_DIR"
    docker compose up -d
    
    sleep 3
    if docker compose ps | grep -q "Up"; then
        log_info "服务已启动！"
        docker compose ps
    else
        log_error "启动失败，查看日志: docker compose logs"
        exit 1
    fi
}

# 停止服务
stop() {
    log_info "停止服务..."
    cd "$DEPLOY_DIR"
    docker compose down
}

# 重启服务
restart() {
    log_info "重启服务..."
    cd "$DEPLOY_DIR"
    docker compose restart
}

# 查看日志
logs() {
    cd "$DEPLOY_DIR"
    docker compose logs -f "${1:-mcp}"
}

# 更新服务
update() {
    log_info "更新服务..."
    cd "$PROJECT_DIR"
    git pull
    
    cd "$DEPLOY_DIR"
    docker compose build
    docker compose up -d
    
    log_info "更新完成！"
}

# 同步组件
sync() {
    log_info "同步组件..."
    cd "$DEPLOY_DIR"
    docker compose exec mcp python mcp_server.py --sync components.yaml --sync-only /data/pods
}

# 状态检查
status() {
    cd "$DEPLOY_DIR"
    
    echo "=== 容器状态 ==="
    docker compose ps
    
    echo ""
    echo "=== 健康检查 ==="
    curl -s http://localhost:8900/webhook/health || echo "服务未响应"
}

# 备份
backup() {
    local backup_dir="${1:-/tmp/mcp-backup-$(date +%Y%m%d_%H%M%S)}"
    log_info "备份到: $backup_dir"
    
    mkdir -p "$backup_dir"
    cd "$DEPLOY_DIR"
    
    cp .env "$backup_dir/" 2>/dev/null || true
    cp components.yaml "$backup_dir/" 2>/dev/null || true
    cp data/keys/.api-keys "$backup_dir/" 2>/dev/null || true
    
    log_info "备份完成！"
}

# 帮助信息
usage() {
    cat <<EOF
MCP iOS Components 部署脚本

用法: $0 <命令> [参数]

命令:
  init          初始化部署环境
  genkey <name> 生成 API Key
  listkeys      列出所有 API Keys
  start         启动服务
  stop          停止服务
  restart       重启服务
  logs [svc]    查看日志
  update        更新服务
  sync          同步组件
  status        查看状态
  backup [dir]  备份配置

示例:
  $0 init                    # 首次部署
  $0 genkey alice            # 生成 Key
  $0 start                   # 启动
  $0 logs                    # 查看日志
EOF
}

# 主入口
main() {
    check_deps
    
    case "${1:-}" in
        init)     init ;;
        genkey)   genkey "$2" ;;
        listkeys) listkeys ;;
        start)    start ;;
        stop)     stop ;;
        restart)  restart ;;
        logs)     logs "$2" ;;
        update)   update ;;
        sync)     sync ;;
        status)   status ;;
        backup)   backup "$2" ;;
        *)        usage ;;
    esac
}

main "$@"
