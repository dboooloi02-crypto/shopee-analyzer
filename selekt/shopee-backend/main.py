"""
main.py — FastAPI 後端主程式
啟動指令: uvicorn main:app --reload --port 8000
"""
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import database as db
from scraper import scrape_keyword

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("main")

# FIX: 模板路徑改為絕對路徑，無論從哪個目錄啟動都不會 500
TEMPLATE_PATH = Path(__file__).parent / "templates" / "dashboard.html"

# ── APScheduler ──────────────────────────────────────────────────────
scheduler = AsyncIOScheduler(timezone="Asia/Taipei")


async def run_scheduled_job(schedule_id: int, keyword: str):
    logger.info(f"定時任務觸發: keyword={keyword}")
    job_id = await db.create_job(keyword)
    await db.update_job(job_id, "running")
    try:
        products = await scrape_keyword(keyword, max_products=60)
        await db.save_products(job_id, keyword, products)
        await db.update_job(job_id, "done", total=len(products))
        job = scheduler.get_job(f"sched_{schedule_id}")
        next_run = job.next_run_time.timestamp() if job and job.next_run_time else None
        if next_run:
            await db.update_schedule_run(schedule_id, next_run)
    except Exception as e:
        logger.error(f"定時採集失敗: {e}")
        await db.update_job(job_id, "failed")


async def reload_schedules():
    """從資料庫重新載入所有定時任務"""
    schedules = await db.get_schedules()
    for s in schedules:
        job_id_str = f"sched_{s['id']}"
        if scheduler.get_job(job_id_str):
            scheduler.remove_job(job_id_str)
        if s["enabled"]:
            try:
                parts = s["cron_expr"].split()
                trigger = CronTrigger(
                    minute=parts[0], hour=parts[1],
                    day=parts[2], month=parts[3], day_of_week=parts[4],
                    timezone="Asia/Taipei"
                )
                scheduler.add_job(
                    run_scheduled_job, trigger,
                    args=[s["id"], s["keyword"]],
                    id=job_id_str, replace_existing=True
                )
                logger.info(f"已載入定時任務: {s['keyword']} ({s['cron_expr']})")
            except Exception as e:
                logger.error(f"載入定時任務失敗: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    scheduler.start()
    await reload_schedules()
    logger.info("✅ Shopee 選品後端已啟動 → http://localhost:8002")
    yield
    scheduler.shutdown()


# ── FastAPI App ──────────────────────────────────────────────────────
app = FastAPI(title="Shopee 選品後端", version="1.0.0", lifespan=lifespan)

# ── 授權中間件（先注冊 = 內層；CORS 後注冊 = 外層，確保 402 也帶 CORS header）
import license as _lic
from fastapi import Request as _Req
from fastapi.responses import JSONResponse as _JSONResp

_LICENSE_WHITELIST = (
    "/api/license", "/api/health",
    "/docs", "/openapi.json",
    "/api/collect/pending-tasks",
)

@app.middleware("http")
async def _license_guard(request: _Req, call_next):
    path = request.url.path
    if (request.method == "OPTIONS"
            or path == "/"
            or any(path.startswith(w) for w in _LICENSE_WHITELIST)):
        return await call_next(request)
    s = _lic.get_status()
    if s["status"] in ("trial_expired", "key_expired"):
        return _JSONResp(
            {"error": "license_expired",
             "message": "試用期已結束，請輸入授權密鑰解鎖",
             "install_id": s["install_id"]},
            status_code=402,
        )
    return await call_next(request)

# ── CORS（後注冊 = 外層，包住 license_guard，402 也會帶 CORS header）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 進度追蹤（簡易 in-memory）───────────────────────────────────────
job_progress: dict[int, dict] = {}


# ══════════════════════════════════════════════════════════════════════
#  API Routes
# ══════════════════════════════════════════════════════════════════════

# ── 採集 ─────────────────────────────────────────────────────────────
import markets as mkt

class CollectRequest(BaseModel):
    keyword:      str
    max_products: int = 60
    market:       str = "tw"   # 市場代碼，預設台灣


class ProductsFromExtension(BaseModel):
    keyword:  str
    products: list
    task_id:  Optional[int] = None
    error:    Optional[str] = None
    market:   str = "tw"


@app.post("/api/collect/start")
async def start_collect(req: CollectRequest, background_tasks: BackgroundTasks):
    """啟動後端 Playwright 採集任務（非同步背景執行）"""
    job_id = await db.create_job(req.keyword, market=req.market)
    job_progress[job_id] = {"done": 0, "total": req.max_products, "status": "running"}

    async def run():
        await db.update_job(job_id, "running")
        try:
            async def progress_cb(done, total):
                job_progress[job_id] = {"done": done, "total": total, "status": "running"}

            products = await scrape_keyword(
                req.keyword, max_products=req.max_products,
                market_code=req.market, progress_cb=progress_cb
            )
            await db.save_products(job_id, req.keyword, products, market=req.market)
            await db.update_job(job_id, "done", total=len(products))
            job_progress[job_id] = {"done": len(products), "total": len(products), "status": "done"}
        except Exception as e:
            logger.error(f"採集失敗: {e}")
            await db.update_job(job_id, "failed")
            job_progress[job_id] = {"done": 0, "total": 0, "status": "failed", "error": str(e)}

    background_tasks.add_task(run)
    return {"job_id": job_id, "status": "started"}


@app.get("/api/collect/progress/{job_id}")
async def collect_progress(job_id: int):
    """SSE 進度推播（Server-Sent Events）"""
    async def event_stream():
        while True:
            prog = job_progress.get(job_id, {"status": "unknown"})
            yield f"data: {__import__('json').dumps(prog)}\n\n"
            if prog.get("status") in ("done", "failed", "unknown"):
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.post("/api/collect/trigger-ext")
async def trigger_ext_collect(req: CollectRequest):
    """建立任務並等待 Chrome 擴充自動採集（不啟動 Playwright）"""
    job_id = await db.create_ext_job(req.keyword, market=req.market)
    logger.info(f"已建立擴充採集任務 Job#{job_id} keyword={req.keyword} market={req.market}")
    return {"job_id": job_id, "status": "pending_ext", "market": req.market}


@app.get("/api/collect/pending-tasks")
async def get_pending_tasks():
    """Chrome 擴充輪詢此接口取得待採集任務（帶 market 欄位）"""
    tasks = await db.get_pending_ext_tasks()
    return {"tasks": tasks}


@app.post("/api/collect/claim/{job_id}")
async def claim_task(job_id: int):
    """Chrome 擴充認領任務，防止多個擴充重複執行"""
    claimed = await db.claim_ext_task(job_id)
    return {"ok": claimed}


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: int):
    """查詢單一任務狀態（前端輪詢用）"""
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "任務不存在")
    return job


