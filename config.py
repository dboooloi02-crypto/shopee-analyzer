"""配置"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
PARSED_DIR = os.path.join(DATA_DIR, "parsed")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")

# Shopee 台湾站
SHOPEE_TW_BASE = "https://shopee.tw"
SHOPEE_TW_SEARCH = f"{SHOPEE_TW_BASE}/search"

# 爬虫默认参数
ITEMS_PER_PAGE = 60  # Shopee 默认每页 60
MAX_ITEMS = 120       # 第一版先爬 2 页
REQUEST_DELAY = 2     # 请求间隔（秒）

# 缓存有效期（秒）
CACHE_TTL = 3600  # 1小时
