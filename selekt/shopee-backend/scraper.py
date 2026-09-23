"""
scraper.py — Playwright 採集器（XHR 攔截版，全平台適配）
"""
import re
import json
import logging
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
import markets as mkt

logger = logging.getLogger("scraper")

# ── 選品打分邏輯 ──────────────────────────────────────────────────────
def score_product(product: dict) -> dict:
    score = 0
    notes = []
    name = (product.get("name") or "").lower()

    # 維度一：市場與利潤（40分）
    sales = product.get("sales", 0)
    if sales >= 1000:      score += 15
    elif sales >= 500:     score += 12; notes.append("銷量中等")
    elif sales >= 100:     score += 8;  notes.append("銷量偏低")
    elif sales >= 10:      score += 4;  notes.append("銷量很低")
    else:                               notes.append("銷量極少，風險高")

    rating = product.get("rating", 0)
    rating_count = product.get("ratingCount", 0)
    if rating >= 4.7 and rating_count >= 50:    score += 15
    elif rating >= 4.5 and rating_count >= 20:  score += 12
    elif rating >= 4.0:                         score += 8;  notes.append("評分一般")
    elif rating >= 3.0:                         score += 4;  notes.append("評分偏低")
    else:                                                    notes.append("評分差或無評分")

    has_variant = bool(re.search(r'組合|套裝|多入|多色|多尺寸|pack|set|combo', name))
    score += 10 if has_variant else 5
    if not has_variant: notes.append("建議增加組合規格")

    # 維度二：競爭與圖片（30分）
    price = product.get("price", 0)
    market_code = product.get("market", mkt.DEFAULT_MARKET)
    _pscore, _pnotes = mkt.price_score(price, market_code)
    score += _pscore
    notes.extend(_pnotes)

    score += 10
    notes.append("圖片品質請人工確認")

    # 維度三：風險與物流（30分）
    risky = bool(re.search(r'玻璃|電器|電子|插頭|食品|飲料|刀|剪', name))
    score += 2 if risky else 9
    if risky: notes.append("⚠ 品類有風險，謹慎評估")

    score += 8

    legal_risk = bool(re.search(r'認證|3C|安規|接觸食品|嬰兒|兒童', name))
    score += 2 if legal_risk else 8
    if legal_risk: notes.append("⚠ 可能需認證，確認法規")

    if score >= 80:    verdict = "強烈推薦"
    elif score >= 70:  verdict = "可以測款"
    elif score >= 60:  verdict = "謹慎考慮"
    else:              verdict = "直接放棄"

    return {**product, "score": score, "verdict": verdict, "notes": notes}


# ── 解析 Shopee API 回傳的單筆商品 ────────────────────────────────────
def parse_item(item: dict, market_code: str = mkt.DEFAULT_MARKET) -> dict | None:
    """Shopee /api/v4/search/search_items item_basic 格式，支援多市場"""
    try:
        ib = item.get("item_basic") or item
        name = ib.get("name", "").strip()
        if not name:
            return None

        raw_price = ib.get("price") or ib.get("price_min") or 0
        price = round(raw_price / 100000, 0)   # Shopee 所有市場均為 × 100000

        sales = ib.get("sold") or ib.get("historical_sold") or 0

        rating_info = ib.get("item_rating") or {}
        rating = round(float(rating_info.get("rating_star") or 0), 1)
        rc_list = rating_info.get("rating_count") or []
        rating_count = rc_list[0] if rc_list else 0

        itemid = ib.get("itemid") or ib.get("item_id") or ""
        shopid = ib.get("shopid") or ib.get("shop_id") or ""
        href  = mkt.product_url(market_code, shopid, itemid) if itemid and shopid else ""

        img_hash = ib.get("image") or ""
        image    = mkt.image_url(market_code, img_hash) if img_hash else ""

        return {
            "name": name, "price": price, "sales": sales,
            "rating": rating, "ratingCount": rating_count,
            "href": href, "image": image, "market": market_code,
        }
    except Exception as e:
        logger.debug(f"parse_item 失敗: {e}")
        return None


# ── 主採集函數 ────────────────────────────────────────────────────────
async def scrape_keyword(keyword: str, max_products: int = 60,
                         market_code: str = mkt.DEFAULT_MARKET,
                         progress_cb=None) -> list:
    """
    Playwright XHR 攔截版（全平台適配）：
    1. 依市場代碼決定 URL / locale / timezone
    2. 攔截 search_items XHR 響應
    3. 解析 JSON → 打分 → 回傳
    """
    results = []
    limit = min(max_products, 60)
    m = mkt.get(market_code)
    url = mkt.search_url(market_code, keyword)

    # 依市場決定時區（印尼跨三個時區取西部，越南/泰國用 +7）
    _timezone_map = {
        "tw": "Asia/Taipei",    "sg": "Asia/Singapore",
        "my": "Asia/Kuala_Lumpur", "id": "Asia/Jakarta",
        "th": "Asia/Bangkok",   "ph": "Asia/Manila",
        "vn": "Asia/Ho_Chi_Minh", "br": "America/Sao_Paulo",
    }
    timezone_id = _timezone_map.get(market_code, "Asia/Taipei")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale=m["locale"],
            timezone_id=timezone_id,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)

        # ── 攔截器：收集 search_items 響應 ──
        intercepted_responses = []

        async def on_response(response):
            url_str = response.url
            if "/api/v4/search/search_items" in url_str or "/api/v2/search/search_items" in url_str:
                try:
                    body = await response.json()
                    intercepted_responses.append(body)
                    logger.info(f"✅ 攔截到 search_items 響應: {len(body.get('items', body.get('data',{}).get('items',[])))} 筆商品")
                except Exception as e:
                    logger.warning(f"攔截解析失敗: {e}")

        page.on("response", on_response)

        try:
            logger.info(f"正在開啟搜索頁: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # 等待頁面 JS 執行並發出 XHR
            await page.wait_for_timeout(5000)

            # 滾動觸發更多商品載入
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
                await page.wait_for_timeout(1500)

            # 再等一會讓攔截器收集完
            await page.wait_for_timeout(2000)

            # ── 處理攔截到的數據 ──
            if not intercepted_responses:
                logger.warning("⚠ 未攔截到任何 search_items 響應 — 可能被反爬封鎖")
                return results

            # 合併所有頁的商品，按 itemid 去重（每次滾動觸發一個新 XHR）
            all_items: list = []
            seen_ids: set = set()
            for body in intercepted_responses:
                page_items = (
                    body.get("items") or
                    body.get("data", {}).get("items") or
                    []
                )
                for item in page_items:
                    ib = item.get("item_basic") or item
                    key = ib.get("itemid") or ib.get("name", "")
                    if key and key not in seen_ids:
                        seen_ids.add(key)
                        all_items.append(item)
            items = all_items
            logger.info(f"合併 {len(intercepted_responses)} 次 XHR，共 {len(items)} 筆不重複商品")

            total = min(len(items), limit)
            for idx, item in enumerate(items[:limit]):
                parsed = parse_item(item, market_code)
                if parsed:
                    scored = score_product(parsed)
                    results.append(scored)
                if progress_cb:
                    await progress_cb(idx + 1, total)

        except PWTimeout:
            logger.error("頁面載入超時")
        except Exception as e:
            logger.error(f"採集錯誤: {e}", exc_info=True)
        finally:
            await browser.close()

    logger.info(f"採集完成，共 {len(results)} 件商品")
    return results
