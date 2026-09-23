# SELEKT 跨境選品平台 · 完整整合指南

## 📐 三層架構

```
┌─────────────────────────────────────────────────────────────┐
│                    瀏覽器端                                    │
│  ┌──────────────────────────┐  ┌────────────────────────┐  │
│  │   index.html (前端 SPA)  │  │  Chrome 擴充插件        │  │
│  │   5頁面完整看板           │  │  Shopee DOM 採集        │  │
│  └──────────┬───────────────┘  └─────────┬──────────────┘  │
│             │ API calls                  │ 同步數據          │
└─────────────┼──────────────────────────┬─┼───────────────────┘
              ▼                          │ ▼
┌─────────────────────────┐   ┌─────────────────────────┐
│  SELEKT 主後端           │   │  Shopee 採集後端          │
│  FastAPI  · port 8002   │   │  FastAPI  · port 8000   │
│  SQLite (selekt.db)     │   │  SQLite (shopee.db)     │
│  5頁面完整 API           │   │  Playwright 採集         │
└─────────────────────────┘   └─────────────────────────┘
```

---

## 🚀 啟動步驟

### 1. 安裝依賴（僅需一次）
```bash
cd selekt-frontend
pip install -r requirements.txt
playwright install chromium   # 可選，僅後端採集需要
```

### 2. 啟動主後端（必須）
```bash
uvicorn main:app --host 0.0.0.0 --port 8002 --reload
```

### 3. 前端訪問方式

**方式一：通過後端伺服器（推薦）**
```
啟動主後端後開啟 http://localhost:8002/ui
```

**方式二：直接開啟 HTML**
```
雙擊 index.html，或用瀏覽器直接開啟
```

> ⚠️ 直接開啟 `index.html` 時，瀏覽器送出的 `Origin` 是 `null`，
> 預設不在後端 CORS 白名單內，API 呼叫會被瀏覽器攔截。
> 如確實需要這種方式，請設置：
> ```bash
> export SELEKT_ALLOWED_ORIGINS="null"
> ```
> 或在 `.env` 中等效配置後重啟後端。

**方式三：啟動 Shopee 採集後端（可選）**
```bash
# 在另一個終端執行
cd shopee-collector-backend
uvicorn main:app --port 8000 --reload
```

---

## 🔌 API 對應表

| 前端頁面 | 調用的 API | 後端文件 |
|---------|-----------|---------|
| 儀表盤 | `/api/v1/dashboard/summary` `/ai_insight` `/ticker` `/products` | main.py |
| 選品雷達 | `/api/v1/radar/categories` `/bar_chart` `/spider` | main.py |
| 趨勢分析 | `/api/v1/trend/keywords` `/series` `/ranking` `/related` | main.py |
| 競品監控 | `/api/v1/competitors/summary` `/list` `/price_distribution` `/events` | main.py |
| 利潤計算器 | `/api/v1/profit/calculate` `/exchange_rate` | main.py |
| 商品採集 | `/api/v1/products` (POST/DELETE) `/api/v1/weights` | main.py |
| Chrome 擴充同步 | `/api/collect/from-extension` (可選) | shopee backend |

---

## 🔧 Chrome 擴充整合

擴充採集完成後，點擊「☁ 同步到後端」。擴充會呼叫：

```javascript
// Chrome 擴充 popup.js 中調用
fetch('http://localhost:8000/api/collect/from-extension', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({ keyword: kw, products: products })
});
```

SELEKT 前端側邊欄的「Chrome 擴充快速同步」區塊也可觸發同步信號。

---

## 📄 檔案清單

| 檔案 | 說明 |
|------|------|
| `index.html` | 完整前端 SPA（5頁面 + Chrome 擴充整合） |
| `main.py` | SELEKT 主後端（含 `/ui` 前端入口） |
| `requirements.txt` | Python 依賴 |
| `selekt.db` | SQLite 資料庫（自動建立） |
