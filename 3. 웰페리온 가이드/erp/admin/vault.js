/* GM 금고 문 — 화면 쪽 모듈 (배 12843 · 2026-09-19 시토).
 * 서버 = server/erp_api/api_vault.py. 문 = 로그인한 cao@ 세션 + GM 패스키(Windows Hello 등) 둘 다.
 * 쓰는 법(화면): <script src="vault.js"></script> 뒤
 *   WellVault.status()                        → {passkeys, mode, unlocked, ...}
 *   WellVault.registerPasskey(code, label)    → 첫 등록만 결재 GM 코드 필요 · 두 번째부터는 먼저 unlock()
 *   WellVault.unlock()                        → 지문/얼굴 확인 → 5분 잠금해제
 *   WellVault.listItems('gm'|'partner')       → 제목·가림표만
 *   WellVault.revealItem('gm'|'partner', id)  → {user, pw, note, url}
 *   WellVault.importPaste(text)               → 붙여넣은 표(TSV/CSV) → {added, updated, skipped}
 * 잠금해제 표는 이 닫힘 안 변수에만 둔다 — localStorage·sessionStorage·쿠키에 값·표를 안 남긴다.
 * 암호화 모드 = B(서버 봉투). PRF(A) 전환 준비: 등록 때 인증기의 PRF 지원 여부만 서버에 알린다(출력값은 안 보낸다).
 */
(function () {
  var token = '', tokenExp = 0;

  function b64d(s) {
    s = s.replace(/-/g, '+').replace(/_/g, '/');
    while (s.length % 4) s += '=';
    var bin = atob(s), u = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
    return u.buffer;
  }
  function b64e(buf) {
    var u = new Uint8Array(buf), s = '';
    for (var i = 0; i < u.length; i++) s += String.fromCharCode(u[i]);
    return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }
  function call(method, path, body) {
    var h = { 'Content-Type': 'application/json' };
    if (token && tokenExp * 1000 > Date.now()) h['X-Vault-Token'] = token;
    return fetch('/api/vault/' + path, { method: method, headers: h, credentials: 'same-origin',
      body: body ? JSON.stringify(body) : undefined })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (d) {
          if (!r.ok || d.ok === false) { var e = new Error(d.error || ('HTTP ' + r.status)); e.status = r.status; throw e; }
          return d;
        });
      });
  }
  function ids(list) {
    return (list || []).map(function (c) { return Object.assign({}, c, { id: b64d(c.id) }); });
  }

  function registerPasskey(code, label) {
    return call('POST', 'register/options', { code: code || '' }).then(function (d) {
      var o = d.options;
      o.challenge = b64d(o.challenge);
      o.user = Object.assign({}, o.user, { id: b64d(o.user.id) });
      o.excludeCredentials = ids(o.excludeCredentials);
      o.extensions = { prf: {} };        // 지원 여부 측정용 — A 모드 전환 판단 근거
      return navigator.credentials.create({ publicKey: o });
    }).then(function (c) {
      var ext = c.getClientExtensionResults ? c.getClientExtensionResults() : {};
      return call('POST', 'register/verify', {
        label: label || '', prf: !!(ext.prf && ext.prf.enabled),
        credential: { id: c.id, rawId: b64e(c.rawId), type: c.type,
          response: { clientDataJSON: b64e(c.response.clientDataJSON), attestationObject: b64e(c.response.attestationObject),
            transports: c.response.getTransports ? c.response.getTransports() : [] } }
      });
    });
  }

  function unlock() {
    return call('POST', 'unlock/options').then(function (d) {
      var o = d.options;
      o.challenge = b64d(o.challenge);
      o.allowCredentials = ids(o.allowCredentials);
      return navigator.credentials.get({ publicKey: o });
    }).then(function (c) {
      var r = c.response;
      return call('POST', 'unlock/verify', {
        credential: { id: c.id, rawId: b64e(c.rawId), type: c.type,
          response: { clientDataJSON: b64e(r.clientDataJSON), authenticatorData: b64e(r.authenticatorData),
            signature: b64e(r.signature), userHandle: r.userHandle ? b64e(r.userHandle) : null } }
      });
    }).then(function (d) { token = d.token; tokenExp = d.exp; return { unlocked: true, exp: d.exp }; });
  }

  window.WellVault = {
    status: function () { return call('GET', 'status'); },
    isUnlocked: function () { return !!token && tokenExp * 1000 > Date.now(); },
    lock: function () { token = ''; tokenExp = 0; },
    registerPasskey: registerPasskey,
    unlock: unlock,
    listItems: function (compartment) { return call('GET', 'items?compartment=' + encodeURIComponent(compartment || 'gm')); },
    revealItem: function (compartment, id) { return call('POST', 'reveal', { compartment: compartment, id: id }); },
    importPaste: function (text) { return call('POST', 'import', { text: text }); }
  };
})();
