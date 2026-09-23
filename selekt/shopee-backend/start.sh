#!/bin/bash
# ──────────────────────────────────────────────────────────────────
#  Shopee 選品後端 - 一鍵啟動腳本
#  使用方式: bash start.sh
# ──────────────────────────────────────────────────────────────────

set -e
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${GREEN}🛍 Shopee 選品後端 啟動中...${NC}"

# 1. 檢查 Python 版本
if ! command -v python3 &>/dev/null; then
  echo "❌ 需要 Python 3.9+"; exit 1
fi
PY=$(python3 --version | awk '{print $2}')
echo "✅ Python $PY"

# 2. 建立虛擬環境（若不存在）
if [ ! -d ".venv" ]; then
  echo -e "${YELLOW}🔧 建立虛擬環境...${NC}"
  python3 -m venv .venv
fi
source .venv/bin/activate

# 3. 安裝依賴
echo -e "${YELLOW}📦 安裝依賴套件...${NC}"
pip install -r requirements.txt -q

# 4. 安裝 Playwright Chromium（只需執行一次）
if [ ! -d "$HOME/.cache/ms-playwright" ]; then
  echo -e "${YELLOW}🌐 安裝 Playwright Chromium（首次約 300MB）...${NC}"
  playwright install chromium
else
  echo "✅ Playwright Chromium 已安裝"
fi

# 5. 啟動伺服器
echo ""
echo -e "${GREEN}🚀 後端已啟動！${NC}"
echo -e "   看板網址: ${GREEN}http://localhost:8000${NC}"
echo -e "   API 文件: ${GREEN}http://localhost:8000/docs${NC}"
echo ""
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
