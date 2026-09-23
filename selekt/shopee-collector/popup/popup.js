// Shopee 選品採集工具 - Popup Script
'use strict';

// ── 狀態 ────────────────────────────────────────────────────────────
let allProducts = [];
let savedProducts = [];
let currentTab = 'collect';

// ── 初始化 ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await loadSaved();
  await checkPage();
  bindEvents();
  updateSavedCountTab();
});

// ── 頁面狀態檢查 ─────────────────────────────────────────────────────
async function checkPage() {
  const dot  = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  const btn  = document.getElementById('btn-collect');

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url) throw new Error('no tab');

    if (!tab.url.includes('shopee.tw')) {
      dot.className  = 'status-dot error';
      text.innerHTML = '請先前往 <strong>shopee.tw</strong> 搜索頁';
      btn.disabled   = true;
      return;
    }

    // Bug Fix #4：從 URL query params 正確取得搜索關鍵字，而非路徑片段
    let displayName = 'Shopee';
    try {
      const tabUrl = new URL(tab.url);
      const keyword = tabUrl.searchParams.get('keyword') ||
                      tabUrl.searchParams.get('q') ||
                      tabUrl.pathname.split('/').filter(Boolean).pop() ||
                      'Shopee';
      displayName = decodeURIComponent(keyword);
    } catch (_) { /* keep default */ }

    // Ping content script
    try {
      await chrome.tabs.sendMessage(tab.id, { action: 'PING' });
      dot.className  = 'status-dot ready';
      text.innerHTML = '已就緒 · <strong>' + esc(displayName) + '</strong>';
      btn.disabled   = false;
    } catch {
      // Content script not injected yet – inject manually
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] });
      dot.className  = 'status-dot ready';
      text.innerHTML = '已就緒 · 點擊按鈕開始採集';
      btn.disabled   = false;
    }
  } catch (e) {
    dot.className  = 'status-dot error';
    text.innerHTML = '無法連接頁面，請重試';
    btn.disabled   = true;
  }
}

// ── 採集 ─────────────────────────────────────────────────────────────
async function collect() {
  const dot  = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  const btn  = document.getElementById('btn-collect');

  dot.className = 'status-dot pulse';
  text.innerHTML = '採集中，請稍候…';
  btn.disabled   = true;

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const resp  = await chrome.tabs.sendMessage(tab.id, { action: 'COLLECT' });

    if (!resp || !resp.ok) throw new Error('collect failed');

    allProducts = resp.products || [];

    dot.className  = 'status-dot ready';
    text.innerHTML = `採集完成 · 共 <strong>${allProducts.length}</strong> 件商品`;
    btn.disabled   = false;

    renderResults(allProducts);
    document.getElementById('total-count').textContent = allProducts.length;
    document.getElementById('results-count-tab').textContent = allProducts.length ? `(${allProducts.length})` : '';
    document.getElementById('btn-export').disabled = allProducts.length === 0;
    document.getElementById('btn-sync').disabled = allProducts.length === 0;

    switchTab('results');
  } catch (e) {
    dot.className  = 'status-dot error';
    text.innerHTML = '採集失敗，請重新整理 Shopee 頁面後再試';
    btn.disabled   = false;
  }
}

