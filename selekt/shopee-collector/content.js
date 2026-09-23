// Shopee 選品採集工具 - Content Script (v2 自主採集版)
// 在用戶已開啟 / BG 自動開啟的 Shopee 搜索頁中讀取商品 DOM 數據

(function () {
  'use strict';

  if (window.__shopeeCollectorLoaded) return;
  window.__shopeeCollectorLoaded = true;

  const _BACKEND = 'http://localhost:8000/api';

  // ── 等待商品卡片（CSR 頁面非同步渲染）────────────────────────────
  function waitForCards(timeout = 12000) {
    return new Promise((resolve) => {
      const SELECTORS = [
        'li.shopee-search-item-result__item',
        'div[data-sqe="item"]',
        'div.col-xs-2-4.shopee-search-item-result__item',
        'li[class*="col-xs"]',
      ];

      function findCards() {
        for (const sel of SELECTORS) {
          const els = document.querySelectorAll(sel);
          if (els.length > 2) return els;   // 至少 3 個才算真正渲染完成
        }
        const fallback = document.querySelectorAll('a[href*="/product/"]');
        return fallback.length > 2 ? fallback : null;
      }

      const existing = findCards();
      if (existing) { resolve(existing); return; }

      const deadline = Date.now() + timeout;
      const observer = new MutationObserver(() => {
        const cards = findCards();
        if (cards) { observer.disconnect(); resolve(cards); }
        else if (Date.now() > deadline) { observer.disconnect(); resolve(null); }
      });
      observer.observe(document.body, { childList: true, subtree: true });
      setTimeout(() => { observer.disconnect(); resolve(findCards()); }, timeout);
    });
  }

  // ── 選品打分 ─────────────────────────────────────────────────────
  function scoreProduct(product) {
    let score = 0;
    const notes = [];
    const sales = product.sales || 0;
    if (sales >= 1000)     { score += 15; }
    else if (sales >= 500) { score += 12; notes.push('銷量中等'); }
    else if (sales >= 100) { score += 8;  notes.push('銷量偏低'); }
    else if (sales >= 10)  { score += 4;  notes.push('銷量很低'); }
    else                   {              notes.push('銷量極少，風險高'); }

    const rating = product.rating || 0;
    const ratingCount = product.ratingCount || 0;
    if (rating >= 4.7 && ratingCount >= 50)      { score += 15; }
    else if (rating >= 4.5 && ratingCount >= 20) { score += 12; }
    else if (rating >= 4.0)                       { score += 8;  notes.push('評分一般'); }
    else if (rating >= 3.0)                       { score += 4;  notes.push('評分偏低'); }
    else                                          {              notes.push('評分差或無評分'); }

    const name = (product.name || '').toLowerCase();
    const hasVariant = /組合|套裝|多入|多色|多尺寸|pack|set|combo/.test(name);
    score += hasVariant ? 10 : 5;
    if (!hasVariant) notes.push('建議增加組合規格');

    const price = product.price || 0;
    if (price >= 150 && price <= 499)      { score += 15; }
    else if (price >= 99 && price < 150)   { score += 10; notes.push('低價區間競爭較激烈'); }
    else if (price >= 500 && price <= 999) { score += 12; }
    else if (price < 99)                   { score += 3;  notes.push('超低價紅海，利潤風險高'); }
    else                                   { score += 8;  notes.push('高價品需強視覺支撐'); }

    score += 10;
    notes.push('圖片品質請人工確認');

    const isRisky = /玻璃|電器|電子|插頭|食品|飲料|刀|剪/.test(name);
    score += isRisky ? 2 : 9;
    if (isRisky) notes.push('⚠ 品類有風險，謹慎評估');

    score += 8;
    const hasLegalRisk = /認證|3C|安規|接觸食品|嬰兒|兒童/.test(name);
    score += hasLegalRisk ? 2 : 8;
    if (hasLegalRisk) notes.push('⚠ 可能需認證，確認法規');

    let verdict = '直接放棄';
    if (score >= 80)      verdict = '強烈推薦';
    else if (score >= 70) verdict = '可以測款';
    else if (score >= 60) verdict = '謹慎考慮';

    return { score, verdict, notes };
  }

  // ── 取「第一個有內容」的元素：依優先順序逐一嘗試選擇器（名稱抓不到 aria-label 時的備援）──
  function queryFirst(card, selectors) {
    for (const sel of selectors) {
      const el = card.querySelector(sel);
      if (el && el.textContent.trim()) return el;
    }
    return null;
  }

  let _debugLogged = false;

  // ── DOM 解析 ─────────────────────────────────────────────────────
  // Shopee PC 商城用 Tailwind 動態 class，無法靠 class 名稱穩定定位欄位，
  // 改用：① 卡片 [role="group"][aria-label="Product card: 商品名"] 取真實商品名
  //       ② 正則掃描卡片全文字找「$價格」「已售N」「評分(數量)」
  function parseCards(cards) {
    const results = [];

    cards.forEach((card, idx) => {
      try {
        // ① 商品名：優先用 aria-label（穩定，不會抓到優惠角標）
        let name = '';
        const group = card.querySelector('[role="group"][aria-label]');
        if (group) {
          name = (group.getAttribute('aria-label') || '')
            .replace(/^Product card:\s*/i, '')
            .trim();
        }
        if (!name) {
          const nameEl = queryFirst(card, [
            '[data-sqe="name"]', '.Cve6sh', '._1NoI8_',
            'div[class*="name"]', 'span[class*="name"]', 'div[class*="ellipsis"]',
          ]);
          name = nameEl ? nameEl.textContent.trim() : '';
        }
        if (!name) return;

        // ② 卡片全文字（壓縮多餘空白），用正則抓價格/銷量/評分
        const text = (card.textContent || '').replace(/\s+/g, ' ').trim();

        let price = 0;
        const priceM = text.match(/\$\s?([\d,]+(?:\.\d+)?)/);
        if (priceM) price = parseFloat(priceM[1].replace(/,/g, '')) || 0;

        let sales = 0;
        const salesM = text.match(/已售[出]?\s*([\d.,]+)\s*([kK萬万]?)/);
        if (salesM) {
          sales = parseFloat(salesM[1].replace(/,/g, '')) || 0;
          const unit = (salesM[2] || '').toLowerCase();
          if (unit === 'k') sales *= 1000;
          if (unit === '萬' || unit === '万') sales *= 10000;
          sales = Math.round(sales);
        }

        // 評分常見呈現："4.8" 或 "4.8(1.2k)"／"4.8 (123)"
        let rating = 0, ratingCount = 0;
        const ratingM = text.match(/([0-5]\.\d)\s*\(\s*([\d.,]+)\s*([kK萬万]?)\s*\)/);
        if (ratingM) {
          rating = parseFloat(ratingM[1]) || 0;
          let rc = parseFloat(ratingM[2].replace(/,/g, '')) || 0;
          const unit = (ratingM[3] || '').toLowerCase();
          if (unit === 'k') rc *= 1000;
          if (unit === '萬' || unit === '万') rc *= 10000;
          ratingCount = Math.round(rc);
        }

        const linkEl = card.closest('a[href*="shopee."]') || card.querySelector('a[href*="shopee."]') || card.querySelector('a');
        const imgEl  = card.querySelector('img');
        const href  = linkEl ? (linkEl.href || '') : '';
        const image = imgEl  ? (imgEl.src || imgEl.dataset.src || '') : '';

        if (!_debugLogged && idx < 3) {
          console.log('[SELEKT][DEBUG]', JSON.stringify({ name, price, sales, rating, ratingCount, text: text.slice(0, 200) }));
          if (idx === 2) _debugLogged = true;
        }

        const product = { idx: idx + 1, name, price, sales, rating, ratingCount, href, image };
        results.push({ ...product, ...scoreProduct(product) });
      } catch (_) {}
    });

    return results;
  }

  // ════════════════════════════════════════════════════════════════
  // ██  後端採集模式（自主執行，不依賴 BG 的長時 await）
  // ════════════════════════════════════════════════════════════════
  // BG 開啟此 Tab 時會在 URL hash 加入 #selekt-task-{id}
  // content.js 偵測到後，自行完成：等待 → 解析 → POST 後端 → 通知 BG 關閉
  const _taskMatch = location.hash.match(/#selekt-task-(\d+)/);
  if (_taskMatch) {
    const _taskId  = parseInt(_taskMatch[1]);
    const _keyword = new URLSearchParams(location.search).get('keyword') || '';
    // 從 hash 讀取市場代碼（BG 傳入），fallback 依域名偵測
    const _hashMarket = location.hash.match(/market=([a-z]+)/)?.[1];
    const _domainMarket = (() => {
      const h = location.hostname;
      if (h.endsWith('shopee.tw'))      return 'tw';
      if (h.endsWith('shopee.sg'))      return 'sg';
      if (h.endsWith('shopee.com.my'))  return 'my';
      if (h.endsWith('shopee.co.id'))   return 'id';
      if (h.endsWith('shopee.co.th'))   return 'th';
      if (h.endsWith('shopee.ph'))      return 'ph';
      if (h.endsWith('shopee.vn'))      return 'vn';
      if (h.endsWith('shopee.com.br'))  return 'br';
      return 'tw';
    })();
    const _market = _hashMarket || _domainMarket;

    console.log(`[SELEKT] 自主採集模式 Task#${_taskId} 關鍵字: ${_keyword}`);

    (async () => {
      let products = [];
      let error    = null;

      try {
        // 等待商品卡片（最多 12 秒，因為 Shopee React 有時很慢）
        const cards = await waitForCards(12000);

        if (!cards || cards.length === 0) {
          error = 'no_cards_found';
          console.warn(`[SELEKT] Task#${_taskId} 未找到商品卡片`);
        } else {
          // 滾動觸發 Shopee 無限滾動懶加載 + 每一步都立刻解析並累積
          // （Shopee 列表為虛擬滾動，滾走的卡片會被卸載，
          //  若只在最後查一次 DOM，最上面那批商品早就被卸載、抓不到）
          console.log(`[SELEKT] Task#${_taskId} 開始分段滾動加載更多商品...`);

          const _SELECTORS = [
            'li.shopee-search-item-result__item',
            'div[data-sqe="item"]',
            'div.col-xs-2-4.shopee-search-item-result__item',
            'li[class*="col-xs"]',
          ];
          function queryAllCards() {
            for (const sel of _SELECTORS) {
              const els = document.querySelectorAll(sel);
              if (els.length > 2) return els;
            }
            return null;
          }

          const _seen = new Map(); // key: href || name+price，跨多次滾動去重
          function collectCurrentBatch() {
            const els = queryAllCards() || cards;
            for (const p of parseCards(els)) {
              const key = p.href || `${p.name}__${p.price}`;
              if (!_seen.has(key)) _seen.set(key, p);
            }
          }

          // 初始批次（滾動前先抓一次，確保第一畫面的商品不漏）
          collectCurrentBatch();

          const SCROLL_TIMES = 8;
          const SCROLL_DELAY = 1500; // ms，等 Shopee XHR 返回並渲染
          for (let _i = 0; _i < SCROLL_TIMES; _i++) {
            // 每次只往下滾一個畫面高度，而非直接跳到頁尾，
            // 讓懶加載逐批渲染，避免一次性虛擬卸載掉上方卡片
            window.scrollBy({ top: window.innerHeight * 0.85, behavior: 'smooth' });
            await new Promise(r => setTimeout(r, SCROLL_DELAY));
            collectCurrentBatch();
            console.log(`[SELEKT] 滾動 ${_i + 1}/${SCROLL_TIMES}，累積 ${_seen.size} 件`);
          }

          products = Array.from(_seen.values());
          console.log(`[SELEKT] Task#${_taskId} 滾動後解析完成 ${products.length} 件`);
        }

        // 直接 POST 後端（content script 有 localhost:8000 權限）
        const resp = await fetch(`${_BACKEND}/collect/from-extension`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ task_id: _taskId, keyword: _keyword, products, error, market: _market })
        });

        if (!resp.ok) {
          console.error(`[SELEKT] Task#${_taskId} 回傳後端失敗 HTTP ${resp.status}`);
        } else {
          console.log(`[SELEKT] Task#${_taskId} ✅ 完成，共 ${products.length} 件`);
        }
      } catch (e) {
        console.error(`[SELEKT] Task#${_taskId} 例外錯誤`, e);
        // 嘗試把錯誤回傳後端
        try {
          await fetch(`${_BACKEND}/collect/from-extension`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ task_id: _taskId, keyword: _keyword, products: [], error: String(e), market: _market })
          });
        } catch {}
      } finally {
        // 通知 BG 關閉此 Tab
        try {
          chrome.runtime.sendMessage({ action: 'CLOSE_TAB' });
        } catch {}
      }
    })();
  }

  // ════════════════════════════════════════════════════════════════
  // ██  手動採集模式（用戶在 Shopee 手動點擊擴充按鈕時）
  // ════════════════════════════════════════════════════════════════
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.action === 'PING') {
      sendResponse({ ok: true });
      return false;
    }
    if (msg.action === 'COLLECT') {
      (async () => {
        try {
          const cards = await waitForCards(8000);
          if (!cards || cards.length === 0) {
            sendResponse({ ok: false, products: [], count: 0,
              error: '找不到商品卡片，請確認已在 Shopee 搜索結果頁' });
            return;
          }
          const products = parseCards(cards);
          sendResponse({ ok: true, products, url: location.href, count: products.length });
        } catch (e) {
          sendResponse({ ok: false, products: [], count: 0, error: String(e) });
        }
      })();
      return true; // 保持 channel 開放等 async
    }
  });

})();
