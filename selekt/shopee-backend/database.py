"""
database.py — SQLite 資料層（aiosqlite 非同步）
"""
import aiosqlite
import json
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "shopee.db"


async def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        PRAGMA journal_mode=WAL;

        -- 採集任務紀錄
        CREATE TABLE IF NOT EXISTS collect_jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword     TEXT    NOT NULL,
            status      TEXT    NOT NULL DEFAULT 'pending',
            total       INTEGER DEFAULT 0,
            created_at  REAL    NOT NULL,
            finished_at REAL,
            market      TEXT    NOT NULL DEFAULT 'tw'
        );

        -- 採集到的商品數據
        CREATE TABLE IF NOT EXISTS products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id      INTEGER NOT NULL REFERENCES collect_jobs(id),
            keyword     TEXT    NOT NULL,
            name        TEXT    NOT NULL,
            price       REAL    DEFAULT 0,
            sales       INTEGER DEFAULT 0,
            rating      REAL    DEFAULT 0,
            rating_count INTEGER DEFAULT 0,
            score       INTEGER DEFAULT 0,
            verdict     TEXT,
            notes       TEXT,
            image       TEXT,
            href        TEXT,
            collected_at REAL   NOT NULL,
            market      TEXT    NOT NULL DEFAULT 'tw'
        );

        -- 收藏的潛力品
        -- FIX: product_id 加 UNIQUE，配合 INSERT OR IGNORE 真正防重複收藏
        CREATE TABLE IF NOT EXISTS favorites (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id  INTEGER UNIQUE REFERENCES products(id),
            keyword     TEXT,
            name        TEXT    NOT NULL,
            price       REAL,
            sales       INTEGER,
            rating      REAL,
            score       INTEGER,
            verdict     TEXT,
            href        TEXT,
            image       TEXT,
            saved_at    REAL    NOT NULL
        );

        -- 定時任務設定
        CREATE TABLE IF NOT EXISTS schedules (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword     TEXT    NOT NULL,
            cron_expr   TEXT    NOT NULL,
            enabled     INTEGER DEFAULT 1,
            last_run    REAL,
            next_run    REAL,
            created_at  REAL    NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_products_job    ON products(job_id);
        CREATE INDEX IF NOT EXISTS idx_products_kw     ON products(keyword);
        CREATE INDEX IF NOT EXISTS idx_products_score  ON products(score DESC);
        """)
        await db.commit()


# ── Jobs ────────────────────────────────────────────────────────────
async def create_job(keyword: str, market: str = "tw") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO collect_jobs(keyword,status,created_at,market) VALUES(?,?,?,?)",
            (keyword, "pending", time.time(), market)
        )
        await db.commit()
        return cur.lastrowid


async def create_ext_job(keyword: str, market: str = "tw") -> int:
    """建立一個等待 Chrome 擴充採集的任務"""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO collect_jobs(keyword,status,created_at,market) VALUES(?,?,?,?)",
            (keyword, "pending_ext", time.time(), market)
        )
        await db.commit()
        return cur.lastrowid


async def get_pending_ext_tasks(limit: int = 5):
    """取得等待擴充採集的任務列表"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, keyword, market FROM collect_jobs WHERE status='pending_ext' ORDER BY created_at ASC LIMIT ?",
            (limit,)
        )
        return [dict(r) for r in await cur.fetchall()]


async def claim_ext_task(job_id: int) -> bool:
    """擴充認領任務，防止重複執行（CAS：只有 pending_ext 才能被認領）"""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE collect_jobs SET status='running_ext' WHERE id=? AND status='pending_ext'",
            (job_id,)
        )
        await db.commit()
        return cur.rowcount > 0


async def get_job(job_id: int):
    """取得單一任務狀態"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM collect_jobs WHERE id=?", (job_id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def update_job(job_id: int, status: str, total: int = None):
    terminal = status in ("done", "failed")
    now = time.time() if terminal else None
    async with aiosqlite.connect(DB_PATH) as db:
        if total is not None:
            await db.execute(
                "UPDATE collect_jobs SET status=?,total=?,finished_at=? WHERE id=?",
                (status, total, now, job_id)
            )
        else:
            if terminal:
                await db.execute(
                    "UPDATE collect_jobs SET status=?,finished_at=? WHERE id=?",
                    (status, now, job_id)
                )
            else:
                await db.execute(
                    "UPDATE collect_jobs SET status=? WHERE id=?",
                    (status, job_id)
                )
        await db.commit()


async def reset_job(job_id: int) -> bool:
    """重置卡住的任務回 pending_ext（只允許 pending_ext/running_ext/failed 狀態）"""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """UPDATE collect_jobs SET status='pending_ext', finished_at=NULL
               WHERE id=? AND status IN ('pending_ext','running_ext','failed')""",
            (job_id,)
        )
        await db.commit()
        return cur.rowcount > 0


async def get_jobs(limit=20):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM collect_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in await cur.fetchall()]


# ── Products ────────────────────────────────────────────────────────
async def save_products(job_id: int, keyword: str, products: list, market: str = "tw"):
    async with aiosqlite.connect(DB_PATH) as db:
        now = time.time()
        await db.executemany(
            """INSERT INTO products
               (job_id,keyword,name,price,sales,rating,rating_count,
                score,verdict,notes,image,href,collected_at,market)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [(
                job_id, keyword,
                p.get("name",""), p.get("price",0), p.get("sales",0),
                p.get("rating",0), p.get("ratingCount") or p.get("rating_count",0),
                p.get("score",0), p.get("verdict",""),
                json.dumps(p.get("notes",[]), ensure_ascii=False),
                p.get("image",""), p.get("href",""), now,
                p.get("market", market)
            ) for p in products]
        )
        await db.commit()


