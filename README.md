# Shopee 选品分析工具

## 使用方式

### 方式一：手动录入数据（推荐，今晚就能用）

1. 在浏览器打开 Shopee 台湾站，搜一个类目
2. 把感兴趣的品复制到 Excel，格式：
   ```
   标题,售价(TWD),批发价(CNY),月销,评分,评价数
   ```
3. 运行：
   ```bash
   cd /mnt/g/shopee-analyzer
   python3 main.py data/template.csv
   ```

### 方式二：示例数据体验
```bash
python3 main.py
# 会输出 15 个桌面收纳类目的示例分析
```

## 输出

Excel 在 `data/reports/` 目录下，带条件颜色：
- 🟢 绿色 = 推荐
- 🔴 红色 = 不推荐
- 🟡 黄色 = 观察

## 目录结构

```
shopee-analyzer/
├── main.py              # 主程序
├── product.py           # 数据结构
├── config.py            # 配置
├── exporter.py          # 导出工具
├── data/
│   ├── template.csv     # 录入模板
│   ├── raw/             # 原始数据
│   ├── parsed/          # 处理后数据
│   ├── cache/           # 缓存
│   └── reports/         # Excel 输出
```

## 待办（后续更新计划）

- [ ] Shopee 自动爬虫（反爬解决后）
- [ ] 评论 NLP 分析（提炼用户痛点）
- [ ] 利润率自动计算（接入 1688 API）
- [ ] 多页爬取 & 批量商品对比
- [ ] Web 版界面（拖拽上传 CSV）

仓库会持续更新，欢迎 Star ⭐ 关注。
