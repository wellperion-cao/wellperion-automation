/* 개인 캘린더 전용 서비스워커 — 2026-08-28 PWA 전환(A-5).
   등록은 calendar.html에서 {scope:"calendar.html"}로 좁혀서 하므로, 이 SW는 오직 calendar.html
   내비게이션만 제어한다(다른 허브 페이지: index.html/schedule.html 등은 절대 건드리지 않음).
   캐시 대상 = 앱 셸(정적 파일)뿐 — POST(Apps Script API, 지원자·온보딩 등 PII 포함 가능)는
   Cache API가 애초에 비-GET 요청을 지원하지 않아 아래 fetch 핸들러에서 무조건 통과시킨다. */
var CACHE_NAME = 'wp-cal-shell-v1';
var SHELL_URLS = [
  'calendar.html',
  'calendar.webmanifest',
  'icons/cal-icon-192.png',
  'icons/cal-icon-512.png',
  'icons/cal-icon-maskable-512.png'
];

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE_NAME)
      .then(function (c) { return c.addAll(SHELL_URLS); })
      .then(function () { return self.skipWaiting(); })
      .catch(function () { /* 캐시 실패해도 SW 설치 자체는 막지 않음 */ })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) { return k !== CACHE_NAME; }).map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') return; // 백엔드 POST(cal-list/cal-add 등)는 그대로 네트워크로 — 캐시 개입 없음
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // 폰트 CDN 등 교차 출처는 이 SW가 개입하지 않음

  e.respondWith(
    caches.match(req).then(function (cached) {
      var networkFetch = fetch(req).then(function (res) {
        if (res && res.ok) {
          var copy = res.clone();
          caches.open(CACHE_NAME).then(function (c) { c.put(req, copy); });
        }
        return res;
      }).catch(function () { return cached; }); // 오프라인이면 캐시로 폴백
      return cached || networkFetch; // 캐시 있으면 즉시 응답 + 백그라운드 갱신(stale-while-revalidate)
    })
  );
});
