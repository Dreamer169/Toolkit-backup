#!/bin/bash
set -e
cd /workspaces/Toolkit
PORT=3000 pnpm --filter ai-toolkit run build
pnpm --filter api-server run build
PORT=8080 NODE_ENV=production nohup node --enable-source-maps artifacts/api-server/dist/index.mjs > /tmp/server.log 2>&1 &
sleep 3
curl -s http://localhost:8080/api/healthz && echo "" && echo "SUCCESS"
