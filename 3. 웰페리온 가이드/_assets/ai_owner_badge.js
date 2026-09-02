/* 관리 주체 이름표 — 화면 제목 옆에 「AI 시우」를 붙인다. (GM 지시 2026-09-02)
 *
 * 왜 있나
 *   시우가 소유·관리하는 화면이 서른 장이 넘는데, 열어 보면 누가 관리하는 화면인지 안 보였다.
 *   GM: "시우가 관리하는 페이지는 항상 제목옆에 AI 시우 라고 표시해줘."
 *
 * 왜 파일 하나인가
 *   서른 장에 같은 마크업을 손으로 심으면 문구를 바꿀 때 서른 장을 다시 고쳐야 한다.
 *   여기 한 곳만 고치면 전부 따라온다(약속 L01·L21).
 *
 * 쓰는 법
 *   각 화면 </body> 앞에 한 줄:  <script src="{경로}/_assets/ai_owner_badge.js" defer></script>
 *   다른 담당의 화면에 붙일 때는 태그에 이름만 준다:  <script src="..." data-owner="AI 시토" defer></script>
 *
 * 인쇄에서는 숨긴다
 *   현장에 붙이는 공지문·회장님 보고서도 이 목록에 들어 있다. 종이에까지 AI 이름이 찍히면
 *   읽는 사람에게는 군더더기다 — 화면에서만 보이고 인쇄물에는 안 나온다.
 */
(function () {
  if (window.__wlpOwnerBadge) return;      /* 한 화면에 두 번 실려도 하나만 */
  window.__wlpOwnerBadge = true;

  var me = document.currentScript;
  var owner = (me && me.getAttribute('data-owner')) || 'AI 시우';

  /* 이미 담당이 적혀 있는 화면에는 붙이지 않는다 — 이름이 두 개 나란히 서면 누구 것인지 더 헷갈린다.
     실측 2026-09-02: 매출회원현황보고는 「AI 시포」, GM업무는 「AI 웰리」가 이미 제목 줄에 있었다. */
  var ALREADY = /AI\s*(웰리|시토|시모|시포|시뽀|시로|시우)/;

  function put() {
    if (document.querySelector('.wlp-owner-badge')) return;
    var head = document.querySelector('.head, header, .letterhead, .hd') || document.body;
    var headText = String((head && head.textContent) || '').slice(0, 600);
    if (ALREADY.test(headText)) return;

    var st = document.createElement('style');
    st.textContent =
      '.wlp-owner-badge{display:inline-flex;align-items:center;gap:4px;vertical-align:middle;' +
      'margin-left:10px;padding:2px 9px;border-radius:20px;border:1px solid rgba(176,141,87,.45);' +
      'background:rgba(176,141,87,.10);color:#a4854f;font-size:11.5px;font-weight:700;' +
      'letter-spacing:.01em;line-height:1.7;white-space:nowrap;font-family:inherit;vertical-align:middle}' +
      '@media print{.wlp-owner-badge{display:none!important}}';
    document.head.appendChild(st);

    /* 제목을 찾는 순서 — 화면마다 마크업이 달라 후보를 넓게 잡는다. 눈에 보이는 첫 제목에만 붙인다. */
    var sels = ['h1', '.title', '.page-title', '.hd-title', '.head .title', '.brand h1', 'header h1', 'h2'];
    var el = null;
    for (var i = 0; i < sels.length && !el; i++) {
      var list = document.querySelectorAll(sels[i]);
      for (var j = 0; j < list.length; j++) {
        var n = list[j];
        if (n.offsetParent !== null && String(n.textContent || '').trim()) { el = n; break; }
      }
    }
    var b = document.createElement('span');
    b.className = 'wlp-owner-badge';
    b.textContent = owner;
    b.title = '이 화면을 관리하는 담당';

    if (el) {
      el.appendChild(b);
    } else {
      /* 제목을 못 찾으면 화면 왼쪽 위에 띄운다 — 안 붙는 것보다 낫다 */
      b.style.cssText = 'position:fixed;top:8px;left:10px;z-index:9999';
      document.body.appendChild(b);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', put);
  } else {
    put();
  }
  /* 화면을 자바스크립트로 다시 그리는 곳이 있어(제목까지 갈아끼우는 화면) 한 번 더 확인한다 */
  setTimeout(put, 1500);
})();