// ── 渲染結果 ─────────────────────────────────────────────────────────
function renderResults(products) {
  const list = document.getElementById('product-list');

  if (!products || products.length === 0) {
    list.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🔍</div>
        <div class="empty-text">找不到符合條件的商品<br>請嘗試調整篩選條件</div>
      </div>`;
    return;
  }

  // Bug Fix #1：移除 inline onclick，改用 data-* 屬性，由事件委派處理
  // （MV3 CSP 禁止 innerHTML 中的 inline event handler）
  list.innerHTML = products.map((p, i) => {
    const verdictClass = verdictToClass(p.verdict);
    const scoreColor   = scoreToColor(p.score);
    // Bug Fix #5：isSaved 判斷與 toggleSave 統一，同時比對 href 和 name
    const isSaved      = savedProducts.some(s =>
      (p.href && s.href === p.href) || s.name === p.name
    );
    const notesHtml    = (p.notes || []).map(n =>
      `<div class="note-item">${esc(n)}</div>`).join('');

    return `
    <div class="product-card" id="card-${i}">
      <div class="card-row1">
        ${p.image ? `<img class="product-img" src="${p.image}" alt="" onerror="this.style.display='none'">` : '<div class="product-img"></div>'}
        <div class="product-info">
          <div class="product-name" title="${esc(p.name)}">${esc(p.name)}</div>
          <div class="product-stats">
            <div class="stat">💰 <span>NT$${p.price || '—'}</span></div>
            <div class="stat">📦 <span>${formatSales(p.sales)}</span> 件售出</div>
            ${p.rating ? `<div class="stat">⭐ <span>${p.rating}</span></div>` : ''}
          </div>
        </div>
      </div>
      <div class="card-row2">
        <div class="score-badge">
          <div class="score-num" style="color:${scoreColor}">${p.score}</div>
          <div class="score-label">分</div>
        </div>
        <div class="score-bar-wrap">
          <div class="score-bar" style="width:${p.score}%;background:${scoreColor}"></div>
        </div>
        <span class="verdict-tag ${verdictClass}">${p.verdict}</span>
        <button class="btn-icon" style="margin-left:6px;font-size:16px" title="收藏"
          data-action="save" data-idx="${i}" id="star-${i}">${isSaved ? '⭐' : '☆'}</button>
        ${p.href ? `<a href="${p.href}" target="_blank" rel="noopener noreferrer">
          <button class="btn-icon" style="margin-left:2px" title="在 Shopee 查看">🔗</button>
        </a>` : ''}
        <button class="btn-icon" style="margin-left:2px" title="展開備註"
          data-action="expand" data-idx="${i}">▾</button>
      </div>
      <div class="notes-list">${notesHtml}</div>
    </div>`;
  }).join('');
}

function renderSaved() {
  const list = document.getElementById('saved-list');
  if (!savedProducts.length) {
    list.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">⭐</div>
        <div class="empty-text">尚無收藏<br>在結果頁點擊 ☆ 收藏潛力品</div>
      </div>`;
    return;
  }

  // Bug Fix #1：移除 inline onclick="removeSaved(...)"，改用 data-* 屬性
  list.innerHTML = savedProducts.map((p, i) => {
    const verdictClass = verdictToClass(p.verdict);
    const scoreColor   = scoreToColor(p.score);
    return `
    <div class="product-card">
      <div class="card-row1">
        ${p.image ? `<img class="product-img" src="${p.image}" alt="" onerror="this.style.display='none'">` : '<div class="product-img"></div>'}
        <div class="product-info">
          <div class="product-name" title="${esc(p.name)}">${esc(p.name)}</div>
          <div class="product-stats">
            <div class="stat">💰 <span>NT$${p.price || '—'}</span></div>
            <div class="stat">📦 <span>${formatSales(p.sales)}</span> 件售出</div>
            ${p.rating ? `<div class="stat">⭐ <span>${p.rating}</span></div>` : ''}
          </div>
        </div>
      </div>
      <div class="card-row2">
        <div class="score-badge">
          <div class="score-num" style="color:${scoreColor}">${p.score}</div>
          <div class="score-label">分</div>
        </div>
        <div class="score-bar-wrap">
          <div class="score-bar" style="width:${p.score}%;background:${scoreColor}"></div>
        </div>
        <span class="verdict-tag ${verdictClass}">${p.verdict}</span>
        <button class="btn-icon" style="margin-left:6px;font-size:14px;color:#e24b4a" title="移除收藏"
          data-action="remove" data-idx="${i}">✕</button>
        ${p.href ? `<a href="${p.href}" target="_blank" rel="noopener noreferrer">
          <button class="btn-icon" style="margin-left:2px" title="在 Shopee 查看">🔗</button>
        </a>` : ''}
      </div>
    </div>`;
  }).join('');
}

