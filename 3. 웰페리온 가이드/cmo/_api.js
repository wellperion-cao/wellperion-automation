// 시모(CMO) 화면 GAS 주소 단일 출처 — 서버 API 로 바꿀 때 여기 한 줄만 고친다.
// 정본 = 시토 API 규격(배960). 값은 지금 쓰는 GAS 배포 URL 그대로(동작 불변).
window.WP_CMO_API = {
  funnel: "https://script.google.com/macros/s/AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec",
  intake: "https://script.google.com/macros/s/AKfycbz4wWhqICMQZR3F9bQc-7_LsDDA9Ywb-g-Q-6BNwjvqiw1EwAT_U94nEjUsf-Uor8uH/exec"
};

// ★API 먼저·GAS 폴백 (시토 배922 _chkRead 와 같은 모양 · 배960). ERP 도메인에서만 서버 거울 /api/funnel?<같은 쿼리> 를
// 먼저 부르고, 실패(미로그인·404·다운)하면 종전 GAS 로 조용히 돌아간다. GitHub Pages·로컬에선 apiOn=false 라 종전 그대로.
// 반환은 fetch Response 그대로 — 호출부의 r.ok / r.json() 코드가 안 바뀐다. 경로 확정 = 시토 배960.
window.WP_CMO_API.apiOn = /^(erp\.wellperion\.com|15\.164\.151\.105)$/.test(location.hostname);
window.wpCmoFetch = function(gasUrl, opts){
  var gas = function(){ return fetch(gasUrl, opts || { redirect: 'follow' }); };
  if (!window.WP_CMO_API.apiOn) return gas();
  var q = gasUrl.indexOf('?') >= 0 ? gasUrl.slice(gasUrl.indexOf('?')) : '';
  return fetch('/api/funnel' + q).then(function(r){ if (!r.ok) throw new Error('api ' + r.status); return r; })
    .catch(function(e){ console.warn('[퍼널] API 실패 → GAS 폴백:', e && e.message); return gas(); });
};
