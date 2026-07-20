/* ══════════════════════════════════════════════════════════════════════════
   부서 체계 페이지 ↔ 채용 현황 연동 컴포넌트 (시우 · 2026-07-20, 배9182 후속)

   목적 : 각 부서 체계 페이지 "채용 현황" 탭에서 "우리 부서 지금 누구 뽑고 있나"를
          공고 목록으로 보여주고, 클릭하면 그 자리에서(다른 페이지로 나가지 않고)
          원본 공고 페이지를 그대로 펼쳐 보여준다.
   출처 : 채용 SSOT = CHRO 채용 시트(db:hire) — 나우열 매니저 관리.
          GAS action="public-job-status" 로 라이브 조회. 이 파일은 값을 갖지 않는다(렌더만).
   원칙 : 조회 실패 시 카드를 아예 그리지 않는다(틀린 정보 노출 금지 · 폴백=침묵).

   부서 매칭 (2026-07-20 개정) — GM 지시: 시트에 부서 칸을 요청하지 않고 우리 쪽에서
   명시적 대응표(JOB_PAGES)로 관리한다. 공고 제목 키워드 추측 방식(구 DEPT_RULES) 폐기.
   각 공고 페이지가 이미 자기 자신을 식별하는 data-jobbucket/data-jobkey 속성을
   그대로 재사용해 매칭한다 — 그 페이지가 스스로를 알아보는 방식과 동일하므로
   탭에 뜨는 공고 = 실제 그 페이지가 맞다(이중 판정 불일치 없음).
   새 공고가 이 표에 없으면 '미분류'로 콘솔에 남긴다(조용히 사라지지 않음).

   사용법 : <div id="hiring-host"></div>
            <script src="hiring-status.js"></script>
            <script>renderHiringStatus('hiring-host','주차관리부');</script>
   ══════════════════════════════════════════════════════════════════════════ */