// ── 收藏 ─────────────────────────────────────────────────────────────
function toggleSave(e, idx) {
  e.stopPropagation();
  const product = allProducts[idx];
  if (!product) return;

  // Bug Fix #5：統一用 href（優先）或 name 來比對，與 renderResults 的 isSaved 一致
  const existIdx = savedProducts.findIndex(s =>
    (product.href && s.href === product.href) || s.name === product.name
  );
  const starBtn  = document.getElementById(`star-${idx}`);

  if (existIdx >= 0) {
    savedProducts.splice(existIdx, 1);
    if (starBtn) starBtn.textContent = '☆';
  } else {
    savedProducts.push({ ...product, savedAt: Date.now() });
    if (starBtn) starBtn.textContent = '⭐';
  }

  persistSaved();
  updateSavedCountTab();
}

function removeSaved(idx) {
  savedProducts.splice(idx, 1);
  persistSaved();
  renderSaved();
  updateSavedCountTab();
}

async function persistSaved() {
  await chrome.storage.local.set({ savedProducts });
}

async function loadSaved() {
  const data = await chrome.storage.local.get('savedProducts');
  savedProducts = data.savedProducts || [];
  renderSaved();
}

function updateSavedCountTab() {
  const el = document.getElementById('saved-count-tab');
  const textEl = document.getElementById('saved-count-text');
  if (el) el.textContent = savedProducts.length ? `(${savedProducts.length})` : '';
  if (textEl) textEl.textContent = `已存 ${savedProducts.length} 件潛力品`;
}

// ── 篩選 ─────────────────────────────────────────────────────────────
function applyFilters() {
  const keyword = document.getElementById('filter-input').value.trim().toLowerCase();
  const verdict = document.getElementById('filter-verdict').value;

  const filtered = allProducts.filter(p => {
    const matchKw = !keyword || p.name.toLowerCase().includes(keyword);
    const matchVd = !verdict || p.verdict === verdict;
    return matchKw && matchVd;
  });

  renderResults(filtered);
}

