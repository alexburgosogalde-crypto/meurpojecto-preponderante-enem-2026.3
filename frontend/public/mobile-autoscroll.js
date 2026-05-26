/* Mobile-only helpers:
   1) Auto-scroll the chat to bottom whenever new content appears.
   2) Replicate original ENEM mobile header: logo on the LEFT, power (logout)
      icon on the RIGHT. Hide bottom tab bar (não existe no original).
*/
(function(){
  if (window.innerWidth > 820) return;

  // ---------- 1) Auto-scroll ----------
  var lastHeight = 0;
  var scrollIfNeeded = function() {
    try {
      var docH = document.documentElement.scrollHeight;
      if (docH > lastHeight) {
        lastHeight = docH;
        setTimeout(function(){
          window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'smooth' });
        }, 80);
      }
    } catch(e) {}
  };

  // ---------- 2) Header power button + remove duplicate SAIR from progress bar ----------
  function injectPowerButton(){
    var header = document.querySelector('.css-14le3h7');
    if (!header) return;

    // Find original SAIR (power) handler in tab bar
    var tabBar = document.querySelector('.css-17m656a');
    var tabSair = null;
    if (tabBar) {
      // Look for a child containing the word "Sair"
      var children = tabBar.querySelectorAll('.css-6nj1yj, .css-1t95esl, .css-vzoa3y');
      for (var i = 0; i < children.length; i++) {
        var txt = (children[i].textContent || '').trim();
        if (txt === 'Sair' || txt === 'SAIR') {
          tabSair = children[i];
          break;
        }
      }
      // Fallback to last child
      if (!tabSair && children.length) tabSair = children[children.length - 1];
    }

    if (!header.querySelector('.mobile-power-btn')) {
      var btn = document.createElement('button');
      btn.className = 'mobile-power-btn';
      btn.setAttribute('aria-label', 'Sair');
      btn.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>';
      btn.addEventListener('click', function(e){
        e.preventDefault();
        var s = document.querySelector('.css-17m656a .css-6nj1yj, .css-17m656a .css-1t95esl');
        // Find by text again at click-time (DOM might have been recreated)
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

    // REMOVE the SAIR item from the progress/tab bar so it doesn't appear twice
    if (tabBar) {
      var items = tabBar.querySelectorAll('.css-6nj1yj, .css-1t95esl, .css-vzoa3y');
      for (var j = 0; j < items.length; j++) {
        var t = (items[j].textContent || '').trim().toLowerCase();
        if (t === 'sair') {
          items[j].style.display = 'none';
          items[j].setAttribute('data-hidden-sair', '1');
        }
      }
    }
  }

  function start(){
    var observer = new MutationObserver(function(){
      scrollIfNeeded();
      injectPowerButton();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    scrollIfNeeded();
    injectPowerButton();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
