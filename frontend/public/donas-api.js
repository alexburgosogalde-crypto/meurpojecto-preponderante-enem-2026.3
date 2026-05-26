/* ============================================================
 *  Donas API client — fala com o backend FastAPI/MongoDB
 *  Usa rotas /api/donas/* (mesma origem, via ingress)
 *  Mantém localStorage como cache/fallback offline.
 * ============================================================ */
(function(){
  var API = '/api/donas';

  function jsonOrNull(p){
    return p.then(function(r){ if(!r.ok) return null; return r.json(); }).catch(function(){ return null; });
  }

  function post(path, body){
    return jsonOrNull(fetch(API + path, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body || {})
    }));
  }
  function patch(path, body){
    return jsonOrNull(fetch(API + path, {
      method:'PATCH', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body || {})
    }));
  }
  function get(path){ return jsonOrNull(fetch(API + path)); }
  function del(path){ return jsonOrNull(fetch(API + path, { method:'DELETE' })); }

  window.DonasAPI = {
    // Cadastros
    upsertCadastro: function(data){ return post('/cadastros', data); },
    listCadastros: function(){ return get('/cadastros'); },
    deleteCadastro: function(cpf){ return del('/cadastros/' + encodeURIComponent(cpf)); },
    clearCadastros: function(){ return del('/cadastros'); },

    // Inscrições — POST dispara Telegram no backend
    createInscricao: function(data){ return post('/inscricoes', data); },
    listInscricoes: function(){ return get('/inscricoes'); },
    updateStatusInscricao: function(id, status){ return patch('/inscricoes/' + encodeURIComponent(id), { status: status }); },
    deleteInscricao: function(id){ return del('/inscricoes/' + encodeURIComponent(id)); },
    clearInscricoes: function(){ return del('/inscricoes'); },

    // Acessos
    logAcesso: function(data){ return post('/acessos', data || {}); },
    listAcessos: function(){ return get('/acessos'); },
    clearAcessos: function(){ return del('/acessos'); },

    // Stats
    stats: function(){ return get('/stats'); },

    // Config
    getConfig: function(){ return get('/config'); },
    saveConfig: function(c){ return jsonOrNull(fetch(API + '/config', {
      method:'PUT', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(c || {})
    })); }
  };
})();
