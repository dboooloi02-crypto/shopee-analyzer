// ── relay.js — SELEKT 保活中繼腳本 ───────────────────────────────────
// 注入到 localhost:8002 頁面，作用：
//   1. 維持與 Background Service Worker 的 Port 連線 → 防止 SW 被休眠
//   2. 監聽頁面的 SELEKT_TRIGGER 自訂事件 → 立即通知 SW 輪詢

(function () {
  'use strict';

  let port = null;

  function connect() {
    try {
      port = chrome.runtime.connect({ name: 'selekt-keepalive' });
      port.onDisconnect.addListener(() => {
        port = null;
        // SW 被強制終止，1 秒後重連（會喚醒 SW）
        setTimeout(connect, 1000);
      });
      // 通知頁面插件已就緒
      window.dispatchEvent(new CustomEvent('SELEKT_EXT_READY'));
    } catch (e) {
      // 插件未安裝，靜默忽略
    }
  }

  // 頁面觸發採集事件 → 立即通知 Background 輪詢
  window.addEventListener('SELEKT_TRIGGER', () => {
    try {
      chrome.runtime.sendMessage({ action: 'POLL_NOW' }, () => {
        // 忽略回覆，fire-and-forget
        void chrome.runtime.lastError;
      });
    } catch {}
  });

  connect();
})();
