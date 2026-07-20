/* ══════════════════════════════════════════════════════════════════════════
   부서 체계 페이지 ↔ 채용 현황 연동 컴포넌트 (시우 · 2026-07-20, 배9182 3차 개정)

   목적 : 각 부서 체계 페이지 "채용 현황" 탭을 열면, 클릭 없이 그 자리에 채용
          공고 본문(지원자격·업무내용·근무조건·우대사항 등)이 원본 그대로 보인다.
          링크·버튼으로 다른 곳에 내보내지 않는다(클릭을 요구하던 이전 방식 폐기 — GM 3회 지적).
   출처 : 채용 SSOT = CHRO 채용 시트(db:hire) — 나우열 매니저 관리.
          GAS action="public-job-status" 로 라이브 조회해 "지금 열려 있는 자리"를 정하고,
          공고 본문 자체는 원본 recruiting/*.html 을 fetch로 그대로 가져와 얹는다
          (복사 없음 — 원본이 바뀌면 다음 로드 때 같이 바뀐다).
   방식 : 원본 페이지의 <style> + 본문(#captureRoot)을 Shadow DOM에 그대로 주입한다.
          Shadow DOM을 쓰는 이유 — iframe처럼 "페이지 안에 페이지"로 보이지 않으면서도,
          원본 CSS(.card·.bento 등 범용 클래스명)가 이 부서 체계 페이지의 스타일과
          충돌하지 않도록 격리한다.
   원칙 : 조회 실패 시 카드를 아예 그리지 않는다(틀린 정보 노출 금지 · 폴백=침묵).

   부서 매칭 — GM 지시로 시트에 부서 칸을 요청하지 않고 우리 쪽 명시 대응표(JOB_PAGES)로
   관리한다. 각 공고 페이지가 이미 자기 자신을 식별하는 data-jobbucket/data-jobkey
   속성을 그대로 재사용해 매칭(그 페이지가 스스로를 알아보는 방식과 동일).
   새 공고가 이 표에 없으면 콘솔에 '미분류'로 남긴다(조용히 사라지지 않음).

   ⚠️ 부서 개수 정정(2026-07-20) — 실제 부서는 4개(주차관리부·운영부·시설부·지원부)뿐이다.
      파트너팀은 별도 체계 페이지(파트너팀 체계.html)로, 이 4개 부서에 포함되지 않는다.
      4개 부서 체계 페이지 모두 이 컴포넌트를 재사용 중(2026-07-20 확산 완료).
      4개 부서 어디에도 안 붙는 공고(골프 프로·수행기사)는 JOB_PAGES에 dept:null로
      명시 등록해둔다 — 억지로 부서에 끼워 넣지 않고, 대응표에서 눈에 보이게 남긴다.

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
    { file: 'operations.html', dept: '운영부',     bucket: '리셉션', jobkey: null },
    // 시설부 — 2026-07-20 현재 시설부로 분류되는 공고 없음(모집 없음으로 표시됨). 아래는
    // 4개 부서(주차관리부·운영부·시설부·지원부)에 속하지 않는 공고 — 억지로 넣지 않고
    // 명시적으로 '부서 미해당'으로 남긴다(dept:null → 어느 부서 탭에도 뜨지 않음, GM 별도 판단 대기).
    { file: 'golfpro.html',    dept: null, note: '파트너팀 성격(오전 골프 프로) — 4개 부서 아님, 파트너팀 체계 재사용 시 여기 dept 채울 것', bucket: null, jobkey: '오전 골프 프로' },
    { file: 'chauffeur.html',  dept: null, note: '수행기사 — 4개 부서·파트너팀 어디에도 속하지 않음. index.html 채용 목록에도 아직 미게시.', bucket: '수행기사', jobkey: null }
  ];

  function normKey(s) {
    return String(s || '').replace(/\s|[()（）]/g, '').toLowerCase();
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
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /* 원본 공고 페이지를 그대로 가져와 그 자리에 얹는다 — 클릭 불필요.
     Shadow DOM에 원본 <style>+본문을 주입해 원본 디자인 그대로 보이게 하되,
     부서 체계 페이지의 스타일과는 서로 새지 않게 격리한다. */
  function renderPosting(mount, url) {
    var loading = document.createElement('p');
    loading.style.cssText = 'font-size:13px;color:var(--dim);margin:8px 0;';
    loading.textContent = '공고 내용을 불러오는 중…';
    mount.appendChild(loading);

    fetch(url)
      .then(function (r) { if (!r.ok) throw new Error('fetch_failed'); return r.text(); })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, 'text/html');
        var root = doc.getElementById('captureRoot');
        if (!root) throw new Error('no_captureRoot');

        /* 상대 경로 이미지(assets/...)를 원본 폴더 기준으로 재해석 —
           이 컴포넌트가 다른 폴더(coo/check/)에서 불러오기 때문에 그대로 두면 깨진다. */
        root.querySelectorAll('img[src]').forEach(function (img) {
          var v = img.getAttribute('src') || '';
          if (!/^(https?:)?\/\//.test(v) && v.indexOf('data:') !== 0 && v.indexOf('/') !== 0) {
            img.setAttribute('src', RECRUIT_BASE + v);
          }
        });

        var styleHTML = '';
        doc.querySelectorAll('head style').forEach(function (s) { styleHTML += s.outerHTML; });
        /* 원본 스타일의 :root{ --navy:...; } 와 body{ color:var(--ink); ... } 는 실제 문서
           루트/<body>에만 매치되고 Shadow DOM 안에는 그 태그가 없어 아무 것도 선택하지
           못한다 — 그 결과 var(--navy) 등이 빈 값이 되고(예: 지원하기 버튼 글자색 소실),
           본문 기본 글자색도 정의되지 않아 요소별로 뜻하지 않게 이 부서 페이지의 글자색을
           상속해(예: 밝은색 배경에 옅은 글자) 안 보이는 곳이 생긴다.
           원본 파일은 그대로 두고, 이 컴포넌트가 주입할 때만 줄 시작의 :root/body 선택자를
           :host로 바꿔(":body" 같은 다른 선택자는 건드리지 않음) 같은 변수·기본 글자색이
           이 Shadow DOM 안에서도 원본과 동일하게 정의되게 한다. */
        styleHTML = styleHTML
          .replace(/(^|\n)(\s*):root(\s*\{)/, '$1$2:host$3')
          .replace(/(^|\n)(\s*)body(\s*\{)/, '$1$2:host$3');

        var host = document.createElement('div');
        host.className = 'hiring-embed';
        var shadow = host.attachShadow({ mode: 'open' });
        /* 좌측정렬·폭 최대 활용(GM 지시) — 원본의 .wrap은 max-width:1040px에 margin:0 auto로
           가운데 정렬되도록 디자인돼 있다. 이 탭은 .board-fullwidth로 이미 화면 폭을 최대로
           쓰고 있으므로, 그 안에서까지 원본이 다시 가운데로 좁게 모이면 양옆에 큰 빈 여백이
           남는다 — 내용·스타일은 원본 그대로 두고 정렬·폭만 이 탭에 맞게 편다. */
        shadow.innerHTML = '<style>:host{display:block;} .wrap{margin:0!important;max-width:100%!important;}</style>' + styleHTML +
          '<div class="wrap" id="captureRoot">' + root.innerHTML + '</div>';

        /* 지원하기 버튼 — 원본 페이지의 모달·업로드 스크립트는 여기 없으므로
           원본 페이지를 새 창으로 열어 그 자리에서 지원을 이어가게 한다. */
        var applyBtn = shadow.getElementById('applyOpenBtn');
        if (applyBtn) {
          applyBtn.removeAttribute('onclick');
          applyBtn.addEventListener('click', function () { window.open(url, '_blank', 'noopener'); });
        }

        loading.remove();
        mount.appendChild(host);
      })
      .catch(function () {
        loading.textContent = '공고 내용을 불러오지 못했습니다. 새로고침 후 다시 시도해 주세요. (원본: ' + url + ')';
      });
  }

  function paint(host, dept, jobs) {
    /* 대응표에 없는 공고 = 미분류 — 조용히 사라지지 않도록 콘솔에 남긴다. */
    jobs.filter(function (j) { return j.closed !== true; }).forEach(function (j) {
      if (!matchPage(j)) console.warn('[hiring-status] 미분류 공고 — JOB_PAGES에 대응 없음:', j.position || j.bucket || j);
    });

    var open = jobs.filter(function (j) {
      return j.closed !== true && deptOf(j) === dept;
    });

    host.innerHTML =
      '<div style="margin:14px 0;">' +
        '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px;">' +
          '<span style="font-size:14px;font-weight:700;color:var(--accent);">🧑‍💼 ' + esc(dept) + ' 채용 현황</span>' +
          (open.length ? '<span style="font-size:11.5px;font-weight:700;color:#2f7d4f;background:#e6f4ea;border:1px solid #cfe9d7;border-radius:999px;padding:3px 10px;">모집 중 ' + open.length + '건</span>' : '') +
          '<a href="' + RECRUIT_BASE + 'index.html" target="_blank" rel="noopener" style="margin-left:auto;font-size:12.5px;color:var(--accent);text-decoration:none;font-weight:650;white-space:nowrap;">전체 채용 목록 ↗</a>' +
        '</div>' +
        (open.length ? '' : '<p style="font-size:13px;color:var(--dim);margin:0 0 8px;">현재 ' + esc(dept) + '에서 모집 중인 자리가 없습니다.</p>') +
        '<div id="hiring-postings"></div>' +
        (open.length ? '<p style="font-size:11.5px;color:var(--dim);margin:16px 0 0;line-height:1.6;">채용 시트(인사 담당 관리)와 원본 공고 페이지에서 자동으로 불러옵니다 — 원본이 바뀌면 여기도 함께 바뀝니다. 지원은 원본 페이지에서 진행됩니다.</p>' : '') +
      '</div>';

    var postHost = host.querySelector('#hiring-postings');
    open.forEach(function (j, i) {
      var p = matchPage(j);
      var url = RECRUIT_BASE + (p ? p.file : 'index.html');
      var block = document.createElement('div');
      if (i > 0) block.style.cssText = 'margin-top:22px;border-top:1px dashed var(--border);padding-top:18px;';
      postHost.appendChild(block);
      renderPosting(block, url);
    });
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
