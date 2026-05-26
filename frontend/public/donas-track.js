/* ============================================================
 *  Donas Tracker — auto-registra cada acesso ao site
 *  Envia POST /api/donas/acessos assim que a página carrega.
 *  Usa sendBeacon (resistente a navegação) com fallback fetch.
 * ============================================================ */
(function(){
  try {
    // Skip admin panel to avoid inflating stats
    if (location.pathname.indexOf('donaspainel') !== -1) return;
  } catch(e) { /* ignore */ }

  function track(){
    try {
      var ua = navigator.userAgent || '';
      var body = JSON.stringify({
        path: (location.pathname || '') + (location.search || ''),
        ua: ua,
        device: /Mobi|Android|iPhone|iPad/i.test(ua) ? 'Mobile' : 'Desktop'
      });
      var url = '/api/donas/acessos';

      // Prefer sendBeacon (não bloqueia, sobrevive a navegação)
      if (navigator.sendBeacon) {
        try {
          var blob = new Blob([body], { type: 'application/json' });
          if (navigator.sendBeacon(url, blob)) return;
        } catch(e) { /* fallthrough to fetch */ }
      }

      // Fallback
      fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body,
        keepalive: true,
        credentials: 'same-origin'
      }).catch(function(){});
    } catch(e) { /* swallow */ }
  }

  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    track();
  } else {
    document.addEventListener('DOMContentLoaded', track, { once: true });
  }
})();
