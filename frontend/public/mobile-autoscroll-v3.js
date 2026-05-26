/* Chat helpers (desktop + mobile):
   Auto-scroll the page to the very bottom whenever the chat grows so the
   latest bot message is always visible above the sticky input.
   Uses scrollHeight directly (more reliable than scrollIntoView on iOS Safari
   which doesn't account for the bottom URL/tab bar in innerHeight).
*/
(function(){
  var isMobile = window.innerWidth <= 820;

  // ---------- Auto-scroll ----------
  var lastChildrenCount = 0;
  var lastListHeight = 0;
  var forceScrollUntil = 0;

  function maxScrollAll(){
    try {
      // Body / window
      var maxTop = (document.documentElement.scrollHeight || document.body.scrollHeight) + 9999;
      window.scrollTo(0, maxTop);
      document.documentElement.scrollTop = maxTop;
      document.body.scrollTop = maxTop;
      // Internal scroll containers used by INEP
      ['.css-1c88qfb', '.css-wbgyl1', '.css-kzkx1t', '.css-1gic6yg'].forEach(function(sel){
        var el = document.querySelector(sel);
        if (el) el.scrollTop = el.scrollHeight + 9999;
      });
    } catch(e) {}
  }

  function checkChat(){
    try {
      var list = document.querySelector('.css-1gic6yg');
      if (!list) return;
      var kids = list.children.length;
      var h = list.scrollHeight;
      if (kids > lastChildrenCount || h > lastListHeight) {
        lastChildrenCount = kids;
        lastListHeight = h;
        // Hold an "aggressive scroll" window for the next 1.5s so async
        // bubble appearance / layout shifts still get pinned to bottom.
        forceScrollUntil = Date.now() + 1500;
      }
      if (Date.now() < forceScrollUntil) {
        maxScrollAll();
      }
    } catch(e) {}
  }

  // Run faster than typical bot delay
  setInterval(checkChat, 120);

  // Also pin to bottom right after user submits (Enter or send button)
  document.addEventListener('keydown', function(ev){
    if (ev.key === 'Enter') forceScrollUntil = Date.now() + 1800;
  }, true);
  document.addEventListener('click', function(ev){
    var t = ev.target;
    if (!t) return;
    var btn = t.closest && t.closest('button');
    if (btn) forceScrollUntil = Date.now() + 1800;
  }, true);

  // ---------- Mobile-only header SAIR button ----------
  if (!isMobile) return;

  function injectPowerButton(){
    var header = document.querySelector('.css-14le3h7');
    if (!header) return;
    var tabBar = document.querySelector('.css-17m656a');
    var tabSair = null;
    if (tabBar) {
      var children = tabBar.querySelectorAll('.css-6nj1yj, .css-1t95esl, .css-vzoa3y');
      for (var i = 0; i < children.length; i++) {
        var txt = (children[i].textContent || '').trim();
        if (txt === 'Sair' || txt === 'SAIR') { tabSair = children[i]; break; }
      }
      if (!tabSair && children.length) tabSair = children[children.length - 1];
    }
    if (!header.querySelector('.mobile-power-btn')) {
      var btn = document.createElement('button');
      btn.className = 'mobile-power-btn';
      btn.setAttribute('aria-label', 'Sair');
      btn.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>';
      btn.addEventListener('click', function(e){
        e.preventDefault();
        var found = null;
        var all = document.querySelectorAll('.css-17m656a .css-6nj1yj, .css-17m656a .css-1t95esl, .css-17m656a .css-vzoa3y');
        for (var i = 0; i < all.length; i++) {
          if ((all[i].textContent || '').trim().toLowerCase() === 'sair') { found = all[i]; break; }
        }
        if (found) found.click();
        else if (tabSair) tabSair.click();
        else window.location.href = '/home.html';
      });
      header.appendChild(btn);
    }
    if (tabBar) {
      var items = tabBar.querySelectorAll('.css-6nj1yj, .css-1t95esl, .css-vzoa3y');
      for (var j = 0; j < items.length; j++) {
        var t = (items[j].textContent || '').trim().toLowerCase();
        if (t === 'sair') { items[j].style.display = 'none'; items[j].setAttribute('data-hidden-sair', '1'); }
      }
    }
  }
  setInterval(injectPowerButton, 500);
})();