async def get_products(keyword=None, verdict=None, min_score=0,
                       job_id=None, limit=200, offset=0):
    clauses, args = ["score >= ?"], [min_score]
    if keyword:
        clauses.append("keyword LIKE ?"); args.append(f"%{keyword}%")
    if verdict:
        clauses.append("verdict = ?"); args.append(verdict)
    if job_id:
        clauses.append("job_id = ?"); args.append(job_id)

    where = " AND ".join(clauses)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            f"SELECT * FROM products WHERE {where} ORDER BY score DESC LIMIT ? OFFSET ?",
            args + [limit, offset]
        )
        rows = [dict(r) for r in await cur.fetchall()]
        for r in rows:
            try: r["notes"] = json.loads(r["notes"] or "[]")
            except: r["notes"] = []
        return rows


async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        total = (await (await db.execute("SELECT COUNT(*) c FROM products")).fetchone())["c"]
        jobs  = (await (await db.execute("SELECT COUNT(*) c FROM collect_jobs")).fetchone())["c"]
        favs  = (await (await db.execute("SELECT COUNT(*) c FROM favorites")).fetchone())["c"]

        verdict_rows = await (await db.execute(
            "SELECT verdict, COUNT(*) cnt FROM products GROUP BY verdict"
        )).fetchall()
        verdicts = {r["verdict"]: r["cnt"] for r in verdict_rows}

        top_kw = await (await db.execute(
            """SELECT keyword, COUNT(*) cnt, AVG(score) avg_score
               FROM products GROUP BY keyword ORDER BY cnt DESC LIMIT 10"""
        )).fetchall()

        score_dist = await (await db.execute(
            """SELECT
               SUM(CASE WHEN score>=80 THEN 1 ELSE 0 END) s80,
               SUM(CASE WHEN score>=70 AND score<80 THEN 1 ELSE 0 END) s70,
               SUM(CASE WHEN score>=60 AND score<70 THEN 1 ELSE 0 END) s60,
               SUM(CASE WHEN score<60 THEN 1 ELSE 0 END) s50
               FROM products"""
        )).fetchone()

        daily = await (await db.execute(
            """SELECT date(collected_at,'unixepoch','localtime') d, COUNT(*) cnt
               FROM products GROUP BY d ORDER BY d DESC LIMIT 14"""
        )).fetchall()

        return {
            "total_products": total,
            "total_jobs": jobs,
            "total_favorites": favs,
            "verdicts": verdicts,
            "top_keywords": [dict(r) for r in top_kw],
            "score_distribution": dict(score_dist) if score_dist else {},
            "daily_collect": [dict(r) for r in daily],
        }


# ── Favorites ───────────────────────────────────────────────────────
async def add_favorite(product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM products WHERE id=?", (product_id,)
        )).fetchone()
        if not row:
            return None
        row = dict(row)
        await db.execute(
            """INSERT OR IGNORE INTO favorites
               (product_id,keyword,name,price,sales,rating,score,verdict,href,image,saved_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (product_id, row["keyword"], row["name"], row["price"],
             row["sales"], row["rating"], row["score"], row["verdict"],
             row["href"], row["image"], time.time())
        )
        await db.commit()
        return row


async def get_favorites():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM favorites ORDER BY saved_at DESC")
        return [dict(r) for r in await cur.fetchall()]


async def delete_favorite(fav_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM favorites WHERE id=?", (fav_id,))
        await db.commit()


# ── Schedules ───────────────────────────────────────────────────────
async def get_schedules():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM schedules ORDER BY created_at DESC")
        return [dict(r) for r in await cur.fetchall()]


async def create_schedule(keyword: str, cron_expr: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO schedules(keyword,cron_expr,enabled,created_at) VALUES(?,?,1,?)",
            (keyword, cron_expr, time.time())
        )
        await db.commit()
        return cur.lastrowid


async def update_schedule_run(schedule_id: int, next_run: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE schedules SET last_run=?,next_run=? WHERE id=?",
            (time.time(), next_run, schedule_id)
        )
        await db.commit()


async def toggle_schedule(schedule_id: int, enabled: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE schedules SET enabled=? WHERE id=?",
            (1 if enabled else 0, schedule_id)
        )
        await db.commit()


async def delete_schedule(schedule_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
        await db.commit()
