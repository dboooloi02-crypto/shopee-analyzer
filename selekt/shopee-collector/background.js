// ── Shopee 選品採集工具 · Background Service Worker (架構修正版) ────
//
// ⚠️ MV3 核心問題：Service Worker 閒置即休眠，長時 await 全部中斷。
//
// ✅ 解法：background.js 只做「認領任務 + 開 Tab」兩件事，不等待。
//          所有等待 / 解析 / 回傳邏輯全部交給 content.js 在頁面內執行。
//          頁面執行環境不受 SW 生命週期限制。
//
// 流程：
//   BG  → poll pending_ext → claim → chrome.tabs.create(url#selekt-task-ID)
//   content.js → 偵測 hash → waitForCards → POST 後端 → sendMessage(CLOSE_TAB)
//   BG  → 收到 CLOSE_TAB → chrome.tabs.remove

const BACKEND     = 'http://localhost:8000/api';
const POLL_MS     = 3000;
let _pollTimer    = null;
let _activePorts  = 0;

// ── Alarm 備援（每分鐘）────────────────────────────────────────────
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create('selektPoll', { periodInMinutes: 1 });
  console.log('[SELEKT] 已安裝 v1.1（輕量 BG 版）');
});
chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create('selektPoll', { periodInMinutes: 1 });
});
chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === 'selektPoll') pollAndCollect();
});

// ── Port 保活（relay.js 維持連線讓 SW 持續運行）───────────────────
chrome.runtime.onConnect.addListener(port => {
  if (port.name !== 'selekt-keepalive') return;
  _activePorts++;
  if (_activePorts === 1) {
    pollAndCollect();
    _pollTimer = setInterval(pollAndCollect, POLL_MS);
  }
  port.onDisconnect.addListener(() => {
    _activePorts = Math.max(0, _activePorts - 1);
    if (_activePorts === 0 && _pollTimer) {
      clearInterval(_pollTimer);
      _pollTimer = null;
    }
  });
});

// ── onMessage：relay.js 即時觸發 / content.js 請求關閉 Tab ────────
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'POLL_NOW') {
    pollAndCollect().then(() => sendResponse({ ok: true }));
    return true;
  }
  if (msg.action === 'CLOSE_TAB' && sender.tab?.id) {
    chrome.tabs.remove(sender.tab.id).catch(() => {});
    sendResponse({ ok: true });
    return false;
  }
});

// ── 輪詢：取得 pending_ext 任務 ───────────────────────────────────
async function pollAndCollect() {
  let tasks;
  try {
    const r = await fetch(`${BACKEND}/collect/pending-tasks`);
    if (!r.ok) return;
    tasks = (await r.json()).tasks || [];
  } catch { return; }

  for (const task of tasks) {
    await processTask(task);  // 幾乎瞬間完成，不阻塞 SW
  }
}

// ── 處理任務：只做「認領」和「開 Tab」────────────────────────────
async function processTask(task) {
  // 1. 認領（CAS，防重複）
  try {
    const r = await fetch(`${BACKEND}/collect/claim/${task.id}`, { method: 'POST' });
    if (!(await r.json()).ok) return;
  } catch { return; }

  console.log(`[SELEKT] ▶ Job#${task.id} "${task.keyword}" market=${task.market||'tw'} — 開啟採集 Tab`);

  // 2. 依市場代碼決定域名，開啟對應 Shopee 搜索頁
  const MARKET_DOMAINS = {
    tw: 'shopee.tw',     sg: 'shopee.sg',
    my: 'shopee.com.my', id: 'shopee.co.id',
    th: 'shopee.co.th',  ph: 'shopee.ph',
    vn: 'shopee.vn',     br: 'shopee.com.br',
  };
  const _domain = MARKET_DOMAINS[task.market || 'tw'] || 'shopee.tw';
  const url = `https://${_domain}/search?keyword=${encodeURIComponent(task.keyword)}#selekt-task-${task.id}`;
  try {
    await chrome.tabs.create({ url, active: false });
    // ✅ 這裡直接 return，不等待任何事情，SW 可以安心休眠
  } catch (e) {
    console.error('[SELEKT] 無法開啟 Tab:', e);
    // Tab 開不了，重置任務讓下次重試
    fetch(`${BACKEND}/jobs/${task.id}/reset`, { method: 'POST' }).catch(() => {});
  }
}
