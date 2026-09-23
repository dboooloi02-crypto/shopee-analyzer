#!/usr/bin/env bash
# SELEKT 停止腳本
G='\033[0;32m'; Y='\033[1;33m'; NC='\033[0m'
echo -e "\n${Y}⏹  正在停止 SELEKT 服務...${NC}"

stopped=0
for PID_FILE in /tmp/selekt_main.pid /tmp/selekt_shopee.pid; do
  if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill "$PID" 2>/dev/null; then
      echo -e "  ${G}✓ 已停止進程 PID=${PID}${NC}"
      ((stopped++))
    fi
    rm -f "$PID_FILE"
  fi
done

# 兜底：殺掉所有 uvicorn 進程
pkill -f "uvicorn main:app" 2>/dev/null && ((stopped++)) || true

echo -e "${G}✅ 服務已停止（共 ${stopped} 個進程）${NC}\n"
