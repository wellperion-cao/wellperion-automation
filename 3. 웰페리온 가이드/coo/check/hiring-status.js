/* ══════════════════════════════════════════════════════════════════════════
   부서 체계 페이지 ↔ 채용 현황 연동 컴포넌트 (시우 · 2026-07-20)

   목적 : 각 부서 체계 페이지에서 "우리 부서 지금 누구 뽑고 있나"를 자동 표시.
   출처 : 채용 SSOT = CHRO 채용 시트(db:hire) — 나우열 매니저 관리.
          GAS action="public-job-status" 로 라이브 조회. 이 파일은 값을 갖지 않는다(렌더만).
   원칙 : 조회 실패 시 카드를 아예 그리지 않는다(틀린 정보 노출 금지 · 폴백=침묵).

   ⚠️ 부서 매칭이 임시다 — 채용 시트에 '부서' 칸이 없어 공고 제목/버킷 키워드로 추정한다.
      시트에 부서 칸이 생기면 DEPT_RULES 를 지우고 j.dept 로 직접 매칭할 것.
      (나우열 매니저 요청 진행 중 · status/briefs/ 프롬프트 참조)

   사용법 : <div id="hiring-host"></div>
            <script src="hiring-status.js"></script>
            <script>renderHiringStatus('hiring-host','주차관리부');</script>
   ══════════════════════════════════════════════════════════════════════════ */
(function () {
  var NOTION_FN = "https://script.google.com/macros/s/AKfycbyyXrdM7nSXKPG3Dy8wI6_3AI1spZs24d-uHTzQZlsqzoRXKkFbSFnX-hr42D3ScQSSHQ/exec";
  var RECRUIT_BASE = "../../chro/recruiting/";

  /* 부서 판정 규칙 — 위에서부터 먼저 맞는 것이 이긴다.
     '주차관리자 · 발렛파킹 (시설부)' 처럼 옛 소속이 제목에 남은 공고가 있어
     주차/발렛을 시설부보다 먼저 본다(주차관리부 = 독립 부서). */
  var DEPT_RULES = [
    { dept: '주차관리부', kw: ['주차', '발렛'] },
    { dept: '지원부',     kw: ['사우나', '탕청소', '지원부'] },
    { dept: '파트너팀',   kw: ['골프', '프로', '파트너'] },
    { dept: '운영부',     kw: ['운영부', '리셉션', '프론트'] },
    { dept: '시설부',     kw: ['시설', '설비', '기계'] }
  ];

  /* 공고 상세 페이지 매칭 — 키워드 → 파일명 */
  var PAGE_RULES = [
    { kw: ['주차', '발렛'], file: 'parking.html'    },
    { kw: ['사우나'],       file: 'sauna.html'      },
    { kw: ['골프'],         file: 'golfpro.html'    },
    { kw: ['수행기사'],     file: 'chauffeur.html'  },
    { kw: ['운영부', '리셉션'], file: 'operations.html' }
  ];

  function hay(job) {
    return String(job.position || '') + ' ' + String(job.bucket || '');
  }
  function matchBy(rules, job) {
    var h = hay(job);
    for (var i = 0; i < rules.length; i++) {
      for (var k = 0; k < rules[i].kw.length; k++) {
        if (h.indexOf(rules[i].kw[k]) >= 0) return rules[i];
      }
    }
    return null;
  }
  function deptOf(job) {
    if (job.dept) return String(job.dept).trim();   // 시트에 부서 칸이 생기면 이 줄이 이긴다
    var r = matchBy(DEPT_RULES, job);
    return r ? r.dept : '';
  }
  function pageOf(job) {
    var r = matchBy(PAGE_RULES, job);
    return RECRUIT_BASE + (r ? r.file : 'index.html');
  }
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function paint(host, dept, jobs) {
    var open = jobs.filter(function (j) {
      return j.closed !== true && deptOf(j) === dept;
    });

    var rows = open.map(function (j) {
      return '<tr>' +
        '<td style="padding:9px 10px;border:1px solid var(--border);font-weight:650;">' + esc(j.position) + '</td>' +
        '<td style="padding:9px 10px;border:1px solid var(--border);white-space:nowrap;color:#2f7d4f;font-weight:700;">● 공고중</td>' +
        '<td style="padding:9px 10px;border:1px solid var(--border);white-space:nowrap;">' +
          '<a href="' + esc(pageOf(j)) + '" target="_blank" rel="noopener" style="color:var(--accent);text-decoration:none;font-weight:650;">공고 보기 ↗</a>' +
        '</td></tr>';
    }).join('');

    var body = open.length
      ? '<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:8px;">' +
          '<tr style="background:var(--paper);">' +
            '<th style="padding:9px 10px;border:1px solid var(--border);text-align:left;">모집 중인 자리</th>' +
            '<th style="padding:9px 10px;border:1px solid var(--border);width:84px;">상태</th>' +
            '<th style="padding:9px 10px;border:1px solid var(--border);width:96px;">공고</th>' +
          '</tr>' + rows +
        '</table>'
      : '<p style="font-size:13px;color:var(--dim);margin:0 0 8px;">현재 ' + esc(dept) + '에서 모집 중인 자리가 없습니다.</p>';

    host.innerHTML =
      '<div style="border:1px solid var(--border);border-radius:12px;padding:14px 16px;background:var(--paper);margin:14px 0;">' +
        '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px;">' +
          '<span style="font-size:14px;font-weight:700;color:var(--accent);">🧑‍💼 ' + esc(dept) + ' 채용 현황</span>' +
          (open.length ? '<span style="font-size:11.5px;font-weight:700;color:#2f7d4f;background:#e6f4ea;border:1px solid #cfe9d7;border-radius:999px;padding:3px 10px;">모집 중 ' + open.length + '건</span>' : '') +
          '<a href="' + RECRUIT_BASE + 'index.html" target="_blank" rel="noopener" style="margin-left:auto;font-size:12.5px;color:var(--accent);text-decoration:none;font-weight:650;white-space:nowrap;">전체 채용 목록 ↗</a>' +
        '</div>' + body +
        '<p style="font-size:11.5px;color:var(--dim);margin:0;line-height:1.6;">채용 시트(인사 담당 관리)에서 자동으로 가져옵니다 — 이 표는 직접 고치지 않습니다. 내용 변경은 인사 담당에게 요청해 주세요.</p>' +
      '</div>';
  }

  window.renderHiringStatus = function (hostId, dept) {
    var host = document.getElementById(hostId);
    if (!host) return;
    fetch(NOTION_FN, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain;charset=utf-8' },
      body: JSON.stringify({ action: 'public-job-status' })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.ok || !Array.isArray(d.jobs)) return;   // 폴백=침묵
        paint(host, dept, d.jobs);
      })
      .catch(function () { /* 조회 실패 시 카드 미표시 — 틀린 정보보다 빈 화면 */ });
  };
})();
