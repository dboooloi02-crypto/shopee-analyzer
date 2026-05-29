/** Shopee Scout - 直接注入提取脚本 */
(function() {
  function parseNumber(text) {
    if (!text) return 0;
    let cleaned = (text+'').replace(/[^0-9.,kK\u4e07]/g, '').trim();
    if (!cleaned) return 0;
    if (/[kK]/.test(cleaned)) return Math.round(parseFloat(cleaned.replace(/[kK]/, '')) * 1000);
    if (/\u4e07/.test(cleaned)) return Math.round(parseFloat(cleaned.replace(/\u4e07/, '')) * 10000);
    cleaned = cleaned.replace(/,/g, '');
    return parseInt(cleaned) || 0;
  }

  function parsePrice(text) {
    if (!text) return 0;
    let cleaned = (text+'').replace(/[^0-9.,]/g, '').replace(/,/g, '');
    let match = cleaned.match(/([\d.]+)/);
    return match ? parseFloat(match[1]) : 0;
  }

  /** 从页面JSON数据中提取商品（SSR嵌入数据） */
  function extractFromJson() {
    let products = [];
    try {
      let data = null;
      if (typeof __INITIAL_STATE__ !== 'undefined') data = __INITIAL_STATE__;
      else {
        let nd = document.getElementById('__NEXT_DATA__');
        if (nd) { try { data = JSON.parse(nd.textContent); } catch(e) {} }
      }
      if (!data) {
        let scripts = document.querySelectorAll('script[type="application/json"]');
        for (let s of scripts) {
          try {
            let d = JSON.parse(s.textContent);
            if (d && (d.items || d.data?.items)) { data = d; break; }
          } catch(e) {}
        }
      }
      if (!data) {
        for (let key of Object.keys(window)) {
          try {
            let val = window[key];
            if (val && typeof val === 'object' && val.items && Array.isArray(val.items) && val.items.length > 0) {
              let first = val.items[0];
              if (first.item_basic || first.name) { data = val; break; }
            }
          } catch(e) {}
        }
      }
      if (data) {
        let items = data?.data?.items || data?.items || data?.data?.search_result?.items || [];
        if (items.length === 0) {
          try {
            for (let k in data) {
              let v = data[k];
              if (v && v.items && Array.isArray(v.items)) { items = v.items; break; }
              if (v && v.data?.items) { items = v.data.items; break; }
            }
          } catch(e) {}
        }
        if (items.length > 0) {
          products = items.map((item, idx) => {
            let ib = item.item_basic || item;
            return {
              name: (ib.name || '').slice(0, 200),
              price: ib.price ? ib.price / 100000 : (parseFloat(ib.price) || 0),
              sold: ib.historical_sold || ib.sold || 0,
              rating: ib.item_rating?.rating_star || 0,
              shop: '',
              location: ib.shop_location || '',
              url: ib.shopid && ib.itemid ? window.location.protocol + '//' + window.location.hostname + '/' + (ib.name || '').replace(/\s+/g, '-') + '-i.' + ib.shopid + '.' + ib.itemid : '',
              rank: idx + 1,
              _source: 'json'
            };
          });
        }
      }
    } catch(e) {}
    return products;
  }

  /** 直接调 Shopee API（用当前浏览器 cookies） */
  function extractFromApiCall() {
    let products = [];
    try {
      let keyword = window.location.href.match(/[?&]keyword=([^&]+)/);
      if (!keyword) return products;
      keyword = decodeURIComponent(keyword[1]);
      let xhr = new XMLHttpRequest();
      xhr.open('GET', '/api/v4/search/search_items?keyword=' + encodeURIComponent(keyword) + '&by=relevancy&limit=60&newest=0', false);
      xhr.withCredentials = true;
      xhr.send();
      if (xhr.status === 200) {
        let data = JSON.parse(xhr.responseText);
        let items = data?.data?.items || [];
        if (items.length > 0) {
          products = items.map((item, idx) => {
            let ib = item.item_basic || item;
            return {
              name: (ib.name || '').slice(0, 200),
              price: ib.price ? ib.price / 100000 : 0,
              sold: ib.historical_sold || ib.sold || 0,
              rating: ib.item_rating?.rating_star || 0,
              shop: ib.shop_location || '',
              location: ib.shop_location || '',
              url: window.location.href,
              rank: idx + 1,
              _source: 'api'
            };
          });
        }
      }
    } catch(e) {}
    return products;
  }

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
          else { let pm = el.innerText.match(/[RM\u20b1$]\s*([\d,]+\.?\d*)/); if (pm) price = parseFloat(pm[1].replace(/,/g, '')); }
          let soldEl = el.querySelector("[class*='sold']") || el.querySelector("[class*='sales']") || el.querySelector("[class*='sale']") || el.querySelector("[class*='rating']");
          let sold = 0;
          if (soldEl) { sold = parseNumber(soldEl.innerText); }
          else { let text = el.innerText;
            let sm = text.match(/(\d[\d,.]*[kK]?)\s*(sold|terjual)/i) || text.match(/(sold|terjual)\s*(\d[\d,.]*[kK]?)/i) || text.match(/\u5df2\u552e\s*([\d,.]+[kK\u4e07]?)/) || text.match(/(\d+)\s*(\u4ef6)/);
            if (sm) sold = parseNumber(sm[0]); }
          let shopEl = el.querySelector("div[class*='shop']") || el.querySelector("a[class*='shop']") || el.querySelector("[class*='shopee']") || el.querySelector("[class*='store']");
          let shop = shopEl ? shopEl.innerText.trim() : '';
          if (shop === name || name.startsWith(shop)) shop = '';
          let malaysiaStates = ['Selangor','Kuala Lumpur','Penang','Johor','Malacca','Sarawak','Sabah','Perak','Pahang','Terengganu','Kelantan','Kedah','Negeri Sembilan','Perlis','Labuan','Putrajaya'];
          if (malaysiaStates.includes(shop)) shop = '';
          let rating = 0;
          let location = '';
          let cardText = el.innerText;
          let ratingMatch = cardText.match(/\b([45]\.\d)\b/);
          if (ratingMatch) rating = parseFloat(ratingMatch[1]);
          let locMatch = cardText.match(/\b(Selangor|Kuala Lumpur|Penang|Johor|Malacca|Sarawak|Sabah|Perak|Pahang|Terengganu|Kelantan|Kedah|Negeri Sembilan|Perlis|Labuan|Putrajaya)\b/i);
          if (locMatch) location = locMatch[1];
          let linkEl = el.querySelector("a[href]");
          let url = linkEl ? linkEl.getAttribute('href') : '';
          if (url && !url.startsWith('http')) url = window.location.protocol + '//' + window.location.hostname + url;
          if (name) { products.push({ name: name.slice(0, 200), price, sold, shop, url, rank: index + 1, _source: 'dom', rating: rating, location: location }); }
        } catch(e) {}
      });
    }
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
    return products.filter(p => { let k = p.name.slice(0, 20); if (seen.has(k)) return false; seen.add(k); return true; });
  }

  let products = extractFromJson();
  if (products.length === 0) products = extractFromApiCall();
  if (products.length === 0) products = extractFromDOM();

  let debugScan = [];
  try {
    let card = document.querySelector('[data-sqe="item"]');
    if (card) {
      let html = card.innerHTML;
      let imgEnd = html.lastIndexOf('</picture>');
      let afterImg = imgEnd > 0 ? html.substring(imgEnd + 10, imgEnd + 800) : html.substring(0, 800);
      afterImg = afterImg.substring(0, 600);
      let text = afterImg.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
      debugScan.push('[\u56fe\u7247\u540e\u6587\u672c] ' + text.substring(0, 200));
      debugScan.push('[\u56fe\u7247\u540eHTML] ' + afterImg.substring(0, 300));
      let parent = card.closest('[class*="shopee-search-item-result"]') || card.parentElement;
      if (parent) {
        let parentText = parent.innerText;
        let shopRelated = [];
        let lines = parentText.split('\n').map(l => l.trim()).filter(l => l.length > 2);
        for (let l of lines) {
          if (l.includes('RM') || l.includes('Product card') || l.includes('View product') || l.startsWith('http') || l.length > 80) continue;
          if (!/\d+\.?\d*/.test(l) || /[45]\.\d/.test(l)) {
            shopRelated.push(l);
          }
        }
        debugScan.push('[\u975e\u4ef7\u683c\u6587\u672c] ' + [...new Set(shopRelated)].slice(0,10).join(' | ').substring(0,200));
      }
    } else {
      debugScan.push('\u672a\u627e\u5230\u5546\u54c1\u5361\u7247');
    }
  } catch(e) { debugScan.push('\u626b\u63cf\u51fa\u9519: ' + e.message); }
  return { success: products.length > 0, count: products.length, products: products, source: 'dom', url: window.location.href, timestamp: new Date().toISOString(), debugScan: debugScan };
})()