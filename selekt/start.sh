#!/usr/bin/env bash
# SELEKT 啟動腳本 — 同時啟動兩個後端服務
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
G='\033[0;32m'; Y='\033[1;33m'; B='\033[0;34m'; NC='\033[0m'

echo -e "\n${B}🚀 正在啟動 SELEKT...${NC}"

# SELEKT 主後端（port 8002）
cd "$ROOT/selekt-frontend"
source .venv/bin/activate
nohup uvicorn main:app --host 0.0.0.0 --port 8002 \
  > /tmp/selekt_main.log 2>&1 &
echo $! > /tmp/selekt_main.pid
deactivate

# Shopee 採集後端（port 8000）
cd "$ROOT/shopee-backend"
source .venv/bin/activate
nohup uvicorn main:app --host 0.0.0.0 --port 8000 \
  > /tmp/selekt_shopee.log 2>&1 &
echo $! > /tmp/selekt_shopee.pid
deactivate

sleep 2
echo ""
echo -e "${G}✅ SELEKT 已啟動！${NC}"
echo ""
echo -e "  ${Y}主介面   ${NC}→  http://localhost:8002/ui"
echo -e "  ${Y}採集後端 ${NC}→  http://localhost:8000"
echo -e "  ${Y}API 文檔 ${NC}→  http://localhost:8002/docs"
echo ""
echo -e "  查看日誌: ${Y}tail -f /tmp/selekt_main.log${NC}"
echo -e "  停止服務: ${Y}./stop.sh${NC}"
echo ""
