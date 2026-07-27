/*
  웰페리온 공용 '작업 현황 로그' 패널 — _assets/worklog_panel.js
  ────────────────────────────────────────────────────────────────
  사용법: 페이지 어디든 한 줄 마크업 + 스크립트 한 줄.
    <div data-worklog="cmo"></div>
    <script src="/wellperion-automation/_assets/worklog_panel.js"></script>
  role 값: ceo|cfo|chro|cmo|coo|cpo|cto — 해당 role의 로그·빠진 것만 걸러 표시.

  ★모달 모드(선택 · 2026-07-27 GM 지시 "맨 하단이 아닌 상단 탭 + 팝업으로 보게"):
    <div data-worklog="cpo" data-worklog-mode="modal" data-worklog-badge="#wlHeaderBadge"></div>
    - mode="modal" 이면 접힘 토글 줄(▸ 작업 현황 로그)을 만들지 않고 내용만 컨테이너에 채운다.
      → 페이지가 이 컨테이너를 자기 팝업(모달) 안에 두고, 여는 버튼은 페이지가 상단에 배치한다.
    - data-worklog-badge = 신규 '빠진 것' 개수를 표시할 요소의 CSS 선택자(상단 버튼 옆 배지).
      0건이면 그 요소를 숨긴다(평상시 조용 — 기본 모드와 같은 규칙).
    - 이 두 속성이 없으면 동작·모양이 종전과 100% 동일하다(ERP 본 페이지 cmo·coo 무영향).

  ★화면 스코프(선택 · 2026-07-27 GM 지시 "멤버십 회원관리는 멤버십 작업현황만, 강습은 강습만"):
    <div data-worklog="cpo" data-worklog-scope="멤버십" data-worklog-scope-set="멤버십,강습"></div>
    - scope-set = 이 페이지가 쓰는 화면 이름 전체. scope = 지금 보고 있는 화면.
    - '한 일' 목록을 area 값으로 거른다:
        area == scope            → 보인다
        area == '공통'            → 보인다(두 화면에 다 걸리는 일 — 한쪽에 억지 배정하면 반대편에서 사라진다)
        area ∈ scope-set 의 다른 화면 → 숨긴다(이게 GM이 요청한 분리)
        area ∉ scope-set (옛 '작업') → 목록 아래 접힘 "화면 구분 이전 기록 N건"으로 남긴다(삭제·은폐 아님)
    - 화면을 바꾸면 페이지가 data-worklog-scope 를 갈아끼우고 window.wlpRenderWorklog() 를 부른다.
    - scope 속성이 없으면 거르지 않는다 = 종전과 동일.

  데이터 소스(고정 스키마 — 백엔드와 합의된 계약, 변경 금지):
    - status/worklog.jsonl      1줄 1 JSON: {ts,role,area,event,result,detail,ref,url}
        result ∈ ok|warn|fail
    - status/worklog_gaps.json  {generated_at, gaps:[{role,severity,title,detail,hint,ref,age,first_seen}],
        summary:{신규,누적}, rules_run:[...]}
        severity ∈ high|mid|low · age ∈ 신규|누적(선택 필드 — 없으면 신규로 취급, 구버전 하위호환)
        first_seen: "YYYY-MM-DD"(선택)

  동작:
    1) [data-worklog] 컨테이너를 모두 찾아 role별로 독립 렌더(데이터는 1회 fetch 공유 — 같은
       페이지에 여러 개 붙어도 안전).
    2) 기본 접힘 1줄 토글 "▸ 작업 현황 로그". 해당 role의 신규(age:"신규") 빠진 것이 있으면 붉은
       배지 "⚠️ N"(N=신규만 — 누적은 배지에 안 잡힘. 평상시 조용해야 진짜 신규가 눈에 띈다).
    3) 펼치면 ⚠️ 빠진 것 2단 + 📋 한 일(최신순·최근 7일·최대 50줄·날짜 구분선).
       - 상단(신규): 심각도 high→mid→low. 0건이면 구획을 숨기지 않고 "빠진 것 없음 ✅"로 명시
         (조용함=정상 신호). 1건 이상이면 굵은 제목·옅은 경고 틴트 카드로 튀게, high만 마커.
       - 하단(누적): 있을 때만 기본 접힌 담백한 1줄 "▸ 과거 누적 M건"(건수는 접힌 채로도 항상 보임).
         펼치면 목록 — 신규보다 확실히 담백(마커 없음·작은 글씨).
       - age 필드 없는 구버전 데이터는 전부 신규로 취급 → 누적 구획 없이 기존 동작 그대로(하위호환).
    4) 데이터 fetch 실패 시 조용히 비우지 않고 "불러오지 못했습니다" 안내를 해당 구획에 표시.
    5) 자체완결(외부 라이브러리 0). 페이지 CSS 변수(--paper·--text·--border·--dim·--accent 등)가
       있으면 그대로 흡수, 없으면 라이트/다크 자동 중립색 폴백.
*/
(function(){
  'use strict';
  if(window.__wlpWorklogPanel) return;   // 중복 include 가드
  window.__wlpWorklogPanel = true;

  var WORKLOG_URL = 'https://raw.githubusercontent.com/wellperion-cao/wellperion-automation/master/status/worklog.jsonl';
  var GAPS_URL    = 'https://raw.githubusercontent.com/wellperion-cao/wellperion-automation/master/status/worklog_gaps.json';
  var SEV_ORDER   = { high: 0, mid: 1, low: 2 };
  var RESULT_ICON = { ok: '✅', warn: '⚠️', fail: '❌' };
  var DAY_MS = 24 * 60 * 60 * 1000;

  // ── 유틸 ──
  function esc(s){ return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function pad2(n){ return (n < 10 ? '0' : '') + n; }
  function tsParts(ts){
    var d = new Date(ts);
    if(isNaN(d.getTime())) return null;
    return {
      time: pad2(d.getHours()) + ':' + pad2(d.getMinutes()),
      dateKey: d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()),
      dateLabel: (d.getMonth() + 1) + '월 ' + d.getDate() + '일',
      time_ms: d.getTime()
    };
  }
  function fmtGenAt(iso){
    var d = new Date(iso);
    if(isNaN(d.getTime())) return '';
    return (d.getMonth() + 1) + '월 ' + d.getDate() + '일 ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());
  }

  // ── JSONL 파서 — 빈 줄·깨진 줄은 건너뛰고 계속 ──
  function parseJsonl(text){
    var out = [];
    var lines = String(text || '').split(/\r?\n/);
    for(var i = 0; i < lines.length; i++){
      var line = lines[i].trim();
      if(!line) continue;
      try{
        var obj = JSON.parse(line);
        if(obj && typeof obj === 'object') out.push(obj);
      }catch(e){ /* 깨진 줄 skip — 계속 진행 */ }
    }
    return out;
  }

  // ── 위젯 CSS(1회 주입) — 페이지 테마 변수 흡수 + 중립 폴백(라이트/다크 자동) ──
  function injectStyle(){
    if(document.getElementById('wl-style')) return;
    var css =
      '.wl-panel{--wl-fb-bg:#ffffff; --wl-fb-text:#18181b; --wl-fb-dim:#84848c; --wl-fb-border:#e2ded7;' +
        ' --wl-fb-surface:#f7f5f1; --wl-fb-accent:#b78a3d;' +
        ' margin:14px 0; width:100%; box-sizing:border-box; border:1px solid var(--border,var(--wl-fb-border));' +
        ' border-radius:12px; background:var(--paper,var(--wl-fb-bg)); overflow:hidden;' +
        ' font-family:inherit; color:var(--text,var(--wl-fb-text));}' +
      '@media (prefers-color-scheme: dark){.wl-panel{--wl-fb-bg:#201f1c; --wl-fb-text:#efece5;' +
        ' --wl-fb-dim:#a19b8f; --wl-fb-border:#3c3833; --wl-fb-surface:#2a2723; --wl-fb-accent:#d8b768;}}' +
      '.wl-toggle{display:flex; align-items:center; gap:8px; width:100%; box-sizing:border-box; text-align:left;' +
        ' background:none; border:none; cursor:pointer; padding:12px 14px; font:inherit; font-size:13.5px;' +
        ' font-weight:700; color:inherit;}' +
      '.wl-toggle:hover{background:var(--surface,var(--wl-fb-surface));}' +
      '.wl-toggle:focus-visible{outline:2px solid var(--accent,var(--wl-fb-accent)); outline-offset:-2px;}' +
      '.wl-caret{display:inline-block; width:10px; flex:0 0 auto; color:var(--dim,var(--wl-fb-dim)); font-size:11px;}' +
      '.wl-badge{margin-left:2px; display:inline-flex; align-items:center; font-size:11px; font-weight:800;' +
        ' color:#b3402c; background:rgba(179,64,44,.13); border:1px solid rgba(179,64,44,.35);' +
        ' border-radius:20px; padding:1px 9px; line-height:1.6;}' +
      '@media (prefers-color-scheme: dark){.wl-badge{color:#f0a692; background:rgba(224,138,114,.16);' +
        ' border-color:rgba(224,138,114,.4);}}' +
      '.wl-badge[hidden]{display:none;}' +
      '.wl-body{border-top:1px solid var(--border,var(--wl-fb-border)); padding:14px; font-size:12.5px;' +
        ' line-height:1.65; word-break:keep-all; overflow-wrap:break-word;}' +
      '.wl-body[hidden]{display:none;}' +
      '.wl-section + .wl-section{margin-top:18px; padding-top:16px; border-top:1px dashed var(--border,var(--wl-fb-border));}' +
      '.wl-section-title{margin:0 0 9px; font-size:11px; font-weight:700; letter-spacing:.03em;' +
        ' text-transform:uppercase; color:var(--dim,var(--wl-fb-dim));}' +
      // 빠진 것 1건 이상일 때만 튀는 카드 — 평상시(0건)는 위 기본 .wl-section-title(작고 흐림) 그대로 유지.
      // 형광색·꽉 찬 블록 없이 옅은 틴트 + 좌측 3px 보더만(과하지 않게).
      '.wl-gaps-alert{background:rgba(179,64,44,.055); border-left:3px solid #b3402c; border-radius:9px;' +
        ' padding:11px 12px 12px;}' +
      '@media (prefers-color-scheme: dark){.wl-gaps-alert{background:rgba(224,138,114,.09);}}' +
      '.wl-gaps-alert .wl-section-title{font-size:13.5px; font-weight:800; text-transform:none;' +
        ' letter-spacing:0; color:#b3402c;}' +
      '@media (prefers-color-scheme: dark){.wl-gaps-alert .wl-section-title{color:#e08a72;}}' +
      '.wl-empty-ok, .wl-empty, .wl-loading{color:var(--dim,var(--wl-fb-dim));}' +
      '.wl-error{color:#b3462f;}' +
      '.wl-gap{margin-bottom:9px; padding:1px 0 1px 11px; border-left:3px solid var(--wl-fb-border);}' +
      '.wl-gaps-alert .wl-gap{border-left-color:rgba(179,64,44,.25);}' +
      '.wl-gap:last-child{margin-bottom:0;}' +
      '.wl-gap-high{border-left-color:#b3402c;}' +
      '.wl-gaps-alert .wl-gap-high{border-left-color:#b3402c;}' +
      '.wl-gap-mid{border-left-color:#c9a24a;}' +
      '.wl-gap-low{border-left-color:var(--border,var(--wl-fb-border));}' +
      '.wl-gap-title{font-weight:700;}' +
      '.wl-gaps-alert .wl-gap-title{font-weight:800;}' +
      '.wl-gap-mark{color:#b3402c; margin-right:4px; font-size:10px; vertical-align:1px;}' +
      '@media (prefers-color-scheme: dark){.wl-gap-mark{color:#e08a72;}}' +
      '.wl-gap-detail{margin-top:2px; color:var(--dim,var(--wl-fb-dim));}' +
      '.wl-gap-hint{margin-top:4px; font-size:11.5px; color:var(--accent,var(--wl-fb-accent));}' +
      '.wl-gap-since{margin-top:3px; font-size:10px; color:var(--dim,var(--wl-fb-dim));}' +
      // 누적(밀린 것) — 신규보다 확실히 담백: 접힌 1줄(건수 상시 노출) + 펼침 목록은 작은 글씨·마커 없음.
      '.wl-old-gaps{margin-top:10px;}' +
      '.wl-old-toggle{display:flex; align-items:center; gap:6px; width:100%; box-sizing:border-box;' +
        ' text-align:left; background:none; border:none; cursor:pointer; padding:5px 2px; font:inherit;' +
        ' font-size:11.5px; font-weight:600; color:var(--dim,var(--wl-fb-dim));}' +
      '.wl-old-toggle:hover{color:var(--text,var(--wl-fb-text));}' +
      '.wl-old-caret{display:inline-block; width:10px; flex:0 0 auto; font-size:10px;}' +
      '.wl-old-list{margin-top:5px; padding-left:1px;}' +
      '.wl-old-list[hidden]{display:none;}' +
      '.wl-gap.wl-gap-old{border-left-color:var(--wl-fb-border); opacity:.85;}' +
      '.wl-gap-old .wl-gap-title{font-weight:600;}' +
      '.wl-gap-old .wl-gap-title, .wl-gap-old .wl-gap-detail, .wl-gap-old .wl-gap-hint{font-size:11.5px;}' +
      '.wl-date-sep{margin:11px 0 5px; font-size:10.5px; font-weight:700; letter-spacing:.02em;' +
        ' color:var(--dim,var(--wl-fb-dim));}' +
      '.wl-date-sep:first-child{margin-top:0;}' +
      '.wl-log-row{display:flex; flex-wrap:wrap; align-items:baseline; gap:0 6px; padding:3px 0 3px 9px;' +
        ' border-left:2px solid var(--wl-fb-border);}' +
      '.wl-log-row.wl-result-ok{border-left-color:#5b9a6f;}' +
      '.wl-log-row.wl-result-warn{border-left-color:#c9a24a;}' +
      '.wl-log-row.wl-result-fail{border-left-color:#b3402c;}' +
      '.wl-log-time{color:var(--dim,var(--wl-fb-dim)); font-variant-numeric:tabular-nums;}' +
      '.wl-log-area{font-weight:700; color:var(--accent,var(--wl-fb-accent));}' +
      '.wl-log-event a{color:inherit; text-decoration:underline; text-underline-offset:2px;}' +
      '.wl-log-detail{flex:0 0 100%; margin:1px 0 4px 17px; color:var(--dim,var(--wl-fb-dim)); font-size:11.5px;}' +
      '.wl-footer{margin-top:12px; padding-top:10px; border-top:1px dashed var(--border,var(--wl-fb-border));' +
        ' font-size:10.5px; color:var(--dim,var(--wl-fb-dim));}' +
      // 모달 모드 — 이미 팝업이 테두리·배경·여백을 갖고 있으니 패널이 또 두르지 않는다(액자 겹침 방지).
      '.wl-panel-modal{margin:0; border:none; border-radius:0; background:none;}' +
      '.wl-panel-modal > .wl-body{border-top:none; padding:0;}' +
      // 지금 어느 화면 기준으로 걸러 보고 있는지 — 제목 옆 작은 꼬리표(비어 보일 때 "왜 없지?"를 막는다).
      '.wl-scope-tag{margin-left:6px; padding:1px 7px; border-radius:20px; font-size:10px; font-weight:700;' +
        ' text-transform:none; letter-spacing:0; color:var(--accent,var(--wl-fb-accent));' +
        ' border:1px solid var(--border,var(--wl-fb-border));}';
    var st = document.createElement('style');
    st.id = 'wl-style';
    st.textContent = css;
    document.head.appendChild(st);
  }

  // ── 데이터 로드(공유, 1회 — 실패해도 다른 소스는 살려서 부분 렌더 가능하게 각각 catch) ──
  var dataPromise = null;
  var WL_NOT_STARTED = '__wl_not_started__'; // worklog.jsonl 이 아직 없음(404)/비어있음 — "고장"이 아니라 "아직 안 쌓임"
  function fetchOk(url){
    return fetch(url + '?t=' + Date.now(), { cache: 'no-store' }).then(function(r){
      if(!r.ok) throw new Error('http ' + r.status);
      return r;
    });
  }
  // worklog.jsonl 전용 로더 — 404/빈 응답(아직 자동화가 한 번도 안 돌아 파일이 없는 정상 초기 상태)과
  // 그 외 실제 실패(네트워크 오류·5xx 등)를 구분해서 각기 다른 안내를 낼 수 있게 한다.
  function fetchWorklog(){
    return fetch(WORKLOG_URL + '?t=' + Date.now(), { cache: 'no-store' }).then(function(r){
      if(r.status === 404) return WL_NOT_STARTED;
      if(!r.ok) throw new Error('http ' + r.status);
      return r.text().then(function(t){
        return String(t || '').trim() ? parseJsonl(t) : WL_NOT_STARTED;
      });
    }).catch(function(){ return null; }); // 진짜 실패만 null(불러오지 못함)
  }
  function loadData(){
    if(dataPromise) return dataPromise;
    dataPromise = Promise.all([
      fetchWorklog(),
      fetchOk(GAPS_URL).then(function(r){ return r.json(); }).catch(function(){ return null; })
    ]).then(function(res){ return { logs: res[0], gaps: res[1] }; });
    return dataPromise;
  }

  // ── 렌더 ──
  function bySeverity(a, b){
    var sa = SEV_ORDER.hasOwnProperty(a.severity) ? SEV_ORDER[a.severity] : 9;
    var sb = SEV_ORDER.hasOwnProperty(b.severity) ? SEV_ORDER[b.severity] : 9;
    return sa - sb;
  }
  // age 없는 구버전 데이터는 전부 신규 취급(하위호환 — 지금 동작 그대로 유지).
  function isNewAge(g){ return g.age !== '누적'; }
  function fmtSince(s){
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s || ''));
    if(!m) return '';
    return parseInt(m[2], 10) + '/' + parseInt(m[3], 10);
  }
  function gapItemHtml(g, isNew){
    var sevKey = SEV_ORDER.hasOwnProperty(g.severity) ? g.severity : 'low';
    var mark = (isNew && sevKey === 'high') ? '<span class="wl-gap-mark">●</span>' : '';
    var since = fmtSince(g.first_seen);
    return '<div class="wl-gap wl-gap-' + sevKey + (isNew ? '' : ' wl-gap-old') + '">' +
      '<div class="wl-gap-title">' + mark + esc(g.title || '(제목 없음)') + '</div>' +
      (g.detail ? '<div class="wl-gap-detail">' + esc(g.detail) + '</div>' : '') +
      (g.hint ? '<div class="wl-gap-hint">💡 ' + esc(g.hint) + '</div>' : '') +
      (since ? '<div class="wl-gap-since">(' + esc(since) + '부터)</div>' : '') +
      '</div>';
  }
  function renderGapsSection(gapsObj, role){
    if(gapsObj === null){
      return '<div class="wl-section"><div class="wl-section-title">⚠️ 빠진 것</div>' +
        '<div class="wl-error">빠진 것 정보를 불러오지 못했습니다</div></div>';
    }
    var roleGaps = (gapsObj.gaps || []).filter(function(g){ return (g && g.role) === role; });
    var newGaps = roleGaps.filter(isNewAge).sort(bySeverity);
    var oldGaps = roleGaps.filter(function(g){ return !isNewAge(g); }).sort(bySeverity);

    // ★아무것도 없으면 구획 자체를 내지 않는다(GM 2026-07-27 · FB260727-153107
    //   "0건인데도 계속 상시로 떠있는건 이상한 것 같은데?"). 07-23 에는 '조용함=정상 신호'로 한 줄 남겼는데,
    //   매번 떠 있으니 오히려 눈에 걸린다는 지적이다. 나중 지시가 이긴다 — 신규·누적 모두 0이면 통째로 뺀다.
    //   ※'한 일'은 그대로 남는다. 빠진 것이 생기면 그때 다시 나타난다.
    if(!newGaps.length && !oldGaps.length) return '';

    var html = '<div class="wl-section">';
    // 상단(신규) — 0건이면 평상시 신호로 조용히 한 줄만. 1건 이상만 카드로 튀게(GM 07-23 지시).
    if(!newGaps.length){
      html += '<div class="wl-section-title">⚠️ 빠진 것</div><div class="wl-empty-ok">빠진 것 없음 ✅</div>';
    } else {
      html += '<div class="wl-gaps-alert"><div class="wl-section-title">⚠️ 빠진 것 ' + newGaps.length + '건</div>';
      newGaps.forEach(function(g){ html += gapItemHtml(g, true); });
      html += '</div>';
    }
    // 하단(누적) — 있을 때만, 기본 접힘·건수는 접힌 채로도 상시 노출. 신규 0·누적 있음도 자연스럽게 공존.
    if(oldGaps.length){
      html += '<div class="wl-old-gaps">' +
        '<button type="button" class="wl-old-toggle" aria-expanded="false">' +
          '<span class="wl-old-caret">▸</span><span>과거 누적 ' + oldGaps.length + '건</span>' +
        '</button>' +
        '<div class="wl-old-list" hidden>' +
        oldGaps.map(function(g){ return gapItemHtml(g, false); }).join('') +
        '</div></div>';
    }
    return html + '</div>';
  }

  // 화면 스코프 판정 — 이 줄을 지금 화면에서 보여줄지. 2026-07-27.
  //   returns 'show' | 'hide' | 'legacy'(화면 구분이 생기기 전 기록 — 접어서 남긴다)
  function scopeVerdict(area, scope, scopeSet){
    if(!scope) return 'show';                       // 스코프 미지정 = 거르지 않음(종전 동작)
    var a = String(area == null ? '' : area).trim();
    if(a === scope) return 'show';
    if(a === '공통') return 'show';                  // 두 화면에 다 걸리는 일
    if(scopeSet.indexOf(a) >= 0) return 'hide';      // 다른 화면 일 = 이번 요청의 핵심(분리)
    return 'legacy';                                 // 옛 '작업' 등 — 구분 이전 기록
  }

  function renderLogsSection(logsAll, role, scope, scopeSet){
    var html = '<div class="wl-section"><div class="wl-section-title">📋 한 일'
      + (scope ? ' <span class="wl-scope-tag">' + esc(scope) + ' 화면</span>' : '') + '</div>';
    if(logsAll === null){
      return html + '<div class="wl-error">작업 로그를 불러오지 못했습니다</div></div>';
    }
    // worklog.jsonl 자체가 아직 없거나(404) 비어있음 — 고장이 아니라 "자동화가 아직 한 번도 안 돎"의
    // 정상 초기 상태이므로 경고 톤이 아닌 담백한 안내로 구분.
    if(logsAll === WL_NOT_STARTED){
      return html + '<div class="wl-empty">아직 기록된 작업이 없습니다. 다음 작업부터 자동으로 쌓입니다.</div></div>';
    }
    var roleLogs = logsAll.filter(function(l){ return l && (l.role === role) && l.ts; });
    if(!roleLogs.length){
      return html + '<div class="wl-empty">아직 기록된 작업이 없습니다</div></div>';
    }
    roleLogs.sort(function(a, b){ return String(b.ts).localeCompare(String(a.ts)); });
    var cutoff = Date.now() - 7 * DAY_MS;
    var recent = roleLogs.filter(function(l){
      var t = new Date(l.ts).getTime();
      return !isNaN(t) && t >= cutoff;
    }).slice(0, 50);
    if(!recent.length){
      return html + '<div class="wl-empty">최근 7일 내 기록이 없습니다</div></div>';
    }
    // 화면 스코프로 세 갈래 — 보임 / 다른 화면(숨김) / 구분 이전(접어서 남김). 2026-07-27.
    var shown = [], legacy = [];
    recent.forEach(function(l){
      var v = scopeVerdict(l.area, scope, scopeSet);
      if(v === 'show') shown.push(l);
      else if(v === 'legacy') legacy.push(l);
    });

    function rowsHtml(list){
      var out = '', lastKey = '';
      list.forEach(function(l){
        var tp = tsParts(l.ts);
        if(!tp) return;
        if(tp.dateKey !== lastKey){
          out += '<div class="wl-date-sep">' + tp.dateLabel + '</div>';
          lastKey = tp.dateKey;
        }
        var icon = RESULT_ICON[l.result] || '';
        var eventTxt = esc(l.event || '');
        var eventHtml = l.url ? ('<a href="' + esc(l.url) + '" target="_blank" rel="noopener">' + eventTxt + '</a>') : eventTxt;
        out += '<div class="wl-log-row wl-result-' + esc(l.result || '') + '"' + (l.ref ? ' title="' + esc(l.ref) + '"' : '') + '>' +
          '<span class="wl-log-time">' + tp.time + '</span>' +
          '<span class="wl-log-sep">·</span>' +
          (l.area ? '<span class="wl-log-area">[' + esc(l.area) + ']</span>' : '') +
          '<span class="wl-log-event">' + eventHtml + '</span>' +
          (icon ? '<span class="wl-log-icon">' + icon + '</span>' : '') +
          '</div>';
        if(l.detail) out += '<div class="wl-log-detail">' + esc(l.detail) + '</div>';
      });
      return out;
    }

    if(!shown.length){
      html += '<div class="wl-empty">이 화면에서 한 일은 최근 7일 내 없습니다</div>';
    } else {
      html += rowsHtml(shown);
    }
    // 구분 이전 기록 — 지우지 않고 접어 둔다. 건수는 접힌 채로도 보인다(누적 gaps와 같은 방식).
    if(legacy.length){
      html += '<div class="wl-old-gaps">' +
        '<button type="button" class="wl-old-toggle" aria-expanded="false">' +
          '<span class="wl-old-caret">▸</span><span>화면 구분 이전 기록 ' + legacy.length + '건</span>' +
        '</button>' +
        '<div class="wl-old-list" hidden>' + rowsHtml(legacy) + '</div></div>';
    }
    return html + '</div>';
  }

  function renderBody(body, data, role, scope, scopeSet){
    var html = renderGapsSection(data.gaps, role) + renderLogsSection(data.logs, role, scope, scopeSet);
    var genAt = (data.gaps && data.gaps.generated_at) ? fmtGenAt(data.gaps.generated_at) : '';
    if(genAt) html += '<div class="wl-footer">마지막 점검: ' + esc(genAt) + '</div>';
    body.innerHTML = html;
  }

  function updateBadge(badge, data, role){
    if(!badge) return;
    if(data.gaps === null){ badge.hidden = true; return; }
    // 배지 = 신규만 카운트(누적이 아무리 많아도 배지엔 안 잡힘 — 평상시 조용해야 진짜 신규가 눈에 띈다).
    var n = (data.gaps.gaps || [])
      .filter(function(g){ return (g && g.role) === role; })
      .filter(isNewAge).length;
    if(n > 0){ badge.hidden = false; badge.textContent = '⚠️ ' + n; }
    else { badge.hidden = true; }
  }

  // ── 인스턴스 1개 구성 ──
  function buildPanel(container, role){
    role = String(role || '').trim().toLowerCase();
    injectStyle();

    // 모달 모드 = 접힘 토글 없이 내용만. 여는 버튼·팝업 껍데기는 페이지가 갖는다(2026-07-27 GM).
    var isModal = String(container.getAttribute('data-worklog-mode') || '').toLowerCase() === 'modal';
    var wrap = document.createElement('div');
    wrap.className = 'wl-panel' + (isModal ? ' wl-panel-modal' : '');
    wrap.innerHTML = isModal
      ? '<div class="wl-body"><div class="wl-loading">불러오는 중…</div></div>'
      : ('<button type="button" class="wl-toggle" aria-expanded="false">' +
           '<span class="wl-caret">▸</span><span>작업 현황 로그</span><span class="wl-badge" hidden></span>' +
         '</button>' +
         '<div class="wl-body" hidden><div class="wl-loading">불러오는 중…</div></div>');
    container.appendChild(wrap);

    var body = wrap.querySelector('.wl-body');
    // 배지 = 기본 모드는 토글 줄 안, 모달 모드는 페이지가 지정한 상단 버튼 옆 요소.
    var badgeSel = container.getAttribute('data-worklog-badge');
    var badge = isModal
      ? (badgeSel ? document.querySelector(badgeSel) : null)
      : wrap.querySelector('.wl-badge');

    if(!isModal){
      var toggle = wrap.querySelector('.wl-toggle');
      var caret = wrap.querySelector('.wl-caret');
      var opened = false;
      toggle.addEventListener('click', function(){
        opened = !opened;
        body.hidden = !opened;
        toggle.setAttribute('aria-expanded', String(opened));
        caret.textContent = opened ? '▾' : '▸';
      });
    }

    // 누적(밀린 것) 토글 — body.innerHTML이 데이터 로드 시 통째로 교체되므로 wrap(고정 요소)에
    // 위임 바인딩(1회)해 매 렌더마다 다시 붙일 필요 없게 한다.
    wrap.addEventListener('click', function(e){
      var t = e.target && e.target.closest ? e.target.closest('.wl-old-toggle') : null;
      if(!t) return;
      var list = t.parentNode.querySelector('.wl-old-list');
      var oc = t.querySelector('.wl-old-caret');
      var willOpen = list.hidden;
      list.hidden = !willOpen;
      t.setAttribute('aria-expanded', String(willOpen));
      if(oc) oc.textContent = willOpen ? '▾' : '▸';
    });

    // 스코프는 '그릴 때마다' 컨테이너에서 다시 읽는다 — 페이지가 화면을 바꾸며 속성만 갈아끼우면 되게.
    function paint(data){
      var scope = String(container.getAttribute('data-worklog-scope') || '').trim();
      var setRaw = String(container.getAttribute('data-worklog-scope-set') || '');
      var scopeSet = setRaw.split(',').map(function(s){ return s.trim(); }).filter(Boolean);
      renderBody(body, data, role, scope, scopeSet);
      updateBadge(badge, data, role);
    }
    _instances.push(function(){ loadData().then(paint); });   // 페이지가 다시 그리라고 할 때 쓰는 손잡이
    loadData().then(paint);
  }

  // 렌더된 인스턴스들 — window.wlpRenderWorklog() 가 전부 다시 그린다(데이터는 캐시 재사용, 재fetch 없음).
  var _instances = [];

  // ── 전체 스캔(같은 페이지 복수 인스턴스 안전 — 이미 초기화된 컨테이너는 건너뜀) ──
  function scan(){
    var els = document.querySelectorAll('[data-worklog]');
    for(var i = 0; i < els.length; i++){
      var el = els[i];
      if(el.getAttribute('data-wl-init') === '1') continue;
      el.setAttribute('data-wl-init', '1');
      buildPanel(el, el.getAttribute('data-worklog'));
    }
  }

  // 재스캔 훅 공개 — 컨테이너를 나중에 동적으로 추가하는 페이지가 직접 호출 가능(기존 페이지엔 무영향).
  window.wlpRescanWorklog = scan;
  // 다시 그리기 훅 — 페이지가 data-worklog-scope 를 바꾼 뒤 부른다(데이터 재요청 없음, 캐시 재사용).
  window.wlpRenderWorklog = function(){
    scan();                                    // 아직 안 만들어진 컨테이너가 있으면 먼저 만든다
    _instances.forEach(function(f){ try{ f(); }catch(e){} });
  };

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', scan);
  } else {
    scan();
  }
})();
