/* ERP 쓰기 관문 — 업무·결재 SSOT(erpTodoCall · 배 960 #6b) + 점검·전사일정(erpCheckPost · 배 960 #5b) (2026-09-04 시토)
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

  /* ── 점검 3부서·전사일정 쓰기 관문 (배 960 #5b) ────────────────────────────────────────────
     점검 GAS(CHECK_API)·전사일정 GAS 로 가던 화면 POST 를 같은 규칙으로 /api/write 에 태운다.
     erpTodoCall 과 다른 점 하나 = **fetch 와 같은 Response 를 돌려준다**. 점검 화면 14곳이 저마다
     `.then(r=>r.json())` · `await r.json()` · `.catch(()=>{})` 로 받고 있어, 파싱된 객체를 돌려주면
     호출부를 전부 고쳐야 한다. 관문 하나 바꾸는 게 싸다(호출부는 함수 이름만 바뀐다).

     제외(종전 GAS 직행 그대로):
       · notify · notify_round = 텔레그램 발신만·원장 안 건드림. 관문이 폴백하면 같은 알림이 두 번 나간다.
       · upload_evidence = 5MB base64 사진(전사일정 증빙) — 원장 쓰기가 아니고 본문만 크다.
       · syncSeedItems = GAS 안에서 no-op.
     서버 목적지 판정(api_write._gas_key)과 같은 목록이다 — 한쪽만 늘리면 안 된다. */
  var CHECK_WRITE = /^(save|saveBoard|saveItems|snapshot_append|unlock_round|save_insp_memo|save_facility_measure|save_facility_notes|fcheck_ranges_save|vendor_save|save_schedule)$/;

  function erpCheckPost(gasUrl, params) {
    var gas = function () {
      return fetch(gasUrl, {
        method: 'POST', redirect: 'follow',
        headers: { 'Content-Type': 'text/plain;charset=utf-8' },
        body: JSON.stringify(params)
      });
    };
    if (!ERP_ON || !params || !CHECK_WRITE.test(String(params.action || ''))) return gas();
    return fetch('/api/write', {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain;charset=utf-8' },
      body: JSON.stringify(params)
    }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      // 본문은 복제본으로만 들여다본다 — 원본 r 은 호출부가 그대로 .json() 할 수 있어야 한다.
      return r.clone().json().then(function (d) {
        if (d && d.error === 'server-forward-failed') return gas();
        // 공용 보드는 5분 동기화를 안 기다리고 그 열쇠만 즉시 다시 떠온다(배 926 /api/board/{key}/refresh).
        if (d && d.ok !== false && params.action === 'saveBoard' && params.key) {
          fetch('/api/board/' + encodeURIComponent(params.key) + '/refresh', { method: 'POST' }).catch(function () {});
        }
        return r;
      });
    }).catch(function (e) {
      console.warn('[점검쓰기관문] /api/write 실패 → GAS 폴백:', e && e.message);
      return gas();
    });
  }

  w.erpTodoCall = erpTodoCall;
  w.erpTodoIsWrite = function (action) { return WRITE.test(String(action || '')); };
  w.erpCheckPost = erpCheckPost;
  w.erpCheckIsWrite = function (action) { return CHECK_WRITE.test(String(action || '')); };
})(window);
