/* 업무·결재 SSOT 쓰기 관문 하나 (배 960 #6b · 2026-09-04 시토)
   ─────────────────────────────────────────────────────────────────────────────
   업무·결재 GAS(TODO_API_URL)로 가던 호출을 ERP 도메인(erp.wellperion.com)에서만 서버 /api/write 로 보낸다.
   서버는 write_log 에 먼저 적고 같은 본문을 그대로 GAS 에 넘긴 뒤 GAS 응답을 그대로 돌려준다(이중 기록).
   서버에 못 닿거나(미로그인 401·서버 다운) 서버가 GAS 에 못 닿으면(server-forward-failed) 종전 GAS 직접 경로로 폴백 —
   실무진은 이전 여부를 못 느낀다. GitHub Pages(github.io)에서는 ERP_ON 이 false 라 종전 그대로다.

   읽기(todo_list·todo_scoreboard·ai_list·todo_categories 등)는 손대지 않는다 — 읽기 거울은 /api/todo (배 922 레인 T).
   되돌리기 = 아래 ERP_ON 을 false 로 두거나, 각 화면에서 erpTodoCall(...) 호출을 종전 fetch 로 되돌린다.

   쓰기 액션 정본 = 정의서 §4(status/briefs/운영모듈_GAS_AWS_DB_이전_정의서_20260904.md).
   서버 목적지 판정(api_write._gas_key)과 같은 접두사(todo_ · approval_rep_)를 쓴다 — 한쪽만 늘리면 안 된다. */
(function (w) {
  var ERP_ON = /^(erp\.wellperion\.com|15\.164\.151\.105)$/.test(location.hostname);
  // 쓰기만 관문을 탄다. todo_list·todo_scoreboard·todo_categories·ai_list 는 읽기라 제외.
  var WRITE = /^(todo_(add|update|delete|done|sign|reset|opinion|opinion_delete|upload|remove_file|orphan_cleanup)|approval_rep_(escalate|sign_upload|cancel))$/;

  function _json(r) {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }

  /* GAS 직접 경로 — 종전 화면 규약 그대로. 첨부(base64)와 긴 본문은 POST(주소줄 길이 한계), 나머지는 GET 쿼리.
     text/plain = CORS preflight(OPTIONS) 회피. GAS 는 doGet·doPost 어느 쪽이든 같은 _processTodoAction 을 탄다. */
  function gasCall(gasUrl, params) {
    var qs = Object.keys(params).map(function (k) {
      return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]);
    }).join('&');
    if (params.base64 || params.file || (gasUrl.length + qs.length + 1) > 1800) {
      return fetch(gasUrl, {
        method: 'POST', redirect: 'follow',
        headers: { 'Content-Type': 'text/plain;charset=utf-8' },
        body: JSON.stringify(params)
      }).then(_json);
    }
    return fetch(gasUrl + '?' + qs, { redirect: 'follow' }).then(_json);
  }

  /* 화면이 부르는 것 하나. 읽기·비ERP 도메인·관문 실패는 전부 종전 GAS 로 간다 — 응답 모양 무변경. */
  function erpTodoCall(gasUrl, params) {
    var gas = function () { return gasCall(gasUrl, params); };
    if (!ERP_ON || !params || !WRITE.test(String(params.action || ''))) return gas();
    return fetch('/api/write', {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain;charset=utf-8' },
      body: JSON.stringify(params)
    }).then(_json)
      .then(function (d) { return (d && d.error === 'server-forward-failed') ? gas() : d; })
      .catch(function (e) {
        console.warn('[업무쓰기관문] /api/write 실패 → GAS 폴백:', e && e.message);
        return gas();
      });
  }

  w.erpTodoCall = erpTodoCall;
  w.erpTodoIsWrite = function (action) { return WRITE.test(String(action || '')); };
})(window);
