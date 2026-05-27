# Shopee 选品分析工具

## 🚀 快速开始（Windows 用户）

不需要 Git，不需要配环境，跟着做就行。

### 第1步：下载

点击页面右上角绿色「**Code**」按钮 →「**Download ZIP**」→ 解压到桌面。

### 第2步：打开终端

打开解压后的文件夹，在空白处**按住 Shift 键 → 右键** → 选择「**在此处打开 PowerShell**」。

### 第3步：安装依赖

在 PowerShell 里输入：

```powershell
pip install openpyxl requests beautifulsoup4
```

### 第4步：运行示例

```powershell
python main.py
```

你会看到 15 个桌面收纳类目的自动分析结果，按毛利率从高到低排序。

### 第5步：用自己的数据

在 `data/` 文件夹里新建一个 `我的商品.csv`，格式如下：

```
标题,售价,批发价,月销,评分,评价数
北欧风桌面收纳盒,199,12,850,4.8,320
透明亚克力化妆品收纳盒,299,18,1200,4.7,560
```

然后运行：

```powershell
python main.py data/我的商品.csv
```

### 第6步：看结果

打开 `data/reports/` 文件夹，双击生成的 Excel 文件即可查看。

- 🟢 绿色 = 推荐
- 🔴 红色 = 不推荐
- 🟡 黄色 = 待观察

---

## 📋 使用方式（Mac / Linux）

```bash
git clone https://github.com/dboooloi02-crypto/shopee-analyzer.git
cd shopee-analyzer
pip install openpyxl requests beautifulsoup4
python3 main.py
```

## 📁 目录结构

```
shopee-analyzer/
├── main.py              # 主程序
├── product.py           # 数据结构
├── config.py            # 配置
├── exporter.py          # 导出工具
├── data/
│   ├── reports/         # Excel 输出
│   ├── raw/             # 原始数据
│   ├── parsed/          # 处理后数据
│   └── cache/           # 缓存
```

## 📌 后续更新

- [ ] Shopee 自动爬虫
- [ ] 评论 NLP 分析
- [ ] 自动比价
- [ ] Web 版界面

仓库持续更新，欢迎 Star ⭐