(function () {
  var NOTION_FN = "https://script.google.com/macros/s/AKfycbyyXrdM7nSXKPG3Dy8wI6_3AI1spZs24d-uHTzQZlsqzoRXKkFbSFnX-hr42D3ScQSSHQ/exec";
  var RECRUIT_BASE = "../../chro/recruiting/";

  /* 공고 페이지 ↔ 부서 명시적 대응표 — 이 프로젝트의 유일한 소스.
     bucket: 페이지의 data-jobbucket과 정확히 일치해야 매칭(우선).
     jobkey: 페이지의 data-jobkey와 부분 일치(양방향 substring, 4자 이상)로 매칭 — bucket 없을 때만.
     새 공고 페이지를 추가할 때는 여기 한 줄만 추가하면 된다. */
  var JOB_PAGES = [
    { file: 'parking.html',    dept: '주차관리부', bucket: null,     jobkey: '주차관리자 · 발렛파킹 (시설부)' },
    { file: 'sauna.html',      dept: '지원부',     bucket: null,     jobkey: '남자사우나 주임' },
    { file: 'golfpro.html',    dept: '파트너팀',   bucket: null,     jobkey: '오전 골프 프로' },
    { file: 'operations.html', dept: '운영부',     bucket: '리셉션', jobkey: null }
    // chauffeur.html(수행기사)은 index.html 채용 목록에 아직 게시되지 않은 페이지 —
    // 현재 어느 부서 체계에도 연결하지 않는다(의도적 제외 · 누락 아님).
  ];

  function normKey(s) {
    return String(s || '').replace(/\s|[()（）]/g, '').toLowerCase();
  }
  function hay(job) {
    return String(job.position || '') + ' ' + String(job.bucket || '');
  }
  /* 각 공고 페이지가 자기 자신을 알아보는 것과 동일한 알고리즘(원본 recruiting/*.html
     내 로직 그대로) — bucket 정확 일치 우선, 없으면 jobkey 부분 일치. */
  function matchPage(job) {
    for (var i = 0; i < JOB_PAGES.length; i++) {
      var p = JOB_PAGES[i];
      if (p.bucket) {
        if (job.bucket && job.bucket === p.bucket) return p;
        continue;
      }
      if (p.jobkey) {
        var pk = normKey(p.jobkey), jk = normKey(job.position);
        if (jk.length >= 4 && pk.length >= 4 && (jk.indexOf(pk) >= 0 || pk.indexOf(jk) >= 0)) return p;
      }
    }
    return null;
  }
  function deptOf(job) {
    var p = matchPage(job);
    return p ? p.dept : '';
  }
  function pageOf(job) {
    var p = matchPage(job);
    return RECRUIT_BASE + (p ? p.file : 'index.html');
  }
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
  var _uid = 0;

  function paint(host, dept, jobs) {
    /* 대응표에 없는 공고 = 미분류 — 조용히 사라지지 않도록 콘솔에 남긴다. */
    jobs.filter(function (j) { return j.closed !== true; }).forEach(function (j) {
      if (!matchPage(j)) console.warn('[hiring-status] 미분류 공고 — JOB_PAGES에 대응 없음:', j.position || j.bucket || j);
    });

    var open = jobs.filter(function (j) {
      return j.closed !== true && deptOf(j) === dept;
    });

    var rows = open.map(function (j) {
      var uid = 'hjob-' + (++_uid);
      var url = pageOf(j);
      return '<tr>' +
          '<td style="padding:9px 10px;border:1px solid var(--border);font-weight:650;">' + esc(j.position) + '</td>' +
          '<td style="padding:9px 10px;border:1px solid var(--border);white-space:nowrap;color:#2f7d4f;font-weight:700;">● 공고중</td>' +
          '<td style="padding:9px 10px;border:1px solid var(--border);white-space:nowrap;">' +
            '<button type="button" onclick="toggleHiringJob(\'' + uid + '\',\'' + esc(url).replace(/'/g, "\\'") + '\')" ' +
              'style="border:1px solid var(--accent);background:none;color:var(--accent);border-radius:8px;padding:6px 12px;font-size:12.5px;font-weight:700;cursor:pointer;font-family:inherit;">공고 보기 ▾</button>' +
          '</td></tr>' +
        '<tr id="' + uid + '-row" class="hidden"><td colspan="3" style="padding:0;border:1px solid var(--border);">' +
          '<iframe id="' + uid + '-frame" data-src="' + esc(url) + '" title="' + esc(j.position) + ' 공고" ' +
            'style="width:100%;height:min(78vh,900px);border:none;display:block;background:var(--bg);"></iframe>' +
        '</td></tr>';
    }).join('');

    var body = open.length
      ? '<div style="overflow-x:auto;"><table style="width:100%;min-width:420px;border-collapse:collapse;font-size:13px;margin-bottom:8px;">' +
          '<tr style="background:var(--paper);">' +
            '<th style="padding:9px 10px;border:1px solid var(--border);text-align:left;">모집 중인 자리</th>' +
            '<th style="padding:9px 10px;border:1px solid var(--border);width:84px;">상태</th>' +
            '<th style="padding:9px 10px;border:1px solid var(--border);width:108px;">공고</th>' +
          '</tr>' + rows +
        '</table></div>'
      : '<p style="font-size:13px;color:var(--dim);margin:0 0 8px;">현재 ' + esc(dept) + '에서 모집 중인 자리가 없습니다.</p>';

    host.innerHTML =
      '<div style="border:1px solid var(--border);border-radius:12px;padding:14px 16px;background:var(--paper);margin:14px 0;">' +
        '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px;">' +
          '<span style="font-size:14px;font-weight:700;color:var(--accent);">🧑‍💼 ' + esc(dept) + ' 채용 현황</span>' +
          (open.length ? '<span style="font-size:11.5px;font-weight:700;color:#2f7d4f;background:#e6f4ea;border:1px solid #cfe9d7;border-radius:999px;padding:3px 10px;">모집 중 ' + open.length + '건</span>' : '') +
          '<a href="' + RECRUIT_BASE + 'index.html" target="_blank" rel="noopener" style="margin-left:auto;font-size:12.5px;color:var(--accent);text-decoration:none;font-weight:650;white-space:nowrap;">전체 채용 목록 ↗</a>' +
        '</div>' + body +
        '<p style="font-size:11.5px;color:var(--dim);margin:0;line-height:1.6;">채용 시트(인사 담당 관리)에서 자동으로 가져옵니다 — 이 표는 직접 고치지 않습니다. "공고 보기"를 누르면 원본 공고 페이지가 바로 아래에 펼쳐집니다(사본 아님 · 원본 실시간 반영). 내용 변경은 인사 담당에게 요청해 주세요.</p>' +
      '</div>';
  }

  /* 공고 보기 토글 — 클릭 시 그 자리(바로 아래 행)에 원본 공고 페이지를 펼친다.
     iframe src는 최초 펼칠 때만 채운다(불필요한 로드 방지). 다른 페이지로 이동하지 않는다. */
  window.toggleHiringJob = function (uid, url) {
    var row = document.getElementById(uid + '-row');
    var frame = document.getElementById(uid + '-frame');
    var btn = (row && row.previousElementSibling) ? row.previousElementSibling.querySelector('button') : null;
    if (!row) return;
    var willOpen = row.classList.contains('hidden');
    if (willOpen) {
      if (frame && !frame.getAttribute('src')) frame.setAttribute('src', frame.getAttribute('data-src'));
      row.classList.remove('hidden');
      if (btn) btn.textContent = '공고 접기 ▴';
    } else {
      row.classList.add('hidden');
      if (btn) btn.textContent = '공고 보기 ▾';
    }
  };

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
