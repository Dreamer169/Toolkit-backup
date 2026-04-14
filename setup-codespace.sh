#!/bin/bash
set -e

echo "=== 检查环境 ==="
node --version
python3 --version
npm --version

echo "=== 安装 pnpm ==="
npm install -g pnpm

echo "=== 安装依赖 ==="
cd /workspaces/Toolkit
pnpm install

echo "=== 安装 Python 依赖 ==="
pip3 install -r scripts/requirements.txt 2>/dev/null || pip3 install patchright playwright 2>/dev/null || true

echo "=== 安装 patchright 浏览器 ==="
python3 -m patchright install chromium 2>/dev/null || true

echo "=== 构建前端 ==="
pnpm --filter ai-toolkit run build

echo "=== 构建后端 ==="
pnpm --filter api-server run build

echo "=== 启动服务 ==="
PORT=8080 NODE_ENV=production nohup node --enable-source-maps artifacts/api-server/dist/index.mjs > /tmp/server.log 2>&1 &
echo "Server PID: $!"

sleep 3
curl -s http://localhost:8080/api/healthz && echo "" && echo "✅ 部署成功！"
