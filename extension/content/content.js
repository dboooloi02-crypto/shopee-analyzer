/**
 * Shopee Scout - 内容提取脚本 v2
 * 
 * 双模式:
 *   A) 拦截 Shopee API 响应 → 结构化数据（最全）
 *   B) DOM 提取 → 备用方案
 * 
 * 永不 403 —— 因为用的是用户浏览器本身的会话。
 * 用户在 Shopee 搜索页正常浏览 → 扩展监听 API 响应 → 数据直接可用。
 */

// ==================== 工具函数 ====================

function parseNumber(text) {
  if (!text) return 0;
  let cleaned = text.replace(/[^0-9.,kK\u4e07]/g, '').trim();
  if (!cleaned) return 0;
  if (/[kK]/.test(cleaned)) return Math.round(parseFloat(cleaned.replace(/[kK]/, '')) * 1000);
  if (/\u4e07/.test(cleaned)) return Math.round(parseFloat(cleaned.replace(/\u4e07/, '')) * 10000);
  cleaned = cleaned.replace(/,/g, '');
  return parseInt(cleaned) || 0;
}

function parsePrice(text) {
  if (!text) return 0;
  let cleaned = text.replace(/[^0-9.,]/g, '').replace(/,/g, '');
  let match = cleaned.match(/([\d.]+)/);
  return match ? parseFloat(match[1]) : 0;
}

// ==================== 模式A: 拦截 API ====================

let apiProducts = [];
let apiCaptured = false;

/**
 * 拦截 Shopee 搜索 API 的响应
 * Shopee 内部使用 fetch/XHR 调 /api/v4/search/search_items
 * 或 graphql 查询
 */
function interceptApi() {
  // 拦截 fetch
  const originalFetch = window.fetch;
  window.fetch = async function(...args) {
    const response = await originalFetch.apply(this, args);
    const url = (typeof args[0] === 'string' ? args[0] : args[0]?.url || '').toLowerCase();
    
    // 匹配 Shopee 搜索 API
    if (url.includes('search_items') || url.includes('search/search') || url.includes('/api/v4/search/') || (url.includes('/api/') && (url.includes('search') || url.includes('product')) && url.includes('?keyword'))) {
      try {
        const clone = response.clone();
        const data = await clone.json();
        const items = data?.data?.items || data?.items || [];
        
        if (items.length > 0) {
          apiProducts = items.map((item, idx) => {
            const ib = item.item_basic || item;
            return {
              name: (ib.name || '').slice(0, 200),
              price: ib.price ? ib.price / 100000 : 0,
              price_min: ib.price_min ? ib.price_min / 100000 : 0,
              price_max: ib.price_max ? ib.price_max / 100000 : 0,
              price_before_discount: ib.price_before_discount ? ib.price_before_discount / 100000 : 0,
              sold: ib.historical_sold || ib.sold || 0,
              rating: ib.item_rating?.rating_star || 0,
              rating_count: ib.item_rating?.rating_count?.[0] || 0,
              shop_location: ib.shop_location || '',
              stock: ib.stock || 0,
              liked_count: ib.liked_count || 0,
              cmt_count: ib.cmt_count || 0,
              image: ib.image || '',
              shopid: ib.shopid || '',
              itemid: ib.itemid || '',
              url: ib.shopid && ib.itemid ? 
                `${window.location.protocol}//${window.location.hostname}/${(ib.name || '-').replace(/\s+/g, '-')}-i.${ib.shopid}.${ib.itemid}` : '',
              rank: idx + 1,
              _source: 'api'
            };
          });
          apiCaptured = true;
          chrome.runtime.sendMessage({ action: 'apiDataReady', count: apiProducts.length });
        }
      } catch(e) {
        // API 解析失败，静默
      }
    }
    return response;
  };

  // 拦截 XHR
  const originalXHROpen = XMLHttpRequest.prototype.open;
  const originalXHRSend = XMLHttpRequest.prototype.send;
  
  XMLHttpRequest.prototype.open = function(method, url) {
    this._xhrUrl = (typeof url === 'string' ? url : url?.toString() || '').toLowerCase();
    return originalXHROpen.apply(this, arguments);
  };
  
  XMLHttpRequest.prototype.send = function(...args) {
    this.addEventListener('load', function() {
      const url = this._xhrUrl || '';
      if (url.includes('search_items') || url.includes('search/search') || url.includes('/api/v4/search/') || (url.includes('/api/') && (url.includes('search') || url.includes('product')) && url.includes('?keyword'))) {
        try {
          const data = JSON.parse(this.responseText);
          const items = data?.data?.items || data?.items || [];
          if (items.length > 0) {
            apiProducts = items.map((item, idx) => {
              const ib = item.item_basic || item;
              return {
                name: (ib.name || '').slice(0, 200),
                price: ib.price ? ib.price / 100000 : 0,
                sold: ib.historical_sold || ib.sold || 0,
                rating: ib.item_rating?.rating_star || 0,
                shop_location: ib.shop_location || '',
                stock: ib.stock || 0,
                liked_count: ib.liked_count || 0,
                shopid: ib.shopid || '',
                itemid: ib.itemid || '',
                rank: idx + 1,
                _source: 'api'
              };
            });
            apiCaptured = true;
            chrome.runtime.sendMessage({ action: 'apiDataReady', count: apiProducts.length });
          }
        } catch(e) {}
      }
    });
    return originalXHRSend.apply(this, args);
  };
}