@app.get("/api/markets")
async def list_markets():
    """回傳所有支援的市場清單，供前端下拉選單使用"""
    return {"markets": mkt.MARKET_LIST}


@app.post("/api/collect/from-extension")
async def collect_from_extension(req: ProductsFromExtension):
    """接收 Chrome 擴充傳來的商品數據並存入資料庫"""
    if req.task_id:
        job_id = req.task_id
        await db.save_products(job_id, req.keyword, req.products, market=req.market)
        status = "done" if not req.error else ("done" if req.products else "failed")
        await db.update_job(job_id, status, total=len(req.products))
        logger.info(f"from-extension Task#{job_id} {status} {len(req.products)} 件 market={req.market}")
    else:
        job_id = await db.create_job(req.keyword, market=req.market)
        await db.update_job(job_id, "running")
        await db.save_products(job_id, req.keyword, req.products)
        await db.update_job(job_id, "done", total=len(req.products))
    return {"job_id": job_id, "saved": len(req.products)}


# ── 商品查詢 ──────────────────────────────────────────────────────────
@app.get("/api/products")
async def list_products(
    keyword: Optional[str] = None,
    verdict: Optional[str] = None,
    min_score: int = 0,
    job_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
):
    products = await db.get_products(keyword, verdict, min_score, job_id, limit, offset)
    return {"products": products, "count": len(products)}


# ── 採集任務紀錄 ──────────────────────────────────────────────────────
@app.get("/api/jobs")
async def list_jobs(limit: int = 20):
    jobs = await db.get_jobs(limit)
    return {"jobs": jobs}


# ── 統計看板 ──────────────────────────────────────────────────────────
@app.get("/api/stats")
async def stats():
    return await db.get_stats()


# ── 收藏 ──────────────────────────────────────────────────────────────
@app.post("/api/favorites/{product_id}")
async def add_favorite(product_id: int):
    result = await db.add_favorite(product_id)
    if not result:
        raise HTTPException(404, "商品不存在")
    return {"ok": True, "product": result}


@app.get("/api/favorites")
async def list_favorites():
    return {"favorites": await db.get_favorites()}


@app.delete("/api/favorites/{fav_id}")
async def del_favorite(fav_id: int):
    await db.delete_favorite(fav_id)
    return {"ok": True}


# ── 定時任務 ──────────────────────────────────────────────────────────
class ScheduleRequest(BaseModel):
    keyword: str
    cron_expr: str  # "分 時 日 月 週" e.g. "0 9 * * *" = 每天早上9點


@app.get("/api/schedules")
async def list_schedules():
    return {"schedules": await db.get_schedules()}


@app.post("/api/schedules")
async def create_schedule(req: ScheduleRequest):
    sid = await db.create_schedule(req.keyword, req.cron_expr)
    await reload_schedules()
    return {"id": sid, "ok": True}


@app.patch("/api/schedules/{sid}/toggle")
async def toggle_schedule(sid: int, enabled: bool):
    await db.toggle_schedule(sid, enabled)
    await reload_schedules()
    return {"ok": True}


@app.delete("/api/schedules/{sid}")
async def delete_schedule(sid: int):
    await db.delete_schedule(sid)
    job_key = f"sched_{sid}"
    if scheduler.get_job(job_key):
        scheduler.remove_job(job_key)
    return {"ok": True}


# ── 健康檢查 ──────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok", "time": time.time()}


# ── 前端看板 ─────────────────────────────────────────────────────────
# FIX: 改用絕對路徑，避免非根目錄啟動時 FileNotFoundError
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return TEMPLATE_PATH.read_text(encoding="utf-8")



@app.post("/api/jobs/{job_id}/reset")
async def reset_job(job_id: int):
    """重置卡住的 pending_ext / running_ext 任務，讓插件重新採集"""
    ok = await db.reset_job(job_id)
    if not ok:
        raise HTTPException(400, "任務無法重置（可能已完成或不存在）")
    return {"ok": True, "message": f"Job#{job_id} 已重置為 pending_ext"}

# ══════════════════════════════════════════════════════════════════════
#  授權系統 (License)
# ══════════════════════════════════════════════════════════════════════
from pydantic import BaseModel as _BM

class _LicActivate(_BM):
    key: str

@app.get("/api/license/status")
def _lic_status():
    return _lic.get_status()

@app.post("/api/license/activate")
def _lic_activate(body: _LicActivate):
    if _lic.activate(body.key):
        return {"ok": True, "message": "授權成功！系統已解鎖。"}
    return _JSONResp({"ok": False, "message": "密鑰無效，請確認後重試"}, status_code=400)
