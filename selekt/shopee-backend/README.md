# Shopee 選品後端系統

## 📐 系統架構

```
┌─────────────────────────────────────────────────┐
│              使用者操作介面                        │
├─────────────────┬───────────────────────────────┤
│  Chrome 擴充    │      瀏覽器看板                  │
│  (已採集數據)   │  http://localhost:8000          │
└────────┬────────┴───────────┬─────────────────── ┘
         │ POST /from-extension│ 操作看板
         ▼                    ▼
┌─────────────────────────────────────────────────┐
│         FastAPI 後端  (main.py)                  │
│  ┌──────────────┐  ┌──────────────────────────┐ │
│  │  REST API    │  │  APScheduler 定時採集     │ │
│  │  /api/*      │  │  cron 任務管理            │ │
│  └──────┬───────┘  └──────────┬───────────────┘ │
│         │                     │                  │
│  ┌──────▼─────────────────────▼───────────────┐ │
│  │         scraper.py (Playwright)             │ │
│  │         無頭 Chromium 瀏覽器採集             │ │
│  └─────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────┐ │
│  │         database.py (SQLite + aiosqlite)     │ │
│  │   collect_jobs / products / favorites /       │ │
│  │   schedules                                  │ │
│  └──────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

---

## 🚀 快速啟動

### 方法一：一鍵腳本（推薦）
```bash
bash start.sh
```

### 方法二：手動步驟
```bash
# 1. 建立虛擬環境
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. 安裝依賴
pip install -r requirements.txt

# 3. 安裝 Playwright Chromium
playwright install chromium

# 4. 啟動後端
uvicorn main:app --reload --port 8000
```

啟動後開啟瀏覽器前往：
- **看板**: http://localhost:8000
- **API 文件**: http://localhost:8000/docs

---

## 📁 檔案說明

| 檔案 | 說明 |
|------|------|
| `main.py` | FastAPI 主程式，所有 API 路由 |
| `database.py` | SQLite 資料層，CRUD 操作 |
| `scraper.py` | Playwright 採集器 + 選品打分邏輯 |
| `templates/dashboard.html` | 前端看板（單頁應用） |
| `data/shopee.db` | SQLite 資料庫（自動建立） |
| `requirements.txt` | Python 依賴 |
| `start.sh` | 一鍵啟動腳本 |

---

## 🔌 API 文件

### 採集相關

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/collect/start` | 啟動後端 Playwright 採集 |
| GET  | `/api/collect/progress/{job_id}` | SSE 進度串流 |
| POST | `/api/collect/from-extension` | 接收 Chrome 擴充數據 |

**範例：啟動採集**
```json
POST /api/collect/start
{
  "keyword": "收納盒",
  "max_products": 60
}
```

### 商品查詢

| 方法 | 路徑 | 參數 |
|------|------|------|
| GET | `/api/products` | `keyword`, `verdict`, `min_score`, `job_id`, `limit`, `offset` |
| GET | `/api/jobs` | `limit` |
| GET | `/api/stats` | — |

### 收藏

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/favorites/{product_id}` | 加入收藏 |
| GET | `/api/favorites` | 取得所有收藏 |
| DELETE | `/api/favorites/{fav_id}` | 刪除收藏 |

### 定時任務

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/schedules` | 新增定時任務 |
| GET | `/api/schedules` | 列出所有任務 |
| PATCH | `/api/schedules/{id}/toggle` | 啟用/停用 |
| DELETE | `/api/schedules/{id}` | 刪除任務 |

**Cron 表達式範例：**
```
0 9 * * *    每天早上 09:00
0 9 * * 1    每週一早上 09:00
0 9,18 * * * 每天早上9點和下午6點
0 */4 * * *  每4小時執行一次
```

---

## 🔗 Chrome 擴充整合

在 Chrome 擴充的 `popup.js` 採集完成後，呼叫以下代碼同步數據：

```javascript
const BACKEND = 'http://localhost:8000/api';

async function syncToBackend(products, keyword) {
  const resp = await fetch(`${BACKEND}/collect/from-extension`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keyword, products })
  });
  const data = await resp.json();
  console.log(`已同步 ${data.saved} 件商品，job_id: ${data.job_id}`);
}
```

---

## ⚠️ 注意事項

1. **首次執行** `playwright install chromium` 會下載約 300MB
2. **反爬機制**：若 Shopee 更新反爬，可能需要調整 `scraper.py` 中的等待時間
3. **本地使用**：後端預設監聽 `0.0.0.0:8000`，僅建議本地使用
4. **資料庫位置**：`data/shopee.db` 可用 DB Browser for SQLite 直接查看

---

## 🛠 常見問題

**Q: 採集失敗 / 找到 0 件商品？**
A: Shopee 頁面結構可能更新，嘗試調整 `scraper.py` 中的 CSS 選擇器

**Q: 啟動後看板顯示空白？**
A: 確認 `templates/dashboard.html` 存在，且 uvicorn 從 `shopee-backend/` 目錄啟動

**Q: Chrome 擴充無法同步？**
A: 確認後端已啟動（http://localhost:8000/api/health 應返回 `{"status":"ok"}`）
