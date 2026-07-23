# MCP iOS Components 生产部署方案

## 架构概览

```
                                    ┌─────────────────────────────────────┐
                                    │           Load Balancer             │
                                    │     (Nginx / Cloud LB / Traefik)    │
                                    └──────────────┬──────────────────────┘
                                                   │ HTTPS :443
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                              Nginx Reverse Proxy                          │
│                    (SSL termination + rate limiting)                      │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │ HTTP :8900
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         MCP Server Container                              │
│                                                                           │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────────┐  │
│   │  Uvicorn    │    │   索引缓存   │    │      组件仓库 (Git)         │  │
│   │  ASGI       │◄──►│   .cache/   │◄──►│      /data/pods/            │  │
│   └─────────────┘    └─────────────┘    └─────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │   Persistent Volume      │
                    │   - /data/pods (组件)    │
                    │   - /data/cache (索引)   │
                    │   - /data/keys (API密钥) │
                    └──────────────────────────┘
```

## 部署方式选择

| 方式 | 适用场景 | 复杂度 | 推荐度 |
|------|----------|--------|--------|
| **Docker Compose** | 单机/小团队 | ⭐ | ⭐⭐⭐⭐⭐ |
| **Kubernetes** | 大规模/多团队 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Systemd** | 裸机部署 | ⭐⭐ | ⭐⭐⭐ |
| **macOS launchd + GitHub Actions** | 当前研发专用 Mac | ⭐⭐ | ⭐⭐⭐⭐⭐ |

## macOS 自动部署（当前生产方案）

MCP 与 lark-ios-bot 是两个独立仓库、两个独立服务。MCP 仅使用标签为
`ios-components-mcp-deploy` 的 YuXilong-Labs runner，不会复用或修改 BaiTu-iOS 的 Bot runner。

### 固定目录

| 用途 | 路径 |
|------|------|
| 服务代码 | `/Users/jenkins/services/mcp-ios-components` |
| 组件与索引 | `/Users/jenkins/data/mcp-ios-components` |
| 日志 | `/Users/jenkins/Library/Logs/mcp-ios-components` |
| launchd | `com.baitu.mcp-ios-components` |

`main` push 和手动 `workflow_dispatch` 都会触发 `.github/workflows/deploy-main.yml`。部署顺序固定为：

1. 在 runner 工作区安装依赖并运行全量 `pytest`。
2. 测试通过后同步服务代码，保留目标机 `.env`、`.venv` 和组件数据。
3. 安装或更新 launchd，服务仅监听 `127.0.0.1:8900`。
4. 通过 MCP 协议执行生产白名单同步，任何组件同步错误都会使 Action 失败。
5. 调用 `list_components`、`search_component`、`watch_status` 和健康检查完成部署验收。

生产白名单维护在 `deploy/components.production.yaml`。GitLab 凭据只保存在目标机
`/Users/jenkins/services/mcp-ios-components/.env`，Action 和仓库均不保存凭据。

### 自动更新

服务默认每 60 秒检查各组件当前分支。发现远端提交后使用 `git pull --ff-only` 更新，并在同一临界区内重建
在线索引；Action 部署后的白名单同步、定时检查和 GitLab Webhook 共用同一把进程锁，不会并发修改组件目录。

### 本机安全访问

生产服务不直接暴露局域网端口。本机使用 SSH 隧道访问：

```bash
ssh -N -L 18900:127.0.0.1:8900 jenkins@10.0.71.58
python3 scripts/mcp_http_client.py \
  --url http://127.0.0.1:18900/mcp \
  --tool list_components \
  --contains BTBaseKit
```

目标机本地健康检查：

```bash
curl --noproxy '*' http://127.0.0.1:8900/webhook/health
launchctl print gui/$(id -u)/com.baitu.mcp-ios-components
```

---

## 方案一：Docker Compose（推荐）

### 1. 目录结构

```
/opt/mcp-ios-components/
├── docker-compose.yml
├── .env                    # 环境变量（敏感信息）
├── nginx/
│   └── mcp.conf           # Nginx 配置
├── data/
│   ├── pods/              # 组件仓库
│   ├── cache/             # 索引缓存
│   └── keys/              # API 密钥
└── logs/                  # 日志目录
```

### 2. 快速部署

```bash
# 1. 克隆仓库
git clone https://github.com/YuXilong-Labs/mcp-ios-components.git
cd mcp-ios-components/deploy

# 2. 配置环境变量
cp .env.example .env
vim .env  # 填写实际配置

# 3. 生成 API Key
docker compose run --rm mcp python mcp_server.py --gen-key "admin"

# 4. 启动服务
docker compose up -d

# 5. 验证
curl -H "Authorization: Bearer sk-xxx" http://localhost:8900/health
```

### 3. 配置清单

#### .env 文件
```bash
# 基础配置
MCP_PORT=8900
MCP_HOST=0.0.0.0

# GitLab 配置（可选）
GITLAB_URL=https://gitlab.your-company.com
GITLAB_TOKEN=glpat-xxxxxxxxxxxx
GITLAB_GROUP=ios-components

# Webhook 安全
WEBHOOK_SECRET=your-webhook-secret-here

# 定时更新
WATCH_INTERVAL=300

# SSH Key（用于 git clone）
SSH_PRIVATE_KEY_PATH=/root/.ssh/id_rsa
```

---

## 方案二：Kubernetes

### Helm Chart 结构

```
helm/mcp-ios-components/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   └── pvc.yaml
```

### 部署命令

