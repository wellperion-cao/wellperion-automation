/* AX 랩스 관리 셸 끼움 — GM 2026-09-17 「화면 정돈 13번」(시모 나눔 · 시토).
   셸(왼쪽 메뉴+상단 바)은 /erp/admin/index.html 한 곳에만 있다. 이 스크립트를 넣은 화면이 셸 없이 단독으로 열리면
   같은 화면을 셸 안(#view/이름)으로 돌려보낸다 — 셸 마크업을 화면마다 복제하지 않는다(약속 L01).
   쓰는 법: <script src="/erp/admin/_assets/shell.js" data-view="auto"></script>
   - 셸 iframe 안이면 아무것도 안 한다. ?standalone=1 이면 단독 표시(헤드리스 검수·인쇄용).
   - erp 도메인 밖(GitHub Pages·file:)에서는 셸이 없으니 그대로 둔다. */
(function () {
  var me = document.currentScript;
  var view = me && me.getAttribute('data-view');
  if (!view) return;
  if (window.top !== window.self) return;                       // 이미 셸 안
  if (/[?&]standalone=1/.test(location.search)) return;
  if (!/^(erp\.wellperion\.com|15\.164\.151\.105)$/.test(location.hostname)) return;
  location.replace('/erp/admin/#view/' + encodeURIComponent(view));
})();
