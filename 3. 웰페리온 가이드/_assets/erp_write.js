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
  // notice_save·notice_delete(coo/notice 공지서식) = 같은 GAS 프로젝트에 얹혀 있어 여기 포함(배 1082 · 거울 없음).
  // notice_list(읽기)는 화면이 gasCall 을 직접 부른다 — 관문 대상 아님.
  // product_plan_save·product_plan_delete(cpo/product 상품기획) = 화면 실제 목적지(TODO_API_URL)가 같은 업무
  //   GAS 라 여기 포함(배 1039 폼류4종 · api_write._gas_key 와 같은 표 · 거울 없음).
  var WRITE = /^(todo_(add|update|delete|done|sign|reset|opinion|opinion_delete|upload|remove_file|orphan_cleanup)|approval_rep_(escalate|sign_upload|cancel)|notice_(save|delete)|product_plan_(save|delete))$/;

  function _json(r) {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }

  /* 관문 POST 하나 — 요청마다 idem 열쇠(uuid)를 본문에 실어 보낸다 (배 960 M7 · 2026-09-04).
     서버가 GAS 쓰기를 끝냈는데 응답만 유실되면(전파 끊김) 종전에는 곧바로 GAS 로 다시 보내
     snapshot_append·todo_add 가 시트에 두 줄이 됐다. 이제 같은 열쇠로 관문에 한 번 더 묻는다 —
     서버가 write_log 에서 그 열쇠를 찾아 저장해 둔 응답을 그대로 돌려준다(GAS 재전송 없음).
     그마저 못 닿으면 각 함수가 종전대로 GAS 로 폴백하는데, 그 본문에도 같은 열쇠가 실려 있다
     (params 를 그대로 쓰므로 — GAS 는 모르는 칸이라 무시한다. 나중에 GAS 가 가릴 수 있는 자리). */
  function _uuid() {
    if (w.crypto && w.crypto.randomUUID) { try { return w.crypto.randomUUID(); } catch (e) {} }
    return 'i' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }
  function gwPost(path, params) {
    if (path === '/api/write' && params && !params.idem) params.idem = _uuid();
    var send = function () {
      return fetch(path, {
        method: 'POST', cache: 'no-store',
        headers: { 'Content-Type': 'text/plain;charset=utf-8' },
        body: JSON.stringify(params)
      });
    };
    return send().catch(function () { return send(); });   // 응답 유실만 1회 더 — 중복은 서버가 가른다
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
    return gwPost('/api/write', params).then(_json)
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
    return gwPost('/api/write', params).then(function (r) {
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

  /* ── 구매요청·자산대장 쓰기 관문 (배 960 #H · CFO 매출지출현황) ───────────────────────────
     운영요약 GAS 로 가던 구매요청·자산 쓰기 8종을 같은 규칙으로 /api/write 에 태운다.
     erpTodoCall 과 같이 **파싱된 객체**를 돌려준다 — 화면 _rawCall 이 이미 `.then(r=>r.json())` 로 받고 있어
     호출부는 fetch 한 줄이 함수 한 줄로 바뀔 뿐이다. GAS 갈래는 종전 화면 규약 그대로 POST(본문 JSON) 하나다
     — 이 GAS 는 GET 쿼리를 안 받는다(화면이 처음부터 POST 만 썼다). erpTodoCall 의 GET/POST 판정을 쓰면 안 된다.

     제외(종전 GAS 직행 그대로):
       · list · asset_list = 읽기다. 사람이 누르는 즉시 바뀌는 원장이라 거울에 안 얹는다 —
         TTL 0 거울은 GAS 왕복에 DB 왕복만 더해 느려진다(읽기 거울 = 레인 E 의 무거운 집계 6종뿐).
       · sales_month·sales_ops·sales_dept·labor_time·proc_summary 등 집계 읽기 = 레인 E 거울(/api/sales/…).
     서버 목적지 판정(api_write._gas_key · _PROC_GAS_ACTIONS)과 같은 목록이다 — 한쪽만 늘리면 안 된다.
     ★이름이 짧고 흔하다(add·delete·status·photo) — 다른 화면이 같은 이름을 관문에 보내면 목적지가 샌다.
       2026-09-04 기준 관문을 타는 화면 전수 확인: 겹치는 액션 없음(api_write.py 자체점검이 회원·접수 쪽을 지킨다). */
  var PROC_WRITE = /^(add|delete|status|photo|asset_(update|label|issue|del))$/;

  function erpProcCall(gasUrl, params) {
    var gas = function () {
      return fetch(gasUrl, {
        method: 'POST', headers: { 'Content-Type': 'text/plain;charset=utf-8' },
        body: JSON.stringify(params)
      }).then(function (r) { return r.json(); });
    };
    if (!ERP_ON || !params || !PROC_WRITE.test(String(params.action || ''))) return gas();
    return gwPost('/api/write', params).then(_json)
      .then(function (d) { return (d && d.error === 'server-forward-failed') ? gas() : d; })
      .catch(function (e) {
        console.warn('[구매쓰기관문] /api/write 실패 → GAS 폴백:', e && e.message);
        return gas();
      });
  }

  /* ── 리셉션 업무·라커관리 관문 (배 960 #9i) ───────────────────────────────────────────────
     두 화면(coo/리셉션 업무/index.html · .../라커관리/index.html)은 실시간 셀 편집이라 5분 캐시 거울을
     앞에 두면 방금 옆자리에서 고친 칸이 되돌아간 것처럼 보인다. 그래서 거울을 앞에 안 둔다.
       쓰기(update·append) → /api/write : write_log 에 먼저 적고(이중기록) 같은 본문을 GAS 로 넘긴다.
       읽기(그 밖)         → /api/reception-ops : 매번 GAS 로 그대로 나가고, 서버는 응답을 「마지막 정상본」으로만 쥔다.
     서버가 GAS 에 못 닿으면(server-forward-failed) 화면이 종전 GAS 직접 경로로 **한 번만** 간다 —
     쓰기는 그 시점에 GAS 가 아직 안 써졌으므로 안전하고, 중복 발송이 안 되게 두 번 시도하지 않는다.
     읽기는 그 GAS 직행마저 막히면(구글 안내 HTML) 서버가 실어 준 마지막 정상본(_stale)으로 화면을 살린다 —
     저장본 없는 PC(처음 들어온 컴퓨터)가 빈 화면에서 막히던 자리다(화면 주석 2026-08-03).
     erpCheckPost 처럼 fetch 와 같은 Response 를 돌려준다 — 두 화면의 call() 이 res.text()·r.json() 을 그대로 한다.
     목적지 판정(tab=리셉션 업무 · db=라커)은 서버가 한다 — 화면이 준 주소로는 절대 안 보낸다(api_reception_ops.target).
     되돌리기 = 두 화면의 erpRcPost(...) 를 종전 fetch 로 되돌리거나 ERP_ON 을 false 로. */
  var RC_WRITE = /^(update|append)$/;

  function erpRcPost(gasUrl, payload) {
    var gas = function () {
      return fetch(gasUrl, {
        method: 'POST', redirect: 'follow', credentials: 'omit', cache: 'no-store',
        headers: { 'Content-Type': 'text/plain;charset=utf-8' },
        body: JSON.stringify(payload)
      });
    };
    if (!ERP_ON || !payload || !(payload.tab || payload.db)) return gas();
    var isWrite = RC_WRITE.test(String(payload.action || ''));
    var fail = function () { return { via: 'gas', stale: null }; };   // 관문을 못 씀 — 종전 경로로
    return gwPost(isWrite ? '/api/write' : '/api/reception-ops', payload).then(function (r) {
      if (!r.ok) return fail();                                       // 401(미로그인)·5xx
      // 본문은 복제본으로만 들여다본다 — 원본 r 은 호출부가 그대로 .text()/.json() 할 수 있어야 한다.
      return r.clone().json().then(function (d) {
        return (d && d.error === 'server-forward-failed')
          ? { via: 'gas', stale: d._stale || null }                   // GAS 는 아직 안 써졌다 — 화면이 직접
          : { via: 'gateway', r: r };                                 // GAS 응답 그대로(unauthorized 포함)
      }, fail);
    }, fail).then(function (v) {
      if (v.via === 'gateway') return v.r;
      return gas().catch(function (e) {
        if (!isWrite && v.stale) {
          console.warn('[리셉션관문] 서버·GAS 둘 다 실패 → 서버 마지막 정상본 표시');
          return new Response(JSON.stringify(v.stale), { headers: { 'Content-Type': 'application/json' } });
        }
        throw e;
      });
    });
  }

  /* ── 오누띠·직원피드백 쓰기 관문 (배 1039 폼류4종) ────────────────────────────────────────
     회원·문의 GAS(FUNNEL_EXEC_URL)로 가던 오누띠 상태변경·직원피드백 접수 2종을 같은 규칙으로 /api/write 에 태운다.
     erpProcCall 과 같은 모양 — 화면은 이미 fetch(gasUrl,...).then(r=>r.json()) 이라 파싱된 객체를 돌려준다.

     제외(종전 GAS 직행 그대로):
       · ohnutti_team_list·staff_feedback_list = 읽기.
       · staff_feedback_photo = 화면이 부르는 실제 GAS(FB_PHOTO_URL)가 다섯 목적지 어디에도 없는 별도 프로젝트
         (콘텐츠 접수 재사용) — 서버 표에 없으면 400 이 되므로 새 env 키가 생기기 전까진 관문에 올리지 않는다.
     서버 목적지 판정(api_write._gas_key · _FUNNEL_GAS_ACTIONS)과 같은 목록이다 — 한쪽만 늘리면 안 된다. */
  var FUNNEL_WRITE = /^(ohnutti_status_update|staff_feedback_submit)$/;

  function erpFunnelCall(gasUrl, params) {
    var gas = function () {
      return fetch(gasUrl, {
        method: 'POST', redirect: 'follow',
        headers: { 'Content-Type': 'text/plain;charset=utf-8' },
        body: JSON.stringify(params)
      }).then(function (r) { return r.json(); });
    };
    if (!ERP_ON || !params || !FUNNEL_WRITE.test(String(params.action || ''))) return gas();
    return gwPost('/api/write', params).then(_json)
      .then(function (d) { return (d && d.error === 'server-forward-failed') ? gas() : d; })
      .catch(function (e) {
        console.warn('[오누띠·피드백쓰기관문] /api/write 실패 → GAS 폴백:', e && e.message);
        return gas();
      });
  }

  w.erpTodoCall = erpTodoCall;
  w.erpTodoIsWrite = function (action) { return WRITE.test(String(action || '')); };
  w.erpCheckPost = erpCheckPost;
  w.erpCheckIsWrite = function (action) { return CHECK_WRITE.test(String(action || '')); };
  w.erpRcPost = erpRcPost;
  w.erpRcIsWrite = function (action) { return RC_WRITE.test(String(action || '')); };
  w.erpProcCall = erpProcCall;
  w.erpProcIsWrite = function (action) { return PROC_WRITE.test(String(action || '')); };
  w.erpFunnelCall = erpFunnelCall;
  w.erpFunnelIsWrite = function (action) { return FUNNEL_WRITE.test(String(action || '')); };
})(window);
