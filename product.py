"""商品数据结构"""
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Product:
    """Shopee 商品基础信息"""
    item_id: int               # Shopee 商品ID
    title: str                 # 标题
    price_min: float           # 最低价（TWD）
    price_max: float           # 最高价（TWD）
    currency: str = "TWD"      # 币种
    historical_sold: int = 0   # 历史销量
    rating: float = 0.0        # 评分（1-5）
    review_count: int = 0      # 评价数
    shop_id: int = 0           # 店铺ID
    shop_name: str = ""        # 店铺名
    shop_location: str = ""    # 店铺位置
    image_url: str = ""        # 主图URL
    category_id: int = 0       # 类目ID
    # 可选扩展
    liked_count: int = 0       # 收藏数
    brand: str = ""            # 品牌
    is_preferred_plus: bool = False  # 优选+
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CrawlResult:
    """爬取结果"""
    keyword: str
    total_items: int
    products: list[Product] = field(default_factory=list)
    error: Optional[str] = None