// ── 匯出 CSV ─────────────────────────────────────────────────────────
function exportCSV() {
  if (!allProducts.length) return;

  const headers = ['排名', '商品名稱', '售價(NT$)', '銷量', '評分', '總分', '評級', '備註', '連結'];
  const rows = allProducts.map((p, i) => [
    i + 1,
    `"${(p.name || '').replace(/"/g, '""')}"`,
    p.price || 0,
    p.sales || 0,
    p.rating || 0,
    p.score,
    p.verdict,
    `"${(p.notes || []).join(' | ').replace(/"/g, '""')}"`,
    // Bug Fix #7：href 也加引號保護，避免 URL 中的逗號破壞 CSV 格式
    `"${(p.href || '').replace(/"/g, '""')}"`,
  ]);

  const csv = [headers, ...rows].map(r => r.join(',')).join('\n');
  const bom = '\uFEFF'; // UTF-8 BOM for Excel
  const blob = new Blob([bom + csv], { type: 'text/csv;charset=utf-8;' });
  const url  = URL.createObjectURL(blob);

  const a = document.createElement('a');
  a.href     = url;
  a.download = `shopee_選品數據_${formatDate()}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Tab 切換 ─────────────────────────────────────────────────────────
function switchTab(name) {
  currentTab = name;
  document.querySelectorAll('.tab').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === name);
  });
  document.querySelectorAll('.panel').forEach(p => {
    p.classList.toggle('active', p.id === `panel-${name}`);
  });
  if (name === 'saved') renderSaved();
}

// ── 展開備註 ─────────────────────────────────────────────────────────
function toggleExpand(e, idx) {
  e.stopPropagation();
  const card = document.getElementById(`card-${idx}`);
  if (card) card.classList.toggle('expanded');
}

// ── 事件綁定 ─────────────────────────────────────────────────────────
function bindEvents() {
  document.getElementById('btn-collect').addEventListener('click', collect);
  document.getElementById('btn-refresh').addEventListener('click', checkPage);
  document.getElementById('btn-export').addEventListener('click', exportCSV);
  document.getElementById('btn-sync').addEventListener('click', syncToBackend);
  document.getElementById('btn-clear-saved').addEventListener('click', async () => {
    if (confirm('確定清空所有已收藏商品？')) {
      savedProducts = [];
      await persistSaved();
      renderSaved();
      updateSavedCountTab();
    }
  });

  document.querySelectorAll('.tab').forEach(t => {
    t.addEventListener('click', () => switchTab(t.dataset.tab));
  });

  document.getElementById('filter-input').addEventListener('input', applyFilters);
  document.getElementById('filter-verdict').addEventListener('change', applyFilters);

  // Bug Fix #1：事件委派取代 inline onclick，符合 MV3 CSP 規範
  // 處理結果列表中的「收藏」和「展開備註」按鈕
  document.getElementById('product-list').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const idx = parseInt(btn.dataset.idx, 10);
    if (btn.dataset.action === 'save')   toggleSave(e, idx);
    if (btn.dataset.action === 'expand') toggleExpand(e, idx);
  });

  // 處理已收藏列表中的「移除」按鈕
  document.getElementById('saved-list').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action="remove"]');
    if (!btn) return;
    removeSaved(parseInt(btn.dataset.idx, 10));
  });
}

// ── 工具函數 ─────────────────────────────────────────────────────────
function verdictToClass(verdict) {
  const map = { '強烈推薦': 'v-great', '可以測款': 'v-ok', '謹慎考慮': 'v-warn', '直接放棄': 'v-fail' };
  return map[verdict] || 'v-warn';
}

function scoreToColor(score) {
  if (score >= 80) return '#1D9E75';
  if (score >= 70) return '#5DCAA5';
  if (score >= 60) return '#EF9F27';
  return '#E24B4A';
}

function formatSales(n) {
  if (!n) return '—';
  if (n >= 10000) return (n / 10000).toFixed(1) + '萬';
  if (n >= 1000)  return (n / 1000).toFixed(1) + 'k';
  return n;
}

function formatDate() {
  const d = new Date();
  return `${d.getFullYear()}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}`;
}

function esc(str) {
  return (str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── 同步到後端 ──
const BACKEND = 'http://localhost:8000/api';

async function syncToBackend() {
  const btn = document.getElementById('btn-sync');
  if (!allProducts.length) return;
  btn.disabled = true;
  btn.textContent = '同步中...';
  try {
    // Bug Fix #2：從 active tab 的 URL 正確取得搜索關鍵字
    // 而非錯誤地讀取 popup 自身的 location.search（永遠為空）
    let kw = document.getElementById('filter-input')?.value?.trim() || '';
    if (!kw) {
      try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tab?.url) {
          const tabUrl = new URL(tab.url);
          kw = tabUrl.searchParams.get('keyword') ||
               tabUrl.searchParams.get('q') || '';
        }
      } catch (_) { /* ignore */ }
    }
    if (!kw) kw = '未知關鍵字';

    const resp = await fetch(`${BACKEND}/collect/from-extension`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keyword: kw, products: allProducts })
    });
    const data = await resp.json();
    btn.textContent = `✅ 已同步 ${data.saved} 件`;
    setTimeout(() => { btn.disabled = false; btn.textContent = '☁ 同步到後端'; }, 3000);
  } catch (e) {
    btn.textContent = '❌ 後端未啟動';
    setTimeout(() => { btn.disabled = false; btn.textContent = '☁ 同步到後端'; }, 3000);
  }
}
