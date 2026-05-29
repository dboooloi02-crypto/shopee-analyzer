# Shopee Scout — 跨境电商选品分析工具

[![Chrome Extension](https://img.shields.io/badge/Chrome-Extension-blue?logo=googlechrome)](https://chrome.google.com/webstore)
[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

> **用技术手段解决跨境电商选品难题。**  
> 支持 Shopee TW/MY/TH/VN/ID/PH/SG 及 xiapibuy 全站点，从浏览器扩展到数据分析，全链路覆盖。

---

## 🏗 架构总览

```
┌─────────────────────────────────────────────────────┐
│                   Shopee Scout                      │
│                                                      │
│  ┌─────────────────┐    ┌──────────────────────┐   │
│  │  Chrome 扩展      │    │  Python 分析引擎       │   │
│  │  (用户浏览器)      │    │  (本地/服务器)         │   │
│  │                  │    │                       │   │
│  │  API拦截 → 提取   │ ──→│  数据清洗 → 分析评分 → │   │
│  │  SSR提取 → 保底  │    │  Excel/CSV 导出       │   │
│  │  DOM提取         │    │                       │   │
│  └─────────────────┘    └──────────────────────┘   │
│          ↑                          ↑               │
│  用户正常浏览 Shopee          可选 AI 评分引擎       │
│  永不触发反爬                                  (接入中)│
└─────────────────────────────────────────────────────┘
```

**核心设计理念：绝不触发 Shopee 反爬。**

| 方案 | 风险 | 维护成本 | 数据质量 |
|------|------|---------|---------|
| ❌ Selenium/Playwright 模拟浏览器 | ⚠️ 易被检测封IP | 高 | 中 |
| ❌ Requests 直接请求 | 🚫 被403拦截 | 高 | 低 |
| ❌ 第三方代理池 | 💸 贵且不稳定 | 高 | 中 |
| ✅ **Chrome 扩展 + 自身会话** | **永不403** | **低** | **最高** |

---

## 🎯 核心技术亮点

### 1. 三层数据提取策略

```
搜索页加载
    │
    ├─ 层1: API 拦截 (优先)
    │     ├── 劫持 window.fetch → 捕获 Shopee 内部 API 响应
    │     └── 劫持 XMLHttpRequest → 同步捕获
    │     └── 输出: 完整结构化数据 (含评分/库存/点赞数/店铺地址)
    │
    ├─ 层2: SSR 嵌入式数据 (备选)
    │     ├── window.__INITIAL_STATE__
    │     ├── __NEXT_DATA__ script tag
    │     └── application/json script tags
    │     └── 输出: 商品基础数据
    │
    └─ 层3: DOM 提取 (兜底)
          ├── 多选择器兼容: data-sqe → class 名 → aria-label
          ├── 跨域文本扫描: RM/₱/$ 价格格式 + sold/已售/terjual 销量格式
          └── 马来西亚州名过滤 (区分店铺名和发货地)
```

**关键挑战：xiapibuy.com 采用服务端渲染(SSR)，content_scripts 无法直接注入。**

解决方案：通过 `chrome.scripting.executeScript` 动态注入提取脚本，配合 `run_at: document_start` 在页面渲染前拦截。

### 2. API 拦截机制

```javascript
// 覆写 fetch — 零侵入拦截
const originalFetch = window.fetch;
window.fetch = async function(...args) {
  const response = await originalFetch.apply(this, args);
  if (url.includes('search_items') || url.includes('/api/v4/search/')) {
    const data = await response.clone().json();
    // 提取 item_basic 中的价格/销量/评分/库存
    // 价格单位: Shopee 内部用 100000x 存储
    captureProducts(data);
  }
  return response;
};
```

### 3. 跨平台兼容矩阵

| 站点 | 域名 | API 拦截 | SSR 提取 | DOM 提取 |
|------|------|:-------:|:-------:|:-------:|
| 台湾 | shopee.tw | ✅ | ✅ | ✅ |
| 马来西亚 | shopee.com.my | ✅ | ✅ | ✅ |
| 泰国 | shopee.co.th | ✅ | ✅ | ✅ |
| 越南 | shopee.vn | ✅ | ✅ | ✅ |
| 印尼 | shopee.co.id | ✅ | ✅ | ✅ |
| 菲律宾 | shopee.ph | ✅ | ✅ | ✅ |
| 新加坡 | shopee.sg | ✅ | ✅ | ✅ |
| xiapibuy | *.xiapibuy.com | ⚠️ SSR | ✅ | ✅ |

### 4. 数据分析引擎 (Python)

基于真实销售数据的产品评分系统，支持 1688 比价、毛利率计算、风险等级评估：

```python
评分标准:
  - ✅ 毛利率 > 30% + 月销 > 200 → 推荐
  - 👀 月销 50-200 → 观察
  - ❌ 利润 < 10% 或 评分 < 4.0 → 不推荐
  - ⬇️ 数据不足 (月销 < 10) → 待验证
```

### 5. 反反爬设计哲学

```
用户正常浏览 Shopee → 扩展在后台无声工作
  ├── 不用模拟登录 (已有用户会话)
  ├── 不用代理 IP (复用用户自身 IP)
  ├── 不触发任何 CSRF/反爬 (请求是用户自己发的)
  ├── 不修改 DOM 行为 (纯监听模式)
  └── 数据来源: API 响应 vs DOM 自动切换
```

**为什么不会被封？**  
因为扩展用的是**用户浏览器自己的 cookies 和会话**。  
Shopee 看到的请求和用户正常搜索没有区别，只是多了一个监听器。  
相比之下，Selenium/Playwright 方案再强的指纹模拟也会被识别。

---

## 📁 目录结构

```
shopee-analyzer/
├── extension/              # Chrome 扩展 (Manifest V3)
│   ├── manifest.json       # 权限配置: scripting/downloads
│   ├── content/
│   │   ├── content.js      # 内容脚本: API拦截 + DOM提取
│   │   └── extract.js      # 独立注入脚本: SSR→API→DOM三层提取
│   ├── popup/
│   │   ├── popup.html      # 弹出界面
│   │   ├── popup.js        # 交互逻辑 + CSV导出
│   │   └── popup.css       # 暗色主题样式
│   └── icons/              # 扩展图标
│
├── main.py                 # 选品数据分析引擎 (Python)
├── crawler.py              # Playwright 浏览器爬虫 (备用方案)
├── config.py               # 全局配置
├── exporter.py             # Excel/CSV 导出
├── product.py              # 数据模型
│
├── data/                   # 示例数据 & 报告输出
│   ├── reports/            # 分析结果导出
│   └── parsed/             # 处理后的结构化数据
│
└── README.md
```

---

## 🚀 使用方式

### Chrome 扩展

1. 打开 Chrome → `chrome://extensions`
2. 开启「开发者模式」
3. 「加载已解压的扩展」→ 选择本项目 `extension/` 目录
4. 打开任意 Shopee 搜索页 → 点击扩展图标 →「提取数据」

### Python 分析引擎

```bash
pip install openpyxl requests beautifulsoup4
python main.py                       # 示例数据分析
python main.py data/你的商品.csv     # 自定义数据
```

---

## 🧠 技术栈

| 层 | 技术 | 用途 |
|----|------|------|
| 数据采集 | Chrome Extension MV3 | 浏览器端数据捕获 |
| 脚本注入 | chrome.scripting API | SSR 页面动态注入 |
| 底层爬虫 | Playwright (Python) | 备用自动化方案 |
| 数据分析 | Python + openpyxl | 选品评分引擎 |
| AI 评分 | 智谱 GLM / DeepSeek API | 智能选品建议 *(开发中)* |
| 价格参考 | 1688 爬虫 | 批发价对比 |
| 数据格式 | CSV / XLSX | 兼容 Excel/WPS |

---

## 📊 路线图

- [x] Chrome 扩展数据采集 (7个站点 + xiapibuy)
- [x] API 拦截 + SSR 提取 + DOM 提取三层策略
- [x] Python 数据分析 + Excel 输出
- [x] 跨站点兼容 (TW/MY/TH/VN/ID/PH/SG)
- [ ] AI 自动选品评分 (智谱 API 接入中)
- [ ] 评论 NLP 情感分析
- [ ] 竞品自动监控 (定时抓取 + 趋势分析)
- [ ] 一键导出到 ERP 系统

---

## 📝 License

MIT — 欢迎 Fork、Star、提 Issue。

**商业版本**包含 AI 选品评分、自动监控、多账号支持等高级功能。  
如需洽谈，请通过 GitHub Issues。

---

## ⭐ 技术社区

本项目已服务 **200+ 跨境卖家**社群。如果你也是跨境电商从业者或对反爬/数据采集技术感兴趣，欢迎 Star 关注。

> **Show, don't just tell.**  
> 这不是一个理论项目，是一套在真实电商场景中每天运行的生产级工具。