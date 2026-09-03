/* page_ping.js — 화면 열람 흔적 1줄 (GM 승인 2026-08-12 · 배478)

   왜 있나
     "아무도 안 여는 화면은 잘 만들어도 완성이 아니다"가 화면 완성도 채점축 하나인데,
     그걸 잴 방법이 없었다. GitHub Pages 는 접속 로그를 안 주고, 저장소 안 어떤 파일도
     "사람이 이 화면을 열었다"를 기록하지 않는다(2026-08-12 전수 실측 — 43개 중 0개).

   무엇을 보내나
     화면 경로와 시각, 그 둘뿐이다. 회원 정보·개인 정보·화면 내용은 보내지 않는다.
       { action:'saveBoard', key:'ping:/coo/check/운영부 체계.html', board:{ last:'2026-08-12 09:14' } }

   어디에 쌓이나
     이미 쓰고 있는 점검 GAS 의 범용 보드 저장소(saveBoard). GAS 코드는 한 줄도 안 바꿨고
     재배포도 없다 — 기존 통로를 그대로 쓴다(약속 L21).
     화면마다 키가 따로라 여러 화면이 동시에 열려도 서로 덮어쓰지 않는다.

   읽는 쪽
     scripts/page_score_extract.py --ping  (하루 1회) → status/page_ping.json

   ponytail: 마지막 열람 시각만 남기고 횟수는 안 센다. 지금 필요한 답은 "한 번이라도 열리나"
   뿐이라 횟수를 세려면 읽고-더하고-쓰기가 되어 경합이 생긴다. 횟수가 필요해지면 그때 GAS 에
   증가 전용 action 을 하나 두는 쪽이 맞다.
*/
(function () {
  var URL = 'https://script.google.com/macros/s/AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec';
  try {
    var path = decodeURIComponent(location.pathname);
    // 로컬에서 파일로 열어 본 것(file://)은 실사용이 아니라 세지 않는다.
    if (location.protocol === 'file:') return;
    var d = new Date();
    var p = function (n) { return (n < 10 ? '0' : '') + n; };
    var stamp = d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) +
                ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
    fetch(URL, {
      method: 'POST', redirect: 'follow', headers: { 'Content-Type': 'text/plain' },
      body: JSON.stringify({ action: 'saveBoard', key: 'ping:' + path, board: { last: stamp } })
    }).catch(function () { /* 실패해도 화면 동작에 영향 없음 — 계측일 뿐이다 */ });
  } catch (e) { /* 같은 이유 */ }
})();

/* ── 새 주소 안내 띠 (웰리 2026-09-03 · GM 지시 "기존에 있던 페이지에 이동 페이지 링크까지 걸어주던가") ──

   왜 여기인가
     ERP 가 AWS(erp.wellperion.com)로 옮겨 가는 중인데, 실무진 북마크·지난 카톡 링크는 여전히
     GitHub Pages 를 가리킨다. 화면 95개에 각각 안내를 넣으면 파일 95개를 건드려 시토의 이전
     작업과 부딪힌다. 이 파일 하나가 이미 35개 화면에 실려 있어, 여기 한 곳만 고치면 그 화면들에
     한꺼번에 뜬다(약속 L21 — 새 파일·새 배선 만들지 않는다).

   안 뜨는 경우
     ① 이미 새 주소(erp.wellperion.com)에서 열었을 때 ② 오늘 닫기를 눌렀을 때 ③ file:// 로 열었을 때.

   ponytail: 띠 하나. 자동 이동(리다이렉트)은 하지 않는다 — 쓰던 화면이 갑자기 로그인으로 튀면
   실무진이 하던 일을 잃는다. 옮길지는 사람이 고른다.
*/
(function () {
  try {
    if (location.protocol === 'file:') return;
    if (location.hostname === 'erp.wellperion.com') return;      // 이미 새 집
    var KEY = 'wp_erp_move_hide_' + new Date().toISOString().slice(0, 10);
    if (localStorage.getItem(KEY)) return;                        // 오늘은 닫음

    // 새 주소 = 같은 경로. GitHub Pages 의 저장소 접두어(/wellperion-automation)는 뗀다.
    var path = location.pathname.replace(/^\/wellperion-automation/, '');
    var to = 'https://erp.wellperion.com' + path + location.search + location.hash;

    var bar = document.createElement('div');
    bar.setAttribute('data-wp-move', '1');
    bar.style.cssText = 'position:sticky;top:0;z-index:99999;display:flex;align-items:center;gap:10px;' +
      'flex-wrap:wrap;padding:8px 14px;background:#14304E;color:#fff;font-size:13px;line-height:1.45;' +
      "font-family:'Noto Sans KR',sans-serif;box-shadow:0 1px 6px rgba(0,0,0,.25)";
    bar.innerHTML =
      '<b style="font-weight:700">업무 화면이 새 주소로 옮겨집니다</b>' +
      '<span style="opacity:.9">회사 구글 계정(@wellperion.com)으로 로그인하면 됩니다 · 이 주소도 당분간 그대로 열립니다</span>' +
      '<a href="' + to + '" style="margin-left:auto;background:#fff;color:#14304E;font-weight:700;' +
      'padding:5px 13px;border-radius:4px;text-decoration:none">새 주소로 열기</a>' +
      '<button type="button" style="background:transparent;color:#fff;border:1px solid rgba(255,255,255,.5);' +
      'border-radius:4px;padding:4px 10px;font:inherit;cursor:pointer">오늘 그만 보기</button>';
    bar.querySelector('button').onclick = function () {
      try { localStorage.setItem(KEY, '1'); } catch (e) {}
      bar.remove();
    };
    var put = function () { if (document.body) document.body.insertBefore(bar, document.body.firstChild); };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', put);
    else put();
  } catch (e) { /* 안내 띠 실패가 화면을 막지 않는다 */ }
})();