// ==================== 模式B: DOM 提取 ====================

function extractFromDOM() {
  let products = [];
  let items = document.querySelectorAll("[data-sqe='item']");
  if (items.length > 0) {
    items.forEach((el, index) => {
      try {
        let nameEl = el.querySelector("div[class*='name']") || el.querySelector("a[class*='name']") || el.querySelector("[aria-label*='Product card:']") || el.querySelector("[aria-label*='product:']");
        let name = nameEl ? (nameEl.innerText || nameEl.getAttribute('title') || nameEl.getAttribute('aria-label') || '').trim() : '';
        if (!name) name = el.innerText.split('\n')[0] || '';
        if (!name || name.trim().length < 3) {
          let lines = el.innerText.split('\n').map(l => l.trim()).filter(l => l.length > 5 && !/^[RM\u20b1$]/.test(l) && !/^\d+$/.test(l));
          name = lines[0] || name;
        }
        if (name.startsWith('Product card:') || name.startsWith('View product:')) {
          name = name.replace(/^(Product card:|View product:)\s*/i, '').trim();
        }

        let priceEl = el.querySelector("div[class*='price']") || el.querySelector("span[class*='price']") || el.querySelector("a.uaKe53") || el.querySelector("[class*='uaKe']") || el.querySelector("[class*='currency']");
        let price = 0;
        if (priceEl) { price = parsePrice(priceEl.innerText); }
        else { let priceMatch = el.innerText.match(/[RM\u20b1$]\s*([\d,]+\.?\d*)/); if (priceMatch) price = parseFloat(priceMatch[1].replace(/,/g, '')); }

        let soldEl = el.querySelector("[class*='sold']") || el.querySelector("[class*='sales']") || el.querySelector("[class*='sale']") || el.querySelector("[class*='rating']");
        let sold = 0;
        if (soldEl) { sold = parseNumber(soldEl.innerText); }
        else {
          let text = el.innerText;
          let soldMatch = text.match(/(\d[\d,.]*[kK]?)\s*(sold|terjual)/i) || text.match(/(sold|terjual)\s*(\d[\d,.]*[kK]?)/i) || text.match(/\u5df2\u552e\s*([\d,.]+[kK\u4e07]?)/) || text.match(/(\d+)\s*(\u4ef6)/);
          if (soldMatch) sold = parseNumber(soldMatch[0]);
        }

        let shopEl = el.querySelector("div[class*='shop']") || el.querySelector("a[class*='shop']") || el.querySelector("[class*='shopee']") || el.querySelector("[class*='store']");
        let shop = shopEl ? shopEl.innerText.trim() : '';
        if (shop === name || name.startsWith(shop)) shop = '';

        let linkEl = el.querySelector("a[href]");
        let url = linkEl ? linkEl.getAttribute('href') : '';
        if (url && !url.startsWith('http')) url = window.location.protocol + '//' + window.location.hostname + url;

        if (name) {
          products.push({ name: name.slice(0, 200), price, sold, shop, url, rank: index + 1, _source: 'dom' });
        }
      } catch(e) {}
    });
  }

  // 策略2: 商品链接备用
  if (products.length === 0) {
    let links = document.querySelectorAll("a[href*='/product-'], a[href*='-i.']");
    links.forEach((link, index) => {
      try {
        let card = link.closest('[class*="card"]') || link.closest('li') || link.closest('[class*="item"]');
        let name = (link.innerText || link.getAttribute('title') || '').trim();
        if (!name) return;
        let containerText = card ? card.innerText : link.innerText;
        let lines = containerText.split('\n').filter(l => l.trim());
        let price = 0, sold = 0;
        for (let line of lines) {
          if (/[0-9]/.test(line) && /[$.\u20b1\u20a9\u00a5RM]/.test(line)) price = parsePrice(line);
          if (/sold|\u5df2\u552e|\u5df2\u5356\u51fa|\u4ef6/.test(line.toLowerCase())) sold = parseNumber(line);
        }
        products.push({ name: name.slice(0, 200), price, sold, shop: '', url: link.getAttribute('href') || '', rank: index + 1, _source: 'dom' });
      } catch(e) {}
    });
  }

  let seen = new Set();
  return products.filter(p => { let key = p.name.slice(0, 20); if (seen.has(key)) return false; seen.add(key); return true; });
}

// ==================== 启动 ====================

try {
  interceptApi();
} catch(e) {
  console.warn('Shopee Scout API intercept init failed:', e);
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'extract') {
    let products = apiProducts.length > 0 ? apiProducts : extractFromDOM();
    let debugHtml = '';
    if (!products.length > 0 || (products.length > 0 && products[0].price === 0)) {
      let card = document.querySelector('[data-sqe="item"]');
      if (card) debugHtml = card.innerHTML.substring(0, 3000);
    }
    sendResponse({
      success: products.length > 0,
      count: products.length,
      products: products,
      source: apiProducts.length > 0 ? 'api' : 'dom',
      url: window.location.href,
      timestamp: new Date().toISOString(),
      debugHtml: debugHtml
    });
  }
  return true;
});