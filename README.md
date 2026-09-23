# Shopee Scout × SELEKT

**跨境电商选品工具链 · Cross-border e-commerce product-research toolkit**

[![Chrome Extension](https://img.shields.io/badge/Chrome-Extension-blue?logo=googlechrome)](https://chrome.google.com/webstore)
[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111%2B-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

**中文** · [English](#english)

---

## 中文

### 这是什么

从 Shopee 搜索页采集真实竞品数据 → 清洗打分 → 利润测算 → 导出/看板。全链路在本机运行，不依赖任何第三方数据服务。

仓库内有**两条产品线**，能力互补，不是新旧版本关系：

| | **A. Shopee Scout** | **B. SELEKT** |
|---|---|---|
| 位置 | 仓库根目录 + `extension/` | `selekt/` |
| 形态 | 采集扩展 + 单文件 Python 分析引擎 | 采集扩展 + 双 FastAPI 后端 + Web 看板 |
| 数据提取 | **三层**：API 拦截 → SSR 注入 → DOM 兜底 | DOM 单层 |
| 站点覆盖 | 8 个（含 `*.xiapibuy.com`） | 8 个 Shopee 官方域名 |
| 数据落点 | CSV / Excel 文件 | SQLite + Web 看板 + 定时任务 |
| 评分 | 毛利率 + 销量 + 风险分级 | 采集端 90 分制 + 分析端加权分制 |
| 适合 | 轻量、一次性选品调研 | 持续监控、多关键词日常运营 |

> 想要最强的数据抓取能力 → 用 **A** 的 `extension/`。
> 想要看板、定时采集、历史沉淀 → 用 **B** 的 `selekt/`。

---

### 快速开始

#### A. Shopee Scout

```bash
pip install openpyxl requests beautifulsoup4
python main.py                        # 跑示例数据
python main.py data/你的商品.csv       # 跑自己的数据
```

Chrome 扩展：`chrome://extensions` → 开启开发者模式 → 加载已解压的扩展 → 选 `extension/`

#### B. SELEKT

```bash
cd selekt
bash install.sh        # 一键装依赖 + 建虚拟环境 + 初始化授权
bash start.sh          # 同时启动两个后端
```

打开 **http://localhost:8002/ui**

Chrome 扩展：加载 `selekt/shopee-collector/`

> ⚠️ `install.sh` / `start.sh` / `stop.sh` 是 **macOS / Linux 专用**（依赖 `nohup`、`/tmp`、`pkill`、`.venv/bin/activate`）。Windows 请按 `selekt/shopee-backend/README.md` 的手动步骤用 `.venv\Scripts\activate` 启动。

---

### 核心技术

#### 1. 三层数据提取（`extension/content/`）

```
搜索页加载
    │
    ├─ 层1  API 拦截（优先）
    │      劫持 window.fetch / XMLHttpRequest，捕获 Shopee 内部
    │      search_items 响应 → 完整结构化数据（价格/销量/评分/库存/店铺）
    │      注意：价格在接口里以 ×100000 存储，需还原
    │
    ├─ 层2  SSR 嵌入式数据（备选）
    │      window.__INITIAL_STATE__ / __NEXT_DATA__ / application/json
    │
    └─ 层3  DOM 提取（兜底）
           多选择器兼容 data-sqe → class → aria-label
           跨域文本扫描：RM/₱/$ 价格格式 + sold/已售/terjual 销量格式
```

`xiapibuy.com` 是服务端渲染，`content_scripts` 注入不到 —— 用 `chrome.scripting.executeScript` 配合 `run_at: document_start` 在渲染前挂上钩子。

#### 2. 反反爬设计

| 方案 | 风险 | 维护成本 | 数据质量 |
|------|------|---------|---------|
| Selenium / Playwright 模拟浏览器 | 易被检测封 IP | 高 | 中 |
| requests 直接请求 | 403 拦截 | 高 | 低 |
| 第三方代理池 | 贵且不稳定 | 高 | 中 |
| **Chrome 扩展 + 用户自身会话** | **不触发 403** | **低** | **最高** |

扩展复用用户浏览器的 cookies 和会话，且**只做监听不改 DOM、不额外发请求**。Shopee 看到的请求与用户正常搜索无异。`selekt/shopee-backend/` 里的 Playwright 方案是另一条独立路径，指纹风险高于扩展。

#### 3. 两套评分引擎（`selekt/`）

- **采集端 · 规则加分制**（`shopee-backend/scraper.py`、`shopee-collector/content.js`）
  8 项加分，**实际满分 90**（不是 100），输出 `score` + 四档 verdict：强烈推荐 ≥80 / 可以测款 ≥70 / 谨慎考虑 ≥60 / 直接放弃。
- **分析端 · 加权分制**（`selekt-frontend/main.py`）
  `需求 40% + 竞争 30% + 物流 30%`，权重可运行时调整（和必须 = 1），输出 S/A/B/C 分级 + 利润率。

跨库导入时，采集端的 `score` 只用于 `min_score` 过滤，`verdict` 映射成 track/watch/pass；分析端会**重新算一套自己的分**。两者口径不同，不要直接比对。

#### 4. 利润计算器

支持 8 个市场的币种、价格分段、物流费、佣金率与汇率：

```
净利 = 售价 − (采购价 × 汇率 + 物流基础费 + 重量 × 每kg费 + 售价 × 佣金率)
并给出 20% / 30% / 40% 目标利润率对应的建议定价
```

---

### 目录结构

```
shopee-analyzer/
├── extension/                    A · 采集扩展（MV3，三层提取）
│   ├── manifest.json
│   ├── content/
│   │   ├── content.js            fetch/XHR API 拦截 + DOM 提取
│   │   └── extract.js            SSR → API → DOM 三层提取注入脚本
│   └── popup/
│       ├── popup.html
│       ├── popup.js              交互 + CSV 导出
│       └── popup.css
│
├── main.py                       A · 选品分析引擎
├── crawler.py                    A · Playwright 备用爬虫
├── exporter.py                   A · Excel / CSV 导出
├── product.py                    A · 数据模型
├── config.py                     A · 全局配置
├── data/template.csv             A · 数据模板
│
├── selekt/                       B · 全链路版
│   ├── install.sh                一键部署（Unix）
│   ├── start.sh / stop.sh / restart.sh
│   ├── license.py                授权模块（环境变量启用，未设置则停用）
│   ├── selekt-frontend/          分析后端 :8002 + Web 看板（7 页 SPA）
│   │   ├── main.py               30 个 API 端点
│   │   ├── index.html            单文件 SPA（内联 CSS+JS + Chart.js）
│   │   ├── markets.py            8 市场配置中心
│   │   └── requirements.txt
│   ├── shopee-backend/           采集后端 :8000
│   │   ├── main.py               19 个 API 端点
│   │   ├── scraper.py            Playwright + XHR 拦截 + 打分
│   │   ├── database.py           aiosqlite 异步数据层
│   │   ├── markets.py            与 selekt-frontend 同源
│   │   ├── templates/dashboard.html
│   │   └── requirements.txt
│   └── shopee-collector/         采集扩展（MV3）
│       ├── manifest.json
│       ├── background.js         Service Worker：轮询 → 认领 → 开 Tab
│       ├── content.js            DOM 采集 + 打分 + 回传
│       ├── relay.js              端口保活，防止 SW 休眠
│       └── popup/
│
├── .github/workflows/            Pylint
└── README.md
```

---

### 技术栈

| 层 | 技术 | 用途 |
|----|------|------|
| 数据采集 | Chrome Extension MV3 | 浏览器端数据捕获（两条产品线共用思路） |
| 脚本注入 | `chrome.scripting` API | SSR 页面动态注入 |
| 底层爬虫 | Playwright (Python) | 无头浏览器备用方案 |
| 分析后端 | FastAPI + SQLite | 选品评分、利润测算、看板 API |
| 采集后端 | FastAPI + aiosqlite + APScheduler | 采集调度、定时任务、SSE 进度推流 |
| 前端看板 | 原生 HTML/CSS/JS + Chart.js | 7 页单文件 SPA |
| 数据格式 | CSV / XLSX / SQLite | 兼容 Excel / WPS |
| 授权 | HMAC-SHA256 密钥 | 3 天试用 + 正式密钥 |

---

### SELEKT 授权说明

`selekt/license.py` **不含任何硬编码密钥**。从环境变量读取：

```bash
export SELEKT_LICENSE_SECRET="<你的密钥>"
# 生成密钥
python -c "import secrets;print(secrets.token_urlsafe(32))"

# 查看状态 / 生成授权密钥
python license.py
python license.py key <install_id> [有效天数]
```

- **未设置该变量** → 授权模块自动停用，所有 API 放行，可零配置运行。
- **已设置** → 启用 3 天试用；试用到期或密钥过期后，除授权相关端点外的所有 API 返回 `402`。

授权数据存于 `~/.selekt/`。

---

### 已知限制

诚实列出，避免误用：

1. **自动化采集目前只能跑台湾站。** 采集端 `pending-tasks` 已返回任务的 `market`，但派发端（`background.js`）尚未把 market 写进 URL，因此自动采集一律走 `shopee.tw`。手动采集的弹窗也只放行 `shopee.tw`。
2. **扩展端的价格解析对部分市场失效。** `selekt/shopee-collector/content.js` 的价格正则匹配美元符号，印尼（Rp）、泰国（฿）、越南（₫）取不到价格；且它的价格分段写死为台湾区间，与后端 `markets.price_score()` 不一致。**多市场采集请优先用 `extension/`（Shopee Scout）。**
3. **分析端的部分数据是演示值。** `dashboard/ai_insight`、`dashboard/ticker`、`competitors/summary`、`competitors/price_distribution`、`trend/*`、`radar/*` 均为硬编码 mock，尚未接入真实数据源。采集端 `shopee-backend` 的数据是真实的。
4. **两个 SQLite 库不随仓库分发**（已在 `selekt/.gitignore` 中忽略），首次启动自动建表。
5. **部署脚本是 Unix-only**，Windows 需按子目录 README 手动启动。
6. **`price_twd` 字段名在多市场下有歧义** —— 它实际存的是"当地币种售价"，非台湾站商品也会写进这一列，跨市场聚合统计时需注意。

---

### License

MIT — 欢迎 Fork、Star、提 Issue。

如需洽谈，请通过 GitHub Issues。

---

## English

### What this is

Scrape real competitor data from Shopee search pages → clean & score → profit modelling → export / dashboard. Everything runs locally, no third-party data service required.

This repo contains **two product lines**. They complement each other — they are not old and new versions of the same thing.

| | **A. Shopee Scout** | **B. SELEKT** |
|---|---|---|
| Location | repo root + `extension/` | `selekt/` |
| Shape | capture extension + single-file Python analysis engine | capture extension + two FastAPI backends + web dashboard |
| Extraction | **three layers**: API intercept → SSR injection → DOM fallback | DOM only |
| Sites | 8 domains incl. `*.xiapibuy.com` | 8 official Shopee domains |
| Output | CSV / Excel files | SQLite + web dashboard + scheduled jobs |
| Scoring | margin + sales + risk tier | 90-point rule score + weighted score |
| Best for | lightweight, one-off research | continuous monitoring, day-to-day ops |

> Want the strongest capture capability → use **A**'s `extension/`.
> Want a dashboard, scheduled collection and history → use **B**'s `selekt/`.

---

### Quick start

#### A. Shopee Scout

```bash
pip install openpyxl requests beautifulsoup4
python main.py                        # sample data
python main.py data/your_products.csv # your own data
```

Extension: `chrome://extensions` → enable Developer mode → Load unpacked → pick `extension/`

#### B. SELEKT

```bash
cd selekt
bash install.sh        # deps + venv + licence init
bash start.sh          # start both backends
```

Open **http://localhost:8002/ui**, then load `selekt/shopee-collector/` as an unpacked extension.

> ⚠️ `install.sh` / `start.sh` / `stop.sh` are **macOS / Linux only** (they rely on `nohup`, `/tmp`, `pkill` and `.venv/bin/activate`). On Windows, follow the manual steps in `selekt/shopee-backend/README.md` using `.venv\Scripts\activate`.

---

### Core techniques

#### 1. Three-layer extraction (`extension/content/`)

```
Search page loads
    │
    ├─ Layer 1  API intercept (preferred)
    │      Hook window.fetch / XMLHttpRequest, capture Shopee's internal
    │      search_items response → full structured data
    │      Note: prices are stored ×100000 in the API and must be scaled down
    │
    ├─ Layer 2  Embedded SSR data (fallback)
    │      window.__INITIAL_STATE__ / __NEXT_DATA__ / application/json
    │
    └─ Layer 3  DOM extraction (last resort)
           Multi-selector: data-sqe → class → aria-label
           Cross-locale text scan: RM/₱/$ price formats, sold/已售/terjual
```

`xiapibuy.com` is server-rendered, so `content_scripts` cannot attach — we inject via `chrome.scripting.executeScript` with `run_at: document_start`, hooking before render.

#### 2. Anti-anti-bot design

| Approach | Risk | Maintenance | Data quality |
|----------|------|-------------|--------------|
| Selenium / Playwright | detectable, IP bans | high | medium |
| Raw `requests` | 403 blocked | high | low |
| Proxy pools | costly, unstable | high | medium |
| **Chrome extension + user session** | **no 403** | **low** | **highest** |

The extension reuses the browser's own cookies and session, and **only listens — it never mutates the DOM and sends no extra requests**. Shopee sees exactly the traffic a normal search produces. The Playwright path inside `selekt/shopee-backend/` is a separate route with a higher fingerprinting risk.

#### 3. Two scoring engines (`selekt/`)

- **Capture side · additive rule score** (`shopee-backend/scraper.py`, `shopee-collector/content.js`)
  8 weighted items, **90 points actually achievable** (not 100). Emits `score` plus one of four verdicts: strongly recommend ≥80 / worth testing ≥70 / consider carefully ≥60 / skip.
- **Analysis side · weighted score** (`selekt-frontend/main.py`)
  `demand 40% + competition 30% + logistics 30%`, weights adjustable at runtime (must sum to 1). Emits an S/A/B/C grade plus margin.

On cross-database import, the capture-side `score` is only used as a `min_score` filter and `verdict` is mapped to track/watch/pass; the analysis side then **computes its own score from scratch**. The two are not directly comparable.

#### 4. Profit calculator

Currency, price tiers, shipping cost, commission and FX rate for 8 markets:

```
net = price − (source_price × fx + base_shipping + weight × per_kg + price × commission)
```

Also returns the price needed to hit 20% / 30% / 40% target margins.

---

### Repository layout

```
shopee-analyzer/
├── extension/                    A · capture extension (MV3, three-layer)
├── main.py                       A · product-research engine
├── crawler.py                    A · Playwright fallback crawler
├── exporter.py                   A · Excel / CSV export
├── product.py                    A · data model
├── config.py                     A · global config
├── data/template.csv             A · data template
│
├── selekt/                       B · full pipeline
│   ├── install.sh                one-click deploy (Unix)
│   ├── start.sh / stop.sh / restart.sh
│   ├── license.py                licence module (env-gated, off by default)
│   ├── selekt-frontend/          analysis backend :8002 + 7-page SPA
│   ├── shopee-backend/           capture backend :8000 + Playwright + scheduler
│   └── shopee-collector/         capture extension (MV3)
│
├── .github/workflows/            Pylint
└── README.md
```

---

### Tech stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Capture | Chrome Extension MV3 | in-browser data capture |
| Injection | `chrome.scripting` API | attach to SSR pages before render |
| Crawling | Playwright (Python) | headless browser fallback |
| Analysis API | FastAPI + SQLite | scoring, profit modelling, dashboard API |
| Capture API | FastAPI + aiosqlite + APScheduler | job scheduling, SSE progress streaming |
| Dashboard | vanilla HTML/CSS/JS + Chart.js | 7-page single-file SPA |
| Data formats | CSV / XLSX / SQLite | Excel / WPS compatible |
| Licensing | HMAC-SHA256 keys | 3-day trial + permanent keys |

---

### SELEKT licensing

`selekt/license.py` contains **no hard-coded secret**. It reads from the environment:

```bash
export SELEKT_LICENSE_SECRET="<your-secret>"
# generate one
python -c "import secrets;print(secrets.token_urlsafe(32))"

# check status / issue a key
python license.py
python license.py key <install_id> [days]
```

- **Variable unset** → licensing is disabled, every API is allowed, zero-config usage.
- **Variable set** → 3-day trial enforced; once the trial or key expires, all endpoints except the licence endpoints return `402`.

Licence data lives in `~/.selekt/`.

---

### Known limitations

Listed honestly so nothing gets misused:

1. **Automated collection currently only works on the Taiwan site.** The capture backend's `pending-tasks` endpoint does return each job's `market`, but the dispatcher (`background.js`) does not yet write it into the URL, so automated runs always hit `shopee.tw`. The manual popup is also gated to `shopee.tw`.
2. **The extension's price parsing fails on some markets.** The price regex in `selekt/shopee-collector/content.js` keys on the dollar sign, so Indonesia (Rp), Thailand (฿) and Vietnam (₫) yield no price; its price tiers are also hard-coded to Taiwan ranges and diverge from the backend's `markets.price_score()`. **For multi-market capture, prefer `extension/` (Shopee Scout).**
3. **Some analysis-side data is demo data.** `dashboard/ai_insight`, `dashboard/ticker`, `competitors/summary`, `competitors/price_distribution`, `trend/*` and `radar/*` are hard-coded mocks and not yet wired to real sources. Everything from the capture backend (`shopee-backend`) is real.
4. **The two SQLite databases are not shipped** (ignored in `selekt/.gitignore`); tables are created on first run.
5. **Deploy scripts are Unix-only**; on Windows start the services manually per the sub-directory READMEs.
6. **The `price_twd` column name is misleading for multi-market data** — it actually stores the local-currency price, and non-Taiwan products are written into that same column. Be careful when aggregating across markets.

---

### License

MIT — Fork, Star and Issues are all welcome.

For commercial enquiries, please open a GitHub Issue.

---

### Community

Originally built for a community of **200+ cross-border sellers**.

> **Show, don't just tell.**
> This is not a theoretical project — it is a production toolkit that runs daily in real e-commerce work.
