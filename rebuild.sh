#!/bin/bash
set -e
cd /workspaces/Toolkit

cp /tmp/app.ts artifacts/api-server/src/app.ts

pkill -f "node.*index.mjs" 2>/dev/null || true
sleep 1

pnpm --filter api-server run build

PORT=8080 NODE_ENV=production nohup node --enable-source-maps artifacts/api-server/dist/index.mjs > /tmp/server.log 2>&1 &
echo "Server PID: $!"
sleep 3
curl -s http://localhost:8080/api/healthz && echo ""
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ && echo " <- frontend"
