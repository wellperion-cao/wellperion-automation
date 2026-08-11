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
