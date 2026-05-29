document.addEventListener('DOMContentLoaded', () => {
  const extractBtn = document.getElementById('extractBtn');
  const exportBtn = document.getElementById('exportBtn');
  const statusEl = document.getElementById('status');
  const urlDisplay = document.getElementById('urlDisplay');
  const resultArea = document.getElementById('resultArea');
  const countEl = document.getElementById('count');
  const tableBody = document.getElementById('tableBody');
  const sourceEl = document.getElementById('sourceBadge');

  let currentProducts = [];
  let currentSource = '';

  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs[0];
    if (!tab) {
      statusEl.textContent = '\u65e0\u6cd5\u83b7\u53d6\u5f53\u524d\u6807\u7b7e\u9875';
      return;
    }
    const url = tab.url || '';
    if ((url.includes('shopee.') || url.includes('xiapibuy.com')) && url.includes('search')) {
      urlDisplay.textContent = '\u2713 ' + url.substring(0, 50) + '...';
      extractBtn.disabled = false;
      statusEl.textContent = '\u5c31\u7eea\uff0c\u70b9\u51fb\u63d0\u53d6';
    } else {
      urlDisplay.textContent = '\u2717 \u8bf7\u5148\u6253\u5f00 Shopee \u641c\u7d22\u9875';
      statusEl.textContent = '\u5728 Shopee \u641c\u7d22\u5173\u952e\u8bcd\u540e\u518d\u8bd5';
    }
  });

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.action === 'apiDataReady') {
      statusEl.textContent = `API \u6570\u636e\u5df2\u5c31\u7eea (${msg.count}\u4ef6)\uff0c\u70b9\u51fb\u63d0\u53d6`;
    }
  });

  extractBtn.addEventListener('click', async () => {
    extractBtn.disabled = true;
    statusEl.textContent = '\u63d0\u53d6\u4e2d...';
    try {
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      const tab = tabs[0];
      let response;
      try {
        response = await chrome.tabs.sendMessage(tab.id, { action: 'extract' });
      } catch(e) {
        if (tab.url && tab.url.includes('xiapibuy')) {
          const results = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            files: ['content/extract.js']
          });
          response = results[0]?.result;
        } else {
          throw e;
        }
      }
      if (response && response.success) {
        currentProducts = response.products || [];
        currentSource = response.source || 'dom';
        countEl.textContent = currentProducts.length;
        if (sourceEl) {
          let sourceLabels = { 'api': 'API\u62e6\u622a \u2713', 'json': 'JSON\u6570\u636e', 'dom': 'DOM\u63d0\u53d6' };
          sourceEl.textContent = sourceLabels[currentSource] || 'DOM\u63d0\u53d6';
          let sourceClasses = { 'api': 'badge-api', 'json': 'badge-api', 'dom': 'badge-dom' };
          sourceEl.className = 'badge ' + (sourceClasses[currentSource] || 'badge-dom');
        }
        tableBody.innerHTML = '';
        currentProducts.forEach((p, i) => {
          const row = document.createElement('tr');
          if ((p._source === 'api' || p._source === 'json') && p.rating) {
            row.innerHTML = `
              <td>${i + 1}</td>
              <td class="name-cell" title="${p.name || ''}">${(p.name || '').slice(0, 50)}</td>
              <td class="price-cell">RM${p.price?.toFixed(2) || p.price || 0}</td>
              <td class="sold-cell">${p.sold || 0}</td>
              <td class="rating-cell">${(p.rating || 0).toFixed(1)}\u2b50</td>
              <td class="shop-cell">${p.shop_location || p.location || ''}</td>
            `;
          } else {
            let showRating = p.rating > 0 ? p.rating.toFixed(1) + '\u2b50' : (p.location || '-');
            row.innerHTML = `
              <td>${i + 1}</td>
              <td class="name-cell" title="${p.name || ''}">${(p.name || '').slice(0, 50)}</td>
              <td class="price-cell">RM${p.price || 0}</td>
              <td class="sold-cell">${p.sold || 0}</td>
              <td class="rating-cell">${showRating}</td>
              <td class="shop-cell">${p.shop || p.location || ''}</td>
            `;
          }
          tableBody.appendChild(row);
        });
        resultArea.style.display = 'block';
        statusEl.textContent = `\u6210\u529f\u63d0\u53d6 ${currentProducts.length} \u4ef6\u5546\u54c1 (${currentSource === 'api' ? 'API\u62e6\u622a' : 'DOM\u63d0\u53d6'})`;
      } else {
        statusEl.textContent = '\u63d0\u53d6\u5931\u8d25\uff1a\u65e0\u6cd5\u8bfb\u53d6\u9875\u9762\u6570\u636e';
      }
      if (response && response.debugScan) {
        const debugEl = document.getElementById('debugInfo');
        debugEl.style.display = 'block';
        debugEl.textContent = '--- \u9875\u9762\u5143\u7d20\u626b\u63cf ---\\n' + response.debugScan.join('\\n');
      }
    } catch (err) {
      statusEl.textContent = '\u63d0\u53d6\u5931\u8d25\uff1a' + err.message;
    } finally {
      extractBtn.disabled = false;
    }
  });

  exportBtn.addEventListener('click', () => {
    if (currentProducts.length === 0) return;
    const hasApiFields = currentProducts.some(p => (p._source === 'api' || p._source === 'json') && p.rating);
    let header, rows;
    if (hasApiFields) {
      header = '\u6392\u540d,\u5546\u54c1\u540d,\u4ef7\u683c,\u9500\u91cf,\u8bc4\u5206,\u5e97\u94fa,\u5730\u5740,\u94fe\u63a5';
      rows = currentProducts.map((p, i) => [
        i + 1,
        `"${(p.name || '').replace(/"/g, '""')}"`,
        p.price || 0,
        p.sold || 0,
        p.rating || 0,
        `"${(p.shop_location || '').replace(/"/g, '""')}"`,
        p.stock || 0,
        p.liked_count || 0,
        p.cmt_count || 0,
        `"${(p.url || '').replace(/"/g, '""')}"`
      ].join(','));
    } else {
      header = '\u6392\u540d,\u5546\u54c1\u540d,\u4ef7\u683c,\u9500\u91cf,\u8bc4\u5206,\u5e97\u94fa,\u5730\u5740,\u94fe\u63a5';
      rows = currentProducts.map((p, i) => [
        i + 1,
        `"${(p.name || '').replace(/"/g, '""')}"`,
        p.price,
        p.sold,
        (p.rating || 0).toFixed(1),
        `"${(p.shop || '').replace(/"/g, '""')}"`,
        `"${(p.location || '').replace(/"/g, '""')}"`,
        `"${(p.url || '').replace(/"/g, '""')}"`
      ].join(','));
    }
    const csv = [header, ...rows].join('\\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    chrome.downloads.download({ url: url, filename: 'shopee_scout_' + new Date().toISOString().slice(0, 10) + '.csv', saveAs: true });
    statusEl.textContent = 'CSV \u5df2\u5bfc\u51fa';
  });
});