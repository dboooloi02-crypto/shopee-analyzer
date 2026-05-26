"""Shopee 台湾站爬虫

使用 Playwright 浏览器引擎，绕过 Shopee 反爬机制。
第一版只爬列表页，不做评论/详情页。

使用方式：
    from crawler import ShopeeCrawler
    crawler = ShopeeCrawler()
    result = crawler.search("桌面收納", max_items=60)
"""

import os
import json
import time
import hashlib
from datetime import datetime
from typing import Optional

from config import RAW_DIR, CACHE_DIR, CACHE_TTL, REQUEST_DELAY, ITEMS_PER_PAGE
from product import Product, CrawlResult


class ShopeeCrawler:
    """Shopee 台湾站爬虫"""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._browser = None
        self._context = None

    def _cache_path(self, key: str) -> str:
        """生成缓存文件路径"""
        h = hashlib.md5(key.encode()).hexdigest()
        return os.path.join(CACHE_DIR, f"{h}.json")

    def _load_cache(self, key: str) -> Optional[list]:
        """读取缓存"""
        path = self._cache_path(key)
        if not os.path.exists(path):
            return None
        mtime = os.path.getmtime(path)
        if time.time() - mtime > CACHE_TTL:
            return None
        with open(path, "r") as f:
            data = json.load(f)
        # 还原为 Product 对象
        return [Product(**p) for p in data]

    def _save_cache(self, key: str, products: list[Product]):
        """写入缓存"""
        os.makedirs(CACHE_DIR, exist_ok=True)
        path = self._cache_path(key)
        with open(path, "w") as f:
            json.dump([p.to_dict() for p in products], f, ensure_ascii=False, indent=2)

    def _save_raw(self, keyword: str, page: int, data: dict):
        """保存原始 API 响应"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{keyword}_{page}_{ts}.json"
        # 清理文件名
        fname = fname.replace(" ", "_").replace("/", "_")
        path = os.path.join(RAW_DIR, fname)
        os.makedirs(RAW_DIR, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _parse_products(self, items: list[dict]) -> list[Product]:
        """从 Shopee API 响应中解析商品"""
        products = []
        for item in items:
            try:
                basic = item.get("item_basic", {})
                if not basic:
                    continue
                p = Product(
                    item_id=basic.get("item_id", 0),
                    title=basic.get("name", ""),
                    price_min=basic.get("price_min", 0) / 100000,  # Shopee 价格单位
                    price_max=basic.get("price_max", 0) / 100000,
                    historical_sold=basic.get("historical_sold", 0),
                    rating=basic.get("item_rating", {}).get("rating_star", 0),
                    review_count=basic.get("item_rating", {}).get("rating_count", 0),
                    shop_id=basic.get("shop_id", 0),
                    shop_name=basic.get("shop_name", "") or basic.get("shop_location", ""),
                    shop_location=basic.get("shop_location", ""),
                    image_url=basic.get("image", ""),
                    category_id=basic.get("category_id", 0),
                    liked_count=basic.get("liked_count", 0),
                    is_preferred_plus=basic.get("is_preferred_plus", False),
                )
                products.append(p)
            except Exception as e:
                print(f"  ⚠️ 解析商品失败: {e}")
                continue
        return products

    def search(self, keyword: str, max_items: int = 60) -> CrawlResult:
        """搜索商品

        Args:
            keyword: 搜索关键词（如"桌面收納"）
            max_items: 最大商品数（60=1页, 120=2页）

        Returns:
            CrawlResult 对象
        """
        cache_key = f"{keyword}_{max_items}"

        # 1. 尝试从缓存读取
        cached = self._load_cache(cache_key)
        if cached is not None:
            print(f"  📦 使用缓存数据 ({len(cached)} 条)")
            return CrawlResult(keyword=keyword, total_items=len(cached), products=cached)

        from playwright.sync_api import sync_playwright

        all_products = []
        pages_to_fetch = max(1, max_items // ITEMS_PER_PAGE)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                locale="zh-TW",
                timezone_id="Asia/Taipei",
            )
            page = context.new_page()

            # 拦截搜索 API 响应
            api_responses = []

            def on_response(response):
                url = response.url
                if "api/v4/search/search_items" in url and response.status == 200:
                    try:
                        data = response.json()
                        api_responses.append(data)
                    except Exception:
                        pass

            page.on("response", on_response)

            try:
                for page_idx in range(pages_to_fetch):
                    newest = page_idx * ITEMS_PER_PAGE
                    url = f"https://shopee.tw/search?keyword={keyword}&page={page_idx}"
                    print(f"  🌐 正在爬取第 {page_idx + 1} 页 (newest={newest})...")

                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    # 等待搜索结果出现
                    try:
                        page.wait_for_selector(".shopee-search-item-result__item", timeout=10000)
                    except Exception:
                        pass
                    page.wait_for_timeout(5000)

                    # 额外滚动触发懒加载
                    for _ in range(3):
                        page.evaluate("window.scrollBy(0, 600)")
                        page.wait_for_timeout(1000)

                # 等待所有 API 响应收集完成
                page.wait_for_timeout(2000)

            except Exception as e:
                browser.close()
                return CrawlResult(
                    keyword=keyword,
                    total_items=0,
                    error=f"爬取失败: {e}",
                )

            browser.close()

        # 2. 解析收集到的 API 响应
        for resp_data in api_responses:
            items = resp_data.get("items", [])
            if not items:
                continue

            # 保存原始响应
            self._save_raw(keyword, len(all_products), resp_data)

            products = self._parse_products(items)
            all_products.extend(products)
            print(f"  ✅ 解析到 {len(products)} 个商品")

        # 3. 去重（按 item_id）
        seen = set()
        unique_products = []
        for p in all_products:
            if p.item_id not in seen:
                seen.add(p.item_id)
                unique_products.append(p)

        # 4. 截取上限
        result_products = unique_products[:max_items]

        # 5. 保存缓存
        self._save_cache(cache_key, result_products)

        print(f"\n  📊 共获取 {len(result_products)} 个商品 (去重后)")

        return CrawlResult(
            keyword=keyword,
            total_items=len(result_products),
            products=result_products,
        )
