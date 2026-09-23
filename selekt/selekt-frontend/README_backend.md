# SELEKT Backend v2.2

## 启动
```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8002 --reload
```
交互文档：http://localhost:8002/docs

---

## 接口总览

### 页面 1 · 仪表盘
| Method | Path | 说明 |
|--------|------|------|
| GET | /api/v1/dashboard/summary | 4个指标卡 |
| GET | /api/v1/dashboard/ai_insight | AI洞察条 |
| GET | /api/v1/dashboard/ticker | 底部滚动条 |
| GET | /api/v1/products | 商品列表（含过滤/排序/分页）|
| POST | /api/v1/products | 新增商品 |
| GET | /api/v1/products/{id} | 单品详情 |
| DELETE | /api/v1/products/{id} | 删除商品 |

### 页面 2 · 选品雷达
| Method | Path | 说明 |
|--------|------|------|
| GET | /api/v1/radar/categories | 六大类目卡片 |
| GET | /api/v1/radar/bar_chart | 柱状图数据 |
| GET | /api/v1/radar/spider | 蛛网图数据 |

### 页面 3 · 趋势分析
| Method | Path | 说明 |
|--------|------|------|
| GET | /api/v1/trend/keywords | 关键词列表 |
| GET | /api/v1/trend/series?keyword=收纳&days=30 | 折线图+统计卡 |
| GET | /api/v1/trend/ranking?top=5 | 热度排行 |
| GET | /api/v1/trend/related?keyword=收纳 | 关联词推荐 |

### 页面 4 · 竞品监控
| Method | Path | 说明 |
|--------|------|------|
| GET | /api/v1/competitors/summary | 3个指标卡 |
| GET | /api/v1/competitors/list | 竞品排行表 |
| GET | /api/v1/competitors/price_distribution | 价格分布柱状图 |
| GET | /api/v1/competitors/events | 近期动态列表 |
| POST | /api/v1/competitors/events | 新增动态（Webhook用）|

### 页面 5 · 利润计算器
| Method | Path | 说明 |
|--------|------|------|
| POST | /api/v1/profit/calculate | 实时利润计算 |
| GET | /api/v1/profit/exchange_rate | 当前汇率 |

### 通用
| Method | Path | 说明 |
|--------|------|------|
| GET | /api/v1/weights | 查询评分权重 |
| PUT | /api/v1/weights | 更新评分权重 |

---

## 利润计算示例
```bash
curl -X POST http://localhost:8002/api/v1/profit/calculate \
  -H "Content-Type: application/json" \
  -d '{
    "price_twd": 189,
    "source_price_cny": 25,
    "weight_kg": 1.2,
    "logistics_class": "medium",
    "commission_rate": 5.0,
    "exchange_rate": 4.4
  }'
```
