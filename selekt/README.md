# SELEKT · 全链路选品平台

[中文](#中文) · [English](#english)

---

## 中文

### 组成

```
浏览器                        本机
┌────────────────────┐   ┌──────────────────────┐
│ index.html SPA     │──▶│ selekt-frontend :8002 │──▶ selekt.db
│ (7 页看板)          │   │ 分析/评分/利润/看板     │    (5 表)
└────────────────────┘   └──────────▲───────────┘
                                    │ HTTP 导入
┌────────────────────┐   ┌──────────┴───────────┐
│ shopee-collector   │──▶│ shopee-backend  :8000 │──▶ data/shopee.db
│ (Chrome MV3 扩展)   │   │ 采集/调度/收藏         │    (4 表)
└────────────────────┘   └──────────────────────┘
```

| 模块 | 端口 | 职责 |
|------|:----:|------|
| `selekt-frontend/` | 8002 | 分析后端 + Web 看板（30 个 API 端点） |
| `shopee-backend/` | 8000 | 采集后端（19 个 API 端点，Playwright + APScheduler） |
| `shopee-collector/` | — | Chrome MV3 扩展，DOM 采集 |

### 启动

```bash
bash install.sh     # 装依赖、建 venv、初始化授权
bash start.sh       # 启动两个后端
bash stop.sh        # 停止
bash restart.sh     # 重启
```

启动后：

- 主界面 → http://localhost:8002/ui
- 分析 API 文档 → http://localhost:8002/docs
- 采集看板 → http://localhost:8000
- 采集 API 文档 → http://localhost:8000/docs

Chrome 扩展：`chrome://extensions` → 开发者模式 → 加载已解压的扩展 → 选 `shopee-collector/`

> **Windows 用户**：`install.sh` / `start.sh` 依赖 `nohup`、`/tmp`、`pkill`、`.venv/bin/activate`，无法在 Windows 运行。请分别进入两个目录，用 `.venv\Scripts\activate` 手动启动：
> ```powershell
> cd selekt-frontend
> python -m venv .venv; .\.venv\Scripts\activate
> pip install -r requirements.txt
> uvicorn main:app --host 0.0.0.0 --port 8002
> ```
> `shopee-backend` 同理（需额外 `playwright install chromium`）。

### 三条采集路径

| 路径 | 入口 | 机制 |
|------|------|------|
| A · 后端无头采集 | SPA「後端採集」→ `POST :8000/api/collect/start` | Playwright 打开搜索页，拦截 `search_items` XHR |
| B · 扩展自动采集（推荐） | SPA → `POST :8000/api/collect/trigger-ext` | 建 `pending_ext` 任务 → 扩展轮询认领（CAS）→ 开 Tab → content.js 采集回传 |
| C · 扩展手动采集 | 扩展弹窗「開始採集」 | 采集当前页 DOM，可导出 CSV，可同步到后端 |

任务状态机：`pending` → `running` → `done` / `failed`；扩展路径为 `pending_ext` → `running_ext` → `done` / `failed`。
卡住的 `pending_ext` / `running_ext` / `failed` 任务可调 `POST :8000/api/jobs/{id}/reset` 重置重跑。

### 授权

```bash
export SELEKT_LICENSE_SECRET="<你的密钥>"        # 不设置则授权模块停用，全功能放行
python license.py                                 # 查看状态与 install_id
python license.py key <install_id> [有效天数]      # 生成密钥，省略天数 = 永久
```

试用期 3 天。授权数据在 `~/.selekt/`。
`license.py` 在根目录与两个子模块各有一份**内容完全相同**的副本 —— 修改时三处必须同步（根目录那份是权威源）。

### 常见问题

| 现象 | 排查 |
|------|------|
| 看板空白 / API 全部失败 | 确认 8002 已启动：`curl http://localhost:8002/api/health`（采集端）或 `http://localhost:8002/` |
| 导入商品报 502 | 8000 未启动。导入需要两个后端**同时**运行 |
| 扩展同步失败 | `curl http://localhost:8000/api/health` 应返回 `{"status":"ok"}` |
| 扩展采集 0 件 | Shopee 页面结构可能已更新，检查 `content.js` 的选择器 |
| 自动采集一直跑台湾站 | 已知限制，见根目录 README「已知限制」第 1 条 |
| 直接双击 index.html 打不开数据 | `file://` 的 Origin 是 `null`，不在 CORS 白名单。改用 `http://localhost:8002/ui`，或设 `SELEKT_ALLOWED_ORIGINS="null"` |

---

## English

### Components

| Module | Port | Responsibility |
|--------|:----:|----------------|
| `selekt-frontend/` | 8002 | Analysis backend + web dashboard (30 endpoints) |
| `shopee-backend/` | 8000 | Capture backend (19 endpoints, Playwright + APScheduler) |
| `shopee-collector/` | — | Chrome MV3 extension, DOM capture |

### Run it

```bash
bash install.sh     # deps, venv, licence init
bash start.sh       # start both backends
bash stop.sh        # stop
bash restart.sh     # restart
```

- Dashboard → http://localhost:8002/ui
- Analysis API docs → http://localhost:8002/docs
- Capture dashboard → http://localhost:8000

> **Windows**: the shell scripts are Unix-only. Start each service manually inside its directory using `.venv\Scripts\activate` (and run `playwright install chromium` for `shopee-backend`).

### Three capture paths

| Path | Entry point | Mechanism |
|------|-------------|-----------|
| A · headless backend | SPA → `POST :8000/api/collect/start` | Playwright opens the search page and intercepts the `search_items` XHR |
| B · automated extension (recommended) | SPA → `POST :8000/api/collect/trigger-ext` | creates a `pending_ext` job → extension polls and claims it (CAS) → opens a tab → `content.js` captures and posts back |
| C · manual extension | popup 「開始採集」 | captures the current page's DOM; CSV export and backend sync available |

### Licensing

```bash
export SELEKT_LICENSE_SECRET="<your-secret>"     # unset = licensing disabled, everything allowed
python license.py                                # show status and install_id
python license.py key <install_id> [days]        # issue a key; omit days for permanent
```

3-day trial. Licence data lives in `~/.selekt/`.
`license.py` exists as three **byte-identical** copies (root and both sub-modules) — keep them in sync; the root copy is the source of truth.

### Troubleshooting

| Symptom | Check |
|---------|-------|
| Blank dashboard / all API calls fail | Is 8002 up? `curl http://localhost:8002/` |
| Import returns 502 | 8000 is not running. Import requires **both** backends |
| Extension sync fails | `curl http://localhost:8000/api/health` should return `{"status":"ok"}` |
| Extension captures 0 items | Shopee may have changed its page structure — check the selectors in `content.js` |
| Automated capture always hits the Taiwan site | Known limitation — see item 1 under "Known limitations" in the root README |
| Data missing when opening `index.html` directly | A `file://` origin is `null`, which is not in the CORS allowlist. Use `http://localhost:8002/ui` or set `SELEKT_ALLOWED_ORIGINS="null"` |