```bash
helm install mcp-ios ./helm/mcp-ios-components \
  --namespace mcp \
  --create-namespace \
  --set gitlab.token=$GITLAB_TOKEN \
  --set ingress.host=mcp.your-company.com
```

---

## 方案三：Systemd（裸机）

```bash
# 安装服务
sudo cp deploy/mcp-ios-components.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mcp-ios-components
sudo systemctl start mcp-ios-components

# 查看日志
journalctl -u mcp-ios-components -f
```

---

## 安全配置

### 1. API Key 管理

```bash
# 生成 Key（建议为每个用户/服务生成独立 Key）
python mcp_server.py --gen-key "alice-macbook"
python mcp_server.py --gen-key "ci-server"
python mcp_server.py --gen-key "jenkins"

# 列出所有 Key
python mcp_server.py --list-keys

# Key 文件权限
chmod 600 /data/keys/.api-keys
```

### 2. 网络安全

- **仅内网访问**：不直接暴露到公网
- **VPN/专线**：远程团队通过 VPN 访问
- **IP 白名单**：Nginx 配置 `allow/deny`

### 3. HTTPS 配置

```nginx
server {
    listen 443 ssl http2;
    server_name mcp.your-company.com;
    
    ssl_certificate /etc/ssl/certs/mcp.crt;
    ssl_certificate_key /etc/ssl/private/mcp.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    
    location / {
        proxy_pass http://127.0.0.1:8900;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 4. Rate Limiting

```nginx
limit_req_zone $binary_remote_addr zone=mcp_limit:10m rate=10r/s;

server {
    location / {
        limit_req zone=mcp_limit burst=20 nodelay;
        proxy_pass http://127.0.0.1:8900;
    }
}
```

---

## 监控与告警

### 1. 健康检查端点

```bash
# 服务健康
curl http://localhost:8900/webhook/health

# 索引状态（通过 MCP 工具）
# watch_status, list_components
```

### 2. Prometheus Metrics（建议添加）

```python
# 可以添加 prometheus_client 暴露指标
# - mcp_requests_total
# - mcp_index_size
# - mcp_component_count
# - mcp_cache_hits
```

### 3. 日志收集

```yaml
# docker-compose.yml 日志配置
logging:
  driver: "json-file"
  options:
    max-size: "100m"
    max-file: "5"
```

### 4. 告警规则

| 指标 | 阈值 | 动作 |
|------|------|------|
| 服务不可用 | > 1 min | PagerDuty/飞书告警 |
| 响应时间 | > 5s | 通知 |
| 磁盘使用 | > 80% | 清理缓存 |
| 索引失败 | 连续 3 次 | 检查 Git 权限 |

---

## 备份策略

### 1. 需要备份的内容

| 数据 | 重要性 | 备份频率 |
|------|--------|----------|
| `.api-keys` | 高 | 每次变更 |
| `components.yaml` | 高 | 每次变更 |
| `.cache/index.json` | 低 | 可重建 |
| 组件仓库 | 低 | GitLab 已有 |

### 2. 备份脚本

```bash
#!/bin/bash
BACKUP_DIR=/backup/mcp-ios/$(date +%Y%m%d)
mkdir -p $BACKUP_DIR
cp /data/keys/.api-keys $BACKUP_DIR/
cp /opt/mcp-ios-components/.env $BACKUP_DIR/
cp /opt/mcp-ios-components/components.yaml $BACKUP_DIR/
```

---

## CI/CD 集成

### GitLab CI 自动部署

```yaml
# .gitlab-ci.yml
stages:
  - build
  - deploy

build:
  stage: build
  script:
    - docker build -t registry.company.com/mcp-ios:$CI_COMMIT_SHA .
    - docker push registry.company.com/mcp-ios:$CI_COMMIT_SHA

deploy:
  stage: deploy
  script:
    - ssh deploy@mcp-server "cd /opt/mcp-ios && docker compose pull && docker compose up -d"
  only:
    - main
```

### Webhook 自动更新组件

GitLab 仓库配置 Webhook → MCP Server 自动拉取更新：

```
URL: https://mcp.your-company.com/webhook/gitlab
Secret: $WEBHOOK_SECRET
Events: Push events
```

---

## 运维命令速查

```bash
# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f mcp

# 重建索引
docker compose exec mcp python mcp_server.py --rebuild-index

# 同步组件
docker compose exec mcp python mcp_server.py --sync components.yaml --sync-only

# 添加 API Key
docker compose exec mcp python mcp_server.py --gen-key "new-user"

# 重启服务
docker compose restart mcp

# 更新镜像
docker compose pull && docker compose up -d
```

---

## 容量规划

| 规模 | 组件数 | 源文件数 | 内存 | 磁盘 | CPU |
|------|--------|----------|------|------|-----|
| 小型 | < 20 | < 5000 | 512MB | 5GB | 1 核 |
| 中型 | 20-50 | 5000-20000 | 1GB | 20GB | 2 核 |
| 大型 | > 50 | > 20000 | 2GB+ | 50GB+ | 4 核 |

---

## 故障排查

### 常见问题

1. **索引构建失败**
   - 检查组件目录权限
   - 检查 podspec 文件是否有效

2. **Git clone/pull 失败**
   - 检查 SSH Key 是否正确挂载
   - 检查 GitLab Token 权限

3. **API Key 认证失败**
   - 确认 Key 文件路径正确
   - 确认 Key 格式（sk- 前缀）

4. **内存占用过高**
   - 减少 `--watch` 频率
   - 清理不需要的组件
