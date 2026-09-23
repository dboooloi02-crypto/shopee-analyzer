# markets.py — Shopee 全平台市場配置中心
# 新增市場只需在 MARKETS 裡加一筆，其餘代碼自動適配

from typing import TypedDict, Dict

class MarketConfig(TypedDict):
    domain:      str          # Shopee 域名
    currency:    str          # ISO 幣種代碼
    symbol:      str          # 顯示符號
    locale:      str          # Playwright locale
    # 價格分段邊界 [超低, 低, 中, 高]，高於最大值為超高價
    price_tiers: list[float]
    # 物流費（當地幣）：小件 / 中件 / 大件
    logi_costs:  Dict[str, float]
    logi_per_kg: float        # 每公斤附加運費（當地幣）
    default_fx:  float        # CNY → 當地幣 預設匯率
    sales_units: Dict[str, int]  # 銷量縮寫對應倍數

MARKETS: Dict[str, MarketConfig] = {
    "tw": {
        "domain":      "shopee.tw",
        "currency":    "TWD",
        "symbol":      "NT$",
        "locale":      "zh-TW",
        "price_tiers": [99, 150, 499, 999],
        "logi_costs":  {"small": 20,    "medium": 35,    "large": 60},
        "logi_per_kg": 20,
        "default_fx":  4.4,
        "sales_units": {"萬": 10000, "万": 10000, "k": 1000, "K": 1000},
    },
    "sg": {
        "domain":      "shopee.sg",
        "currency":    "SGD",
        "symbol":      "S$",
        "locale":      "en-SG",
        "price_tiers": [3, 8, 30, 60],
        "logi_costs":  {"small": 1.5,   "medium": 3.0,   "large": 5.0},
        "logi_per_kg": 1.5,
        "default_fx":  0.18,
        "sales_units": {"k": 1000, "K": 1000},
    },
    "my": {
        "domain":      "shopee.com.my",
        "currency":    "MYR",
        "symbol":      "RM",
        "locale":      "ms-MY",
        "price_tiers": [5, 15, 60, 120],
        "logi_costs":  {"small": 4,     "medium": 7,     "large": 12},
        "logi_per_kg": 3,
        "default_fx":  0.60,
        "sales_units": {"k": 1000, "K": 1000},
    },
    "id": {
        "domain":      "shopee.co.id",
        "currency":    "IDR",
        "symbol":      "Rp",
        "locale":      "id-ID",
        "price_tiers": [5_000, 20_000, 100_000, 300_000],
        "logi_costs":  {"small": 8_000, "medium": 15_000, "large": 25_000},
        "logi_per_kg": 5_000,
        "default_fx":  2_100,
        "sales_units": {"rb": 1000, "jt": 1_000_000, "k": 1000, "K": 1000},
    },
    "th": {
        "domain":      "shopee.co.th",
        "currency":    "THB",
        "symbol":      "฿",
        "locale":      "th-TH",
        "price_tiers": [50, 100, 400, 900],
        "logi_costs":  {"small": 30,    "medium": 50,    "large": 80},
        "logi_per_kg": 20,
        "default_fx":  4.8,
        "sales_units": {"k": 1000, "K": 1000},
    },
    "ph": {
        "domain":      "shopee.ph",
        "currency":    "PHP",
        "symbol":      "₱",
        "locale":      "en-PH",
        "price_tiers": [99, 200, 800, 1_500],
        "logi_costs":  {"small": 50,    "medium": 80,    "large": 120},
        "logi_per_kg": 30,
        "default_fx":  7.8,
        "sales_units": {"k": 1000, "K": 1000},
    },
    "vn": {
        "domain":      "shopee.vn",
        "currency":    "VND",
        "symbol":      "₫",
        "locale":      "vi-VN",
        "price_tiers": [30_000, 80_000, 400_000, 900_000],
        "logi_costs":  {"small": 15_000, "medium": 25_000, "large": 40_000},
        "logi_per_kg": 10_000,
        "default_fx":  3_500,
        "sales_units": {"k": 1000, "K": 1000, "tr": 1_000_000},
    },
    "br": {
        "domain":      "shopee.com.br",
        "currency":    "BRL",
        "symbol":      "R$",
        "locale":      "pt-BR",
        "price_tiers": [5, 15, 60, 120],
        "logi_costs":  {"small": 6,     "medium": 10,    "large": 18},
        "logi_per_kg": 4,
        "default_fx":  0.72,
        "sales_units": {"k": 1000, "K": 1000, "mil": 1000},
    },
}

DEFAULT_MARKET = "tw"


def get(market_code: str) -> MarketConfig:
    """取得市場配置，不存在時 fallback 到台灣"""
    return MARKETS.get(market_code, MARKETS[DEFAULT_MARKET])


def search_url(market_code: str, keyword: str) -> str:
    m = get(market_code)
    from urllib.parse import quote_plus
    return f"https://{m['domain']}/search?keyword={quote_plus(keyword)}"


def product_url(market_code: str, shopid, itemid) -> str:
    m = get(market_code)
    return f"https://{m['domain']}/product/{shopid}/{itemid}"


def image_url(market_code: str, img_hash: str) -> str:
    m = get(market_code)
    return f"https://cf.{m['domain']}/file/{img_hash}_tn"


def price_score(price: float, market_code: str) -> tuple[int, list[str]]:
    """依市場定價區間給分，回傳 (分數, 備註列表)"""
    tiers = get(market_code)["price_tiers"]
    low, mid_low, mid, high = tiers
    notes: list[str] = []
    if mid_low <= price <= mid:
        score = 15
    elif low <= price < mid_low:
        score = 10; notes.append("低價區間競爭較激烈")
    elif mid < price <= high:
        score = 12
    elif price < low:
        score = 3;  notes.append("超低價紅海，利潤風險高")
    else:
        score = 8;  notes.append("高價區間，受眾較窄")
    return score, notes


def profit_rate(price: float, source_cny: float, weight: float,
                market_code: str = DEFAULT_MARKET,
                lclass: str = "medium",
                comm_rate: float = 5.0,
                fx: float | None = None) -> float:
    """計算利潤率（%），fx=None 時使用市場預設匯率"""
    m = get(market_code)
    rate     = fx if fx is not None else m["default_fx"]
    cost     = source_cny * rate
    logi_b   = m["logi_costs"].get(lclass, m["logi_costs"]["medium"])
    logi     = logi_b + weight * m["logi_per_kg"]
    comm     = price * comm_rate / 100
    total    = cost + logi + comm
    return round((price - total) / price * 100 if price else 0, 1)


# 所有市場清單（供前端下拉）
MARKET_LIST = [
    {"code": k, "name": _name, "domain": v["domain"],
     "currency": v["currency"], "symbol": v["symbol"]}
    for k, v, _name in [
        ("tw", MARKETS["tw"], "台灣"),
        ("sg", MARKETS["sg"], "新加坡"),
        ("my", MARKETS["my"], "馬來西亞"),
        ("id", MARKETS["id"], "印尼"),
        ("th", MARKETS["th"], "泰國"),
        ("ph", MARKETS["ph"], "菲律賓"),
        ("vn", MARKETS["vn"], "越南"),
        ("br", MARKETS["br"], "巴西"),
    ]
]
