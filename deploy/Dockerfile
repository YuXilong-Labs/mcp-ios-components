# MCP iOS Components Server
# 生产级 Dockerfile

FROM python:3.11-slim

LABEL maintainer="YuXilong-Labs"
LABEL description="MCP Server for iOS CocoaPods component APIs"

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /root/.ssh \
    && chmod 700 /root/.ssh

# 配置 SSH（跳过 host key 验证，生产环境建议预置 known_hosts）
RUN echo "Host *\n\tStrictHostKeyChecking no\n\tUserKnownHostsFile /dev/null" > /root/.ssh/config

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt uvicorn starlette httpx

# 复制应用代码
COPY mcp_server.py .
COPY components.yaml.example .

# 创建数据目录
RUN mkdir -p /data/pods /data/cache /data/keys

# 环境变量默认值
ENV IOS_PODS_DIR=/data/pods \
    IOS_PODS_CACHE_DIR=/data/cache \
    IOS_PODS_KEYS_FILE=/data/keys/.api-keys \
    PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE 8900

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8900/webhook/health || exit 1

# 启动命令
ENTRYPOINT ["python", "mcp_server.py"]
CMD ["--http", "--port", "8900", "--host", "0.0.0.0"]
