"""
SELEKT Backend v2.2
FastAPI · SQLite · 五页面完整接口
对应前端: 仪表盘 / 选品雷达 / 趋势分析 / 竞品监控 / 利润计算器
"""

from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Literal
import sqlite3, time, math, os, json, urllib.request, urllib.parse
import markets as mkt

# ── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="SELEKT API", version="2.2.0", docs_url="/docs")

# ── 授權中間件（必須在 CORS 之前注冊，OPTIONS 預檢由 CORS 處理，
#    其餘請求先過授權再往下走）───────────────────────────────────────────────
import license as _lic

@app.middleware("http")
async def _license_guard(request: Request, call_next):
    """試用到期後封鎖所有非授權 API"""
    path = request.url.path
    _whitelist = ("/api/license", "/ui", "/docs", "/openapi.json")
    if (request.method == "OPTIONS"
            or path == "/"
            or any(path.startswith(w) for w in _whitelist)):
        return await call_next(request)
    s = _lic.get_status()
    if s["status"] in ("trial_expired", "key_expired"):
        return JSONResponse(
            {"error": "license_expired",
             "message": "試用期已結束，請輸入授權密鑰解鎖",
             "install_id": s["install_id"]},
            status_code=402
        )
    return await call_next(request)

# ── CORS（收緊：只允許本機前端，生產環境按需修改 SELEKT_ALLOWED_ORIGINS）──
_allowed_origins = os.environ.get(
    "SELEKT_ALLOWED_ORIGINS",
    "http://localhost:8002,http://127.0.0.1:8002"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# ── DB ──────────────────────────────────────────────────────────────────────

DB = "selekt.db"

from contextlib import contextmanager

@contextmanager
def get_conn():
    """Context manager that commits/rolls back AND closes the connection."""
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()

def init_db():
    with get_conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            name              TEXT NOT NULL,
            category          TEXT NOT NULL,
            price_twd         REAL NOT NULL,
            monthly_sales     INTEGER DEFAULT 0,
            review_count      INTEGER DEFAULT 0,
            avg_rating        REAL    DEFAULT 4.5,
            competitor_count  INTEGER DEFAULT 50,
            weight_kg         REAL    DEFAULT 0.5,
            logistics_class   TEXT    DEFAULT 'small',
            source_price_cny  REAL    NOT NULL,
            status            TEXT    DEFAULT 'track',
            created_at        INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS weights (
            id          INTEGER PRIMARY KEY CHECK (id=1),
            demand      REAL DEFAULT 0.40,
            competition REAL DEFAULT 0.30,
            logistics   REAL DEFAULT 0.30,
            updated_at  INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS competitors (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_name   TEXT NOT NULL,
            category    TEXT NOT NULL,
            score       INTEGER DEFAULT 60,
            market_share REAL DEFAULT 10.0,
            delta_pct   REAL DEFAULT 0.0,
            delta_up    INTEGER DEFAULT 1,
            created_at  INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS comp_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_name   TEXT NOT NULL,
            event_type  TEXT NOT NULL,
            product     TEXT NOT NULL,
            detail      TEXT DEFAULT '',
            happened_at INTEGER DEFAULT (strftime('%s','now'))
        );
        INSERT OR IGNORE INTO weights (id) VALUES (1);
        """)
        _migrate_products(c)
        _seed(c)


def _migrate_products(c):
    """為 products 表追加採集導入所需欄位（冪等，可重複執行）"""
    cols = {r["name"] for r in c.execute("PRAGMA table_info(products)").fetchall()}
    if "source" not in cols:
        c.execute("ALTER TABLE products ADD COLUMN source TEXT DEFAULT 'manual'")
    if "shopee_product_id" not in cols:
        c.execute("ALTER TABLE products ADD COLUMN shopee_product_id INTEGER")
    # 同一筆採集商品只導入一次（shopee_product_id 為 NULL 的手動商品不受影響）
    c.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_products_shopee_id "
        "ON products(shopee_product_id) WHERE shopee_product_id IS NOT NULL"
    )

def _seed(c):
    if c.execute("SELECT COUNT(*) FROM products").fetchone()[0] > 0:
        return

    c.executemany(
        "INSERT INTO products (name,category,price_twd,monthly_sales,review_count,"
        "avg_rating,competitor_count,weight_kg,logistics_class,source_price_cny,status)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("不鏽鋼三層浴室收納架","收納",189,420,186,4.7,87,1.2,"medium",25,"track"),
            ("矽膠密封保鮮盒 6件組","廚房",259,310,240,4.5,142,0.8,"small",35,"track"),
            ("北歐風鞋架 五層可調",  "收納",349,380,155,4.6, 65,2.5,"large", 60,"track"),
            ("無痕掛鉤 304不鏽鋼 10入","浴室",129,520,310,4.8,198,0.3,"small", 8,"watch"),
            ("珪藻土腳踏墊 速乾吸水","浴室",199,390,178,4.7, 73,1.5,"medium",30,"track"),
            ("廚房紙巾架 磁吸壁掛式","廚房",149,280,120,4.4, 55,0.4,"small", 12,"watch"),
            ("折疊曬衣架 不鏽鋼加粗","收納",299,245, 98,4.5, 44,1.8,"medium",45,"pass"),
        ]
    )

    c.executemany(
        "INSERT INTO competitors (shop_name,category,score,market_share,delta_pct,delta_up)"
        " VALUES (?,?,?,?,?,?)",
        [
            ("愛美家旗艦店", "收納·廚房", 78, 24.0,  3.0, 1),
            ("居家好物直營", "浴室·收納", 72, 18.0, -2.0, 0),
            ("台灣好物嚴選", "全品類",    68, 15.0,  1.0, 1),
            ("收納達人店",   "收納專營",  65, 12.0,  5.0, 1),
            ("生活質感小舖", "廚房·浴室", 61,  9.0, -4.0, 0),
        ]
    )

    now = int(time.time())
    c.executemany(
        "INSERT INTO comp_events (shop_name,event_type,product,detail,happened_at)"
        " VALUES (?,?,?,?,?)",
        [
            ("愛美家旗艦店", "price_down", "不鏽鋼三層架",    "降價 NT$30",        now - 600),
            ("居家好物直營", "new_product","矽膠密封盒組合",   "新品上架",          now - 3600),
            ("台灣好物嚴選", "rating_drop","浴室置物架",       "評分 4.5→4.1",     now - 10800),
            ("收納達人店",   "restock",    "折疊鞋架",         "大量補貨",          now - 18000),
        ]
    )

init_db()

# ── Scoring Engine ───────────────────────────────────────────────────────────

def get_wt() -> dict:
    with get_conn() as c:
        r = c.execute("SELECT demand,competition,logistics FROM weights WHERE id=1").fetchone()
        return dict(r)

def s_demand(sales, reviews, rating) -> float:
    return round(min(sales/500*60, 60) + min(reviews/200*25, 25) + (rating/5)*15, 1)

def s_comp(competitors, rating) -> float:
    base = 90 if competitors<=20 else 75 if competitors<=50 else 60 if competitors<=100 else 45 if competitors<=200 else 30
    if rating < 4.3: base += 10
    elif rating > 4.8: base -= 5
    return round(min(max(base, 0), 100), 1)

def s_logi(weight, lclass, price) -> float:
    base = {"small": 95, "medium": 70, "large": 40}.get(lclass, 50)
    if price >= 200: base += 5
    elif price < 100: base -= 10
    if weight > 2: base -= 15
    elif weight < 0.5: base += 5
    return round(min(max(base, 0), 100), 1)

def profit_rate(price, source_cny, weight,
                lclass: str = "medium",
                comm_rate: float = 5.0,
                fx: float = 4.4) -> float:
    cost_twd  = source_cny * fx
    logi_base = {"small": 20, "medium": 35, "large": 60}.get(lclass, 35)
    logi_twd  = logi_base + weight * 20
    comm_twd  = price * comm_rate / 100
    total     = cost_twd + logi_twd + comm_twd
    return round((price - total) / price * 100 if price else 0, 1)

def grade(score) -> str:
    return "S" if score >= 85 else "A" if score >= 75 else "B" if score >= 65 else "C"

def enrich(row: dict, w: dict = None) -> dict:
    if w is None:
        w = get_wt()
    d = s_demand(row["monthly_sales"], row["review_count"], row["avg_rating"])
    c = s_comp(row["competitor_count"], row["avg_rating"])
    l = s_logi(row["weight_kg"], row["logistics_class"], row["price_twd"])
    p = profit_rate(row["price_twd"], row["source_price_cny"], row["weight_kg"],
                    row.get("logistics_class", "medium"))
    total = round(d*w["demand"] + c*w["competition"] + l*w["logistics"], 1)
    return {**row, "score_demand": d, "score_competition": c,
            "score_logistics": l, "profit_rate": p,
            "score_total": total, "grade": grade(total)}

def _rng(seed_str: str):
    """可复现的伪随机数生成器"""
    seed = sum(ord(ch) for ch in seed_str) * 1234567
    def rand(n):
        nonlocal seed
        seed = (seed * 1664525 + 1013904223) & 0xFFFFFFFF
        return abs(seed) % n
    return rand

# ── Models ───────────────────────────────────────────────────────────────────

class ProductCreate(BaseModel):
    name: str
    category: str
    price_twd: float          = Field(gt=0)
    monthly_sales: int        = Field(ge=0)
    review_count: int         = Field(ge=0)
    avg_rating: float         = Field(ge=1, le=5)
    competitor_count: int     = Field(ge=0)
    weight_kg: float          = Field(ge=0)
    logistics_class: Literal["small","medium","large"]
    source_price_cny: float   = Field(ge=0)
    status: Literal["track","watch","pass"] = "track"


class ProductUpdate(BaseModel):
    """局部更新（僅更新有提供的欄位），用於補填採集導入後缺失的採購資訊"""
    name: Optional[str]              = None
    category: Optional[str]          = None
    price_twd: Optional[float]       = Field(None, gt=0)
    monthly_sales: Optional[int]     = Field(None, ge=0)
    review_count: Optional[int]      = Field(None, ge=0)
    avg_rating: Optional[float]      = Field(None, ge=1, le=5)
    competitor_count: Optional[int]  = Field(None, ge=0)
    weight_kg: Optional[float]       = Field(None, ge=0)
    logistics_class: Optional[Literal["small","medium","large"]] = None
    source_price_cny: Optional[float] = Field(None, ge=0)
    status: Optional[Literal["track","watch","pass"]] = None

class WeightsUpdate(BaseModel):
    demand: float      = Field(ge=0, le=1)
    competition: float = Field(ge=0, le=1)
    logistics: float   = Field(ge=0, le=1)

class ProfitCalcInput(BaseModel):
    price_local:      float = Field(gt=0, description="當地售價（以市場幣種計）")
    source_price_cny: float = Field(gt=0, description="採購價 CNY")
    weight_kg:        float = Field(gt=0, description="重量 kg")
    logistics_class:  Literal["small","medium","large"] = "medium"
    commission_rate:  float = Field(default=5.0, ge=0, le=30, description="平台佣金率 %")
    exchange_rate:    float = Field(default=4.4, gt=0, description="CNY→當地幣匯率")
    market:           str   = Field(default="tw", description="市場代碼")

# ═══════════════════════════════════════════════════════════════════════════
# 页面 1：仪表盘
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {"service": "SELEKT", "version": "2.2.0", "status": "online"}


@app.get("/api/v1/dashboard/summary",
         summary="仪表盘 · 4个指标卡",
         tags=["仪表盘"])
def dashboard_summary():
    with get_conn() as c:
        w = dict(c.execute("SELECT demand,competition,logistics FROM weights WHERE id=1").fetchone())
        rows = [enrich(dict(r), w) for r in c.execute("SELECT * FROM products").fetchall()]
    total  = len(rows)
    high   = sum(1 for r in rows if r["score_total"] >= 75)
    avg_px = round(sum(r["price_twd"] for r in rows) / total) if total else 0
    avg_pr = round(sum(r["profit_rate"] for r in rows) / total, 1) if total else 0
    return {
        "total_products":   total,
        "high_score_count": high,
        "avg_price_twd":    avg_px,
        "avg_profit_rate":  avg_pr,
        "timestamp":        int(time.time()),
    }


@app.get("/api/v1/dashboard/ai_insight",
         summary="仪表盘 · AI 洞察条",
         tags=["仪表盘"])
def dashboard_ai_insight():
    """
    返回 AI 洞察文本和置信度。
    注意：当前为 mock 数据，生产环境替换为实际 LLM 调用。
    """
    return {
        "text": "本周不锈钢分层收纳架搜索热度上涨34%，竞品数量仅87个，建议优先布局。"
                "密封保鲜盒竞争加剧，新卖家入场需谨慎。"
                "浴室挂钩近30天评分均值4.7，复购率优异。",
        "model":      "mock",
        "source":     "mock",
        "confidence": 91,
        "generated_at": int(time.time()),
    }


@app.get("/api/v1/dashboard/ticker",
         summary="仪表盘 · 底部滚动条",
         tags=["仪表盘"])
def dashboard_ticker():
    items = [
        {"name": "不鏽鋼收納架",  "change": 34,  "up": True},
        {"name": "矽膠保鮮盒",    "change": 12,  "up": True},
        {"name": "密封罐組合",    "change": -8,  "up": False},
        {"name": "北歐鞋架",      "change": 21,  "up": True},
        {"name": "珪藻土地墊",    "change": 18,  "up": True},
        {"name": "廚房掛鉤",      "change":  7,  "up": True},
        {"name": "折疊衣架",      "change": -3,  "up": False},
        {"name": "浴室置物架",    "change": 29,  "up": True},
    ]
    return {"items": items, "source": "mock", "timestamp": int(time.time())}


@app.get("/api/v1/products",
         summary="仪表盘 · 商品列表",
         tags=["仪表盘"])
def list_products(
    category:  Optional[str]            = None,
    status:    Optional[str]            = None,
    min_score: float                     = Query(0,   ge=0, le=100),
    sort:      str                       = Query("score_total"),
    order:     Literal["asc","desc"]    = "desc",
    limit:     int                       = Query(50,  le=200),
    offset:    int                       = Query(0,   ge=0),
):
    with get_conn() as c:
        w = dict(c.execute("SELECT demand,competition,logistics FROM weights WHERE id=1").fetchone())
        rows = [enrich(dict(r), w) for r in c.execute("SELECT * FROM products").fetchall()]
    if category: rows = [r for r in rows if r["category"] == category]
    if status:   rows = [r for r in rows if r["status"]   == status]
    rows = [r for r in rows if r["score_total"] >= min_score]
    valid = {"score_total","score_demand","score_competition","score_logistics","profit_rate","price_twd"}
    if sort in valid:
        rows.sort(key=lambda x: x.get(sort, 0), reverse=(order == "desc"))
    return {"total": len(rows), "data": rows[offset:offset+limit], "offset": offset, "limit": limit}


@app.post("/api/v1/products", status_code=201, tags=["仪表盘"])
def create_product(body: ProductCreate):
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO products (name,category,price_twd,monthly_sales,review_count,"
            "avg_rating,competitor_count,weight_kg,logistics_class,source_price_cny,status)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (body.name, body.category, body.price_twd, body.monthly_sales, body.review_count,
             body.avg_rating, body.competitor_count, body.weight_kg,
             body.logistics_class, body.source_price_cny, body.status)
        )
        row = dict(c.execute("SELECT * FROM products WHERE id=?", (cur.lastrowid,)).fetchone())
    return enrich(row)


@app.get("/api/v1/products/{pid}", tags=["仪表盘"])
def get_product(pid: int):
    with get_conn() as c:
        row = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not row:
        raise HTTPException(404, "商品不存在")
    return enrich(dict(row))


@app.delete("/api/v1/products/{pid}", status_code=204, tags=["仪表盘"])
def delete_product(pid: int):
    with get_conn() as c:
        row = c.execute("SELECT id FROM products WHERE id=?", (pid,)).fetchone()
        if not row:
            raise HTTPException(404, "商品不存在")
        c.execute("DELETE FROM products WHERE id=?", (pid,))


@app.put("/api/v1/products/{pid}",
         summary="仪表盘 · 編輯商品（補充採購價/重量等）",
         tags=["仪表盘"])
def update_product(pid: int, body: ProductUpdate):
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(400, "未提供任何更新欄位")
    with get_conn() as c:
        row = c.execute("SELECT id FROM products WHERE id=?", (pid,)).fetchone()
        if not row:
            raise HTTPException(404, "商品不存在")
        set_clause = ",".join(f"{k}=?" for k in fields)
        c.execute(f"UPDATE products SET {set_clause} WHERE id=?",
                  (*fields.values(), pid))
        row = dict(c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone())
    return enrich(row)


# ═══════════════════════════════════════════════════════════════════════════
# 從 Shopee 採集後端（埠 8000）導入商品到分析資料庫
# ═══════════════════════════════════════════════════════════════════════════

SHOPEE_BACKEND_URL = os.environ.get("SHOPEE_BACKEND_URL", "http://localhost:8000")

# 採集端 verdict → 分析端 status 對照
_VERDICT_STATUS = {
    "強烈推薦": "track",
    "可以測款": "track",
    "謹慎考慮": "watch",
    "直接放棄": "pass",
}


class ImportFromShopee(BaseModel):
    job_id:    Optional[int] = Field(None, description="僅導入此採集任務(job_id)的商品；留空則導入全部任務")
    keyword:   Optional[str] = Field(None, description="僅導入此關鍵字採集到的商品；留空則導入全部")
    min_score: int            = Field(0, ge=0, le=100, description="只導入評分 ≥ 此值的商品")
    limit:     int            = Field(1000, ge=1, le=5000)


@app.post("/api/v1/import/from-shopee",
          summary="從採集後端（埠 8000）導入商品到分析資料庫",
          tags=["導入"])
def import_from_shopee(body: ImportFromShopee = ImportFromShopee()):
    params = {"min_score": body.min_score, "limit": body.limit}
    if body.keyword:
        params["keyword"] = body.keyword
    if body.job_id:
        params["job_id"] = body.job_id
    url = f"{SHOPEE_BACKEND_URL}/api/products?" + urllib.parse.urlencode(params)

    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise HTTPException(502, f"無法連接採集後端（埠 8000）：{e}")

    items = data.get("products", [])
    imported, skipped, junk = 0, 0, 0

    with get_conn() as c:
        for p in items:
            sid = p.get("id")
            if sid is not None:
                exists = c.execute(
                    "SELECT 1 FROM products WHERE shopee_product_id=?", (sid,)
                ).fetchone()
                if exists:
                    skipped += 1
                    continue

            name     = (p.get("name") or "未命名商品").strip()
            category = (p.get("keyword") or "未分類").strip() or "未分類"
            price    = p.get("price") or 0

            # 真正的商品必有售價；price<=0 多為廣告/優惠角標等誤抓資料，跳過不導入
            if price <= 0:
                junk += 1
                continue

            rating = p.get("rating") or 4.5
            rating = min(max(rating, 1), 5)

            status = _VERDICT_STATUS.get(p.get("verdict"), "track")

            c.execute(
                "INSERT INTO products (name,category,price_twd,monthly_sales,review_count,"
                "avg_rating,competitor_count,weight_kg,logistics_class,source_price_cny,"
                "status,source,shopee_product_id)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (name, category, price,
                 p.get("sales", 0) or 0,
                 p.get("rating_count", 0) or 0,
                 rating,
                 50,             # competitor_count：暫用預設值，可在仪表盘手動修改
                 0,               # weight_kg：待補充
                 "medium",
                 0,               # source_price_cny：待補充
                 status, "shopee_import", sid)
            )
            imported += 1

    return {"imported": imported, "skipped": skipped, "junk": junk, "total": len(items)}


@app.post("/api/v1/import/cleanup-junk",
          summary="清除先前誤導入的垃圾資料（廣告/優惠角標，price_twd<=1 且 source=shopee_import）",
          tags=["導入"])
def cleanup_junk_imports():
    with get_conn() as c:
        rows = c.execute(
            "SELECT id FROM products WHERE source='shopee_import' AND price_twd<=1"
        ).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            c.execute(
                "DELETE FROM products WHERE source='shopee_import' AND price_twd<=1"
            )
    return {"deleted": len(ids)}


# ═══════════════════════════════════════════════════════════════════════════
# 页面 2：选品雷达
# ═══════════════════════════════════════════════════════════════════════════

CATEGORY_META = {
    "收納": {"sub": "收納架·置物架·衣架", "demand": 88, "competition": 62, "logistics": 85, "profit": 34},
    "廚房": {"sub": "保鮮盒·掛鉤·紙巾架", "demand": 72, "competition": 74, "logistics": 78, "profit": 28},
    "浴室": {"sub": "掛鉤·置物架·地墊",   "demand": 83, "competition": 55, "logistics": 72, "profit": 36},
    "鞋架": {"sub": "多層·折疊·門口",     "demand": 68, "competition": 40, "logistics": 65, "profit": 29},
    "地墊": {"sub": "珪藻土·PVC·棉麻",    "demand": 85, "competition": 49, "logistics": 88, "profit": 36},
    "掛鉤": {"sub": "無痕·不鏽鋼·黏貼",   "demand": 91, "competition": 84, "logistics": 90, "profit": 42},
}

def _cat_score(meta: dict) -> float:
    w = get_wt()
    return round(
        meta["demand"]      * w["demand"] +
        (100 - meta["competition"]) * w["competition"] +
        meta["logistics"]   * w["logistics"],
        1
    )

@app.get("/api/v1/radar/categories",
         summary="选品雷达 · 六大类目卡片",
         tags=["选品雷达"])
def radar_categories():
    result = []
    for name, meta in CATEGORY_META.items():
        score = _cat_score(meta)
        if score >= 80:
            verdict, vcls = "强烈推荐", "good"
        elif score >= 70:
            verdict, vcls = "可以入场", "good"
        elif score >= 60:
            verdict, vcls = "建议观望", "warn"
        else:
            verdict, vcls = "竞争激烈", "warn"
        result.append({
            "name":        name,
            "sub":         meta["sub"],
            "score":       score,
            "demand":      meta["demand"],
            "competition": meta["competition"],
            "logistics":   meta["logistics"],
            "profit":      meta["profit"],
            "verdict":     verdict,
            "verdict_cls": vcls,
        })
    result.sort(key=lambda x: x["score"], reverse=True)
    return {"data": result}


@app.get("/api/v1/radar/bar_chart",
         summary="选品雷达 · 柱状图数据",
         tags=["选品雷达"])
def radar_bar_chart():
    labels, scores, comps = [], [], []
    for name, meta in CATEGORY_META.items():
        labels.append(name)
        scores.append(_cat_score(meta))
        comps.append(meta["competition"])
    return {"labels": labels, "score_total": scores, "competition": comps}


@app.get("/api/v1/radar/spider",
         summary="选品雷达 · 蛛网图数据",
         tags=["选品雷达"])
def radar_spider():
    labels = list(CATEGORY_META.keys())
    demand = [CATEGORY_META[k]["demand"]      for k in labels]
    comp   = [CATEGORY_META[k]["competition"] for k in labels]
    return {"labels": labels, "demand": demand, "competition": comp}


# ═══════════════════════════════════════════════════════════════════════════
# 页面 3：趋势分析
# ═══════════════════════════════════════════════════════════════════════════

TREND_KEYWORDS = ["收納","廚房","浴室","地墊","鞋架","掛鉤","保鮮盒"]

def _gen_trend(keyword: str, days: int) -> list[float]:
    rng  = _rng(keyword)
    base = 45 + rng(25)
    pts  = []
    for i in range(days):
        val = base + rng(12) - 4 + i * 0.6
        pts.append(round(min(val, 100), 1))
    return pts


@app.get("/api/v1/trend/keywords",
         summary="趋势分析 · 关键词列表",
         tags=["趋势分析"])
def trend_keywords():
    return {"keywords": TREND_KEYWORDS}


@app.get("/api/v1/trend/series",
         summary="趋势分析 · 折线图 + 统计卡",
         tags=["趋势分析"])
def trend_series(
    keyword: str = Query("收纳"),
    days:    int = Query(30, ge=7, le=90),
):
    """注意：趋势数据为 mock，生产环境替换为真实搜索热度 API。"""
    pts   = _gen_trend(keyword, days)
    first = pts[0]
    last  = pts[-1]
    peak  = max(pts)
    chg   = round((last - first) / first * 100, 1) if first else 0
    if chg >= 20:   trend_grade = "↑↑ 热"
    elif chg >= 5:  trend_grade = "↑ 升"
    elif chg >= -5: trend_grade = "→ 稳"
    else:           trend_grade = "↓ 降"
    return {
        "keyword":     keyword,
        "days":        days,
        "source":      "mock",
        "series":      [{"day": i+1, "value": v} for i, v in enumerate(pts)],
        "current":     last,
        "change_pct":  chg,
        "peak":        peak,
        "trend_grade": trend_grade,
    }


@app.get("/api/v1/trend/ranking",
         summary="趋势分析 · 热度排行 TOP N",
         tags=["趋势分析"])
def trend_ranking(top: int = Query(5, ge=1, le=20)):
    result = []
    for kw in TREND_KEYWORDS:
        pts = _gen_trend(kw, 30)
        chg = round((pts[-1] - pts[0]) / pts[0] * 100, 1) if pts[0] else 0
        result.append({"keyword": kw, "score": pts[-1], "change_pct": chg, "up": chg >= 0})
    result.sort(key=lambda x: x["score"], reverse=True)
    return {"data": result[:top]}


@app.get("/api/v1/trend/related",
         summary="趋势分析 · 关联词推荐",
         tags=["趋势分析"])
def trend_related(keyword: str = Query("收纳")):
    related_map = {
        "收納":  ["不鏽鋼收納","層架組合","可調層架","牆上置物","DIY層板","分格收納"],
        "廚房":  ["廚房置物架","保鮮罐","瀝水架","調味料架","砧板架","刀架"],
        "浴室":  ["浴室置物架","防水掛鉤","牙刷架","毛巾架","鏡前燈","沐浴收納"],
        "地墊":  ["珪藻土地墊","吸水地墊","防滑墊","腳踏墊","入門地墊","廚房地墊"],
        "鞋架":  ["折疊鞋架","門口鞋架","防塵鞋盒","鞋櫃","旋轉鞋架","透明鞋盒"],
        "掛鉤":  ["無痕掛鉤","黏貼掛鉤","不鏽鋼掛鉤","S型掛鉤","多功能掛鉤","掛衣鉤"],
        "保鮮盒":["密封保鮮盒","玻璃保鮮盒","不鏽鋼便當盒","真空保鮮","冷凍分裝盒","副食品盒"],
    }
    words = related_map.get(keyword, ["收納", "置物架", "整理盒", "掛鉤", "地墊"])
    return {"keyword": keyword, "related": words}


# ═══════════════════════════════════════════════════════════════════════════
# 页面 4：竞品监控
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/v1/competitors/summary",
         summary="竞品监控 · 3个指标卡",
         tags=["竞品监控"])
def comp_summary():
    return {
        "monitored_products": 34,
        "price_changes":       7,
        "new_competitors":    12,
        "source":             "mock",
        "timestamp":          int(time.time()),
    }


@app.get("/api/v1/competitors/list",
         summary="竞品监控 · 主要竞品排行",
         tags=["竞品监控"])
def comp_list(
    category: Optional[str] = None,
    limit: int = Query(10, le=50),
):
    with get_conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM competitors ORDER BY market_share DESC").fetchall()]
    if category:
        rows = [r for r in rows if category in r["category"]]
    return {"total": len(rows), "data": rows[:limit]}


@app.get("/api/v1/competitors/price_distribution",
         summary="竞品监控 · 价格区间分布",
         tags=["竞品监控"])
def comp_price_dist():
    return {
        "labels": ["<100", "100-150", "150-200", "200-250", "250-300", ">300"],
        "counts": [8, 23, 31, 19, 12, 7],
        "source": "mock",
    }


@app.get("/api/v1/competitors/events",
         summary="竞品监控 · 近期动态",
         tags=["竞品监控"])
def comp_events(limit: int = Query(10, le=50)):
    with get_conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM comp_events ORDER BY happened_at DESC LIMIT ?", (limit,)
        ).fetchall()]

    now = int(time.time())
    for r in rows:
        diff = now - r["happened_at"]
        if diff < 3600:    r["time_ago"] = f"{diff//60}分钟前"
        elif diff < 86400: r["time_ago"] = f"{diff//3600}小时前"
        else:              r["time_ago"] = f"{diff//86400}天前"
        r["is_negative"] = r["event_type"] in ("price_down", "new_product", "restock")

    return {"total": len(rows), "data": rows}


class CompEventCreate(BaseModel):
    shop_name:  str
    event_type: Literal["price_down","price_up","new_product","rating_drop","restock"]
    product:    str
    detail:     str = ""

@app.post("/api/v1/competitors/events",
          status_code=201,
          summary="竞品监控 · 新增动态（Webhook 用）",
          tags=["竞品监控"])
def add_comp_event(body: CompEventCreate):
    with get_conn() as c:
        c.execute(
            "INSERT INTO comp_events (shop_name,event_type,product,detail) VALUES (?,?,?,?)",
            (body.shop_name, body.event_type, body.product, body.detail)
        )
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# 页面 5：利润计算器
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/v1/profit/calculate",
          summary="利润计算器 · 实时计算",
          tags=["利润计算器"])
def profit_calculate(body: ProfitCalcInput):
    m         = mkt.get(body.market)
    sym       = m["symbol"]                              # 貨幣符號
    logi_base = m["logi_costs"].get(body.logistics_class, m["logi_costs"]["medium"])
    logi_cost = round(logi_base + body.weight_kg * m["logi_per_kg"], 1)
    cost_loc  = round(body.source_price_cny * body.exchange_rate, 1)
    comm_loc  = round(body.price_local * body.commission_rate / 100, 1)
    total_cost = cost_loc + logi_cost + comm_loc
    net_profit = round(body.price_local - total_cost, 1)
    rate       = round(net_profit / body.price_local * 100, 1) if body.price_local else 0

    def suggest(target_rate: float) -> float:
        return math.ceil(total_cost / (1 - target_rate / 100))

    if rate >= 30:
        verdict, verdict_level = "利潤率良好，建議入場測款", "good"
    elif rate >= 15:
        verdict, verdict_level = "利潤偏低，需控制採購成本", "warn"
    else:
        verdict, verdict_level = "利潤率不足，暫不建議入場", "bad"

    return {
        "price_local":    body.price_local,
        "currency":       m["currency"],
        "symbol":         sym,
        "cost_breakdown": {
            "source_cost":    cost_loc,
            "logistics_cost": logi_cost,
            "commission":     comm_loc,
            "total_cost":     round(total_cost, 1),
        },
        "net_profit":     net_profit,
        "profit_rate":    rate,
        "grade":          ("S" if rate>=40 else "A" if rate>=30 else "B" if rate>=20 else "C"),
        "verdict":        verdict,
        "verdict_level":  verdict_level,
        "suggest_prices": {
            "target_20pct": suggest(20),
            "target_30pct": suggest(30),
            "target_40pct": suggest(40),
        },
        "params_used": {
            "market":          body.market,
            "exchange_rate":   body.exchange_rate,
            "logistics_class": body.logistics_class,
            "commission_rate": body.commission_rate,
        }
    }


@app.get("/api/v1/profit/exchange_rate",
         summary="利润计算器 · 获取当前汇率",
         tags=["利润计算器"])
def exchange_rate(market: str = "tw"):
    """回傳指定市場的 CNY→當地幣預設匯率（mock，生產環境替換為外匯 API）"""
    m = mkt.get(market)
    return {
        "market":      market,
        "currency":    m["currency"],
        "symbol":      m["symbol"],
        "cny_to_local": m["default_fx"],
        "source":      "mock",
        "updated_at":  int(time.time()),
    }


@app.get("/api/v1/markets",
         summary="獲取所有支援市場清單",
         tags=["市場"])
def list_markets():
    """供前端市場選擇下拉選單使用"""
    return {"markets": mkt.MARKET_LIST}


# ═══════════════════════════════════════════════════════════════════════════
# 通用
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/v1/weights",
         summary="查询评分权重",
         tags=["通用"])
def get_weights():
    return get_wt()


@app.put("/api/v1/weights",
         summary="更新评分权重",
         tags=["通用"])
def update_weights(body: WeightsUpdate):
    total = body.demand + body.competition + body.logistics
    if abs(total - 1.0) > 0.01:
        raise HTTPException(400, f"权重之和必须为 1，当前 {total:.2f}")
    with get_conn() as c:
        c.execute(
            "UPDATE weights SET demand=?,competition=?,logistics=?,"
            "updated_at=strftime('%s','now') WHERE id=1",
            (body.demand, body.competition, body.logistics)
        )
    return {"ok": True, "weights": body.model_dump()}


# ── 前端靜態入口 ─────────────────────────────────────────────────────────────
from fastapi.responses import HTMLResponse as _HTML
import os as _os

@app.get("/ui", response_class=_HTML, include_in_schema=False)
def serve_ui():
    html_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "index.html")
    if _os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return f.read()
    return _HTML(content="<h1>前端文件未找到，請確認 index.html 與 main.py 在同一目錄</h1>")


# ══════════════════════════════════════════════════════════════════════
#  授權 API 端點
# ══════════════════════════════════════════════════════════════════════

class _LicActivate(BaseModel):
    key: str

@app.get("/api/license/status")
def _lic_status():
    return _lic.get_status()

@app.post("/api/license/activate")
def _lic_activate(body: _LicActivate):
    if _lic.activate(body.key):
        return {"ok": True, "message": "授權成功！系統已解鎖。"}
    return JSONResponse({"ok": False, "message": "密鑰無效，請確認後重試"}, status_code=400)
