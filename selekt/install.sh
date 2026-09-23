#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════
#  SELEKT 跨境選品智能平台 v2.2 — 一鍵部署腳本
#  用法: bash install.sh
# ════════════════════════════════════════════════════════════
set -e

# ── 顏色 ────────────────────────────────────────────────────
B='\033[1m'; G='\033[0;32m'; Y='\033[1;33m'
R='\033[0;31m'; C='\033[0;36m'; P='\033[0;35m'; NC='\033[0m'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

print_banner() {
cat << 'EOF'

  ███████╗███████╗██╗     ███████╗██╗  ██╗████████╗
  ██╔════╝██╔════╝██║     ██╔════╝██║ ██╔╝╚══██╔══╝
  ███████╗█████╗  ██║     █████╗  █████╔╝    ██║
  ╚════██║██╔══╝  ██║     ██╔══╝  ██╔═██╗    ██║
  ███████║███████╗███████╗███████╗██║  ██╗   ██║
  ╚══════╝╚══════╝╚══════╝╚══════╝╚═╝  ╚═╝   ╚═╝
       跨境選品智能平台 v2.2 — 一鍵部署

EOF
}

step() { echo -e "\n${C}[${1}/${TOTAL_STEPS}] ${2}${NC}"; }
ok()   { echo -e "  ${G}✓ ${1}${NC}"; }
warn() { echo -e "  ${Y}⚠ ${1}${NC}"; }
err()  { echo -e "  ${R}✗ ${1}${NC}"; exit 1; }

TOTAL_STEPS=6
print_banner

# ── Step 1: Python 環境檢查 ─────────────────────────────────
step 1 "檢查 Python 環境"

if ! command -v python3 &>/dev/null; then
  err "未找到 python3，請先安裝 Python 3.10+\n  macOS: brew install python3\n  Ubuntu: sudo apt install python3"
fi

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJ=$(echo "$PY_VER" | cut -d. -f1)
PY_MIN=$(echo "$PY_VER" | cut -d. -f2)

if [ "$PY_MAJ" -lt 3 ] || { [ "$PY_MAJ" -eq 3 ] && [ "$PY_MIN" -lt 10 ]; }; then
  err "Python 版本需要 ≥ 3.10（當前 ${PY_VER}）"
fi
ok "Python ${PY_VER}"

# ── Step 2: SELEKT 主後端依賴 (port 8002) ──────────────────
step 2 "安裝 SELEKT 主後端依賴（selekt-frontend）"

cd "$ROOT/selekt-frontend"
if [ ! -d ".venv" ]; then
  echo "  建立虛擬環境..."
  python3 -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
deactivate
ok "selekt-frontend 依賴安裝完成"

# ── Step 3: Shopee 採集後端依賴 (port 8000) ────────────────
step 3 "安裝 Shopee 採集後端依賴（shopee-backend）"

cd "$ROOT/shopee-backend"
if [ ! -d ".venv" ]; then
  echo "  建立虛擬環境..."
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
deactivate
ok "shopee-backend 依賴安裝完成"

# ── Step 4: 產生啟動與停止腳本 ─────────────────────────────
step 4 "產生 start.sh / stop.sh"

cd "$ROOT"

# ---- start.sh ------------------------------------------------
cat > start.sh << 'STARTEOF'
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
STARTEOF
chmod +x start.sh

# ---- stop.sh -------------------------------------------------
cat > stop.sh << 'STOPEOF'
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
STOPEOF
chmod +x stop.sh

# ---- restart.sh ----------------------------------------------
cat > restart.sh << 'RESTARTEOF'
#!/usr/bin/env bash
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$ROOT/stop.sh"
sleep 1
bash "$ROOT/start.sh"
RESTARTEOF
chmod +x restart.sh

ok "start.sh / stop.sh / restart.sh 已建立"

# ── Step 5: 初始化授權系統 ──────────────────────────────────
step 5 "初始化授權系統（3 天試用）"

cd "$ROOT"
LIC_INFO=$(python3 - << 'PYEOF'
import sys
sys.path.insert(0, 'selekt-frontend')
import license as lic
s = lic.get_status()
import math, datetime
exp = s.get('expires_at')
exp_str = datetime.datetime.fromtimestamp(exp).strftime('%Y-%m-%d %H:%M') if exp else 'N/A'
print(f"INSTALL_ID={s['install_id']}")
print(f"STATUS={s['status']}")
print(f"REMAINING={s['trial_remaining_days']}")
print(f"EXPIRES={exp_str}")
PYEOF
)

INSTALL_ID=$(echo "$LIC_INFO" | grep INSTALL_ID | cut -d= -f2-)
STATUS=$(echo "$LIC_INFO"     | grep ^STATUS=   | cut -d= -f2-)
EXPIRES=$(echo "$LIC_INFO"    | grep ^EXPIRES=  | cut -d= -f2-)

ok "授權系統初始化完成"
echo ""
echo -e "  ${P}安裝 ID  ${NC}: ${Y}${INSTALL_ID}${NC}"
echo -e "  ${P}試用狀態 ${NC}: ${G}${STATUS}${NC}"
echo -e "  ${P}到期時間 ${NC}: ${EXPIRES}"

# ── Step 6: Chrome 擴充安裝提示 ────────────────────────────
step 6 "Chrome 擴充安裝說明"
ok "擴充已就緒（shopee-collector/）"
echo ""
echo -e "  ${C}請依以下步驟安裝 Chrome 擴充：${NC}"
echo -e "  1. 開啟 ${Y}chrome://extensions/${NC}"
echo -e "  2. 右上角開啟「${Y}開發者模式${NC}」"
echo -e "  3. 點擊「${Y}載入未封裝項目${NC}」"
echo -e "  4. 選擇資料夾: ${Y}${ROOT}/shopee-collector${NC}"
echo ""

# ── 完成 ────────────────────────────────────────────────────
echo -e "${G}"
echo "  ╔════════════════════════════════════════╗"
echo "  ║  🎉  部署完成！                        ║"
echo "  ╚════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  執行 ${Y}./start.sh${NC} 啟動服務"
echo -e "  然後開啟 ${Y}http://localhost:8002/ui${NC}"
echo ""
echo -e "  ${P}需要授權密鑰？請執行:${NC}"
echo -e "  ${Y}python license.py key <安裝ID> [天數]${NC}"
echo -e "  ${P}（需先設置環境變數 SELEKT_LICENSE_SECRET）${NC}"
echo ""
