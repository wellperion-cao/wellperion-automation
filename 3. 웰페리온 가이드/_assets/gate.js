/*!
 * Wellperion 사내 게이트 (단일 출처) — 민감 페이지 전용 "가림막".
 * ─────────────────────────────────────────────────────────────
 * ⚠️ 이것은 "잠금"이 아니라 "커튼"입니다.
 *   - 이 파일은 공개 호스팅(GitHub Pages)에 그대로 노출됩니다 → 비밀번호도 사실상 공개입니다.
 *   - 우연·실수로 들어온 사람은 막지만, 작정한 사람은 소스 보기로 우회 가능합니다.
 *   - 진짜 잠금 = JWT 인증 + 자체 서버 (배 21·101, ≈2026-09 가용). 그때 이 커튼을 교체합니다.
 * 그러므로 이 비밀번호는 서버·계정 등 "진짜 중요한 비밀번호"와 절대 같게 쓰지 마세요.
 *
 * 사용법: 보호할 페이지 <head> 안에 한 줄만 추가
 *   <script src="(경로)/_assets/gate.js" charset="utf-8"></script>
 *   - 2단계 깊이(cfo/finance 등): ../../_assets/gate.js
 *   - 루트(wellperion_*.html):     _assets/gate.js
 */
(function () {
  "use strict";

  // ── 단일 출처: 비밀번호는 오직 여기서만 관리 ──────────────────
  var GATE_PW = "wellperion!@345";
  window.WELP_GATE_PW = GATE_PW; // 기존 GAS 호출(password 동봉) 호환용
  var SKEY = "welp_gate_ok";     // 같은 탭 세션에서 한 번 통과하면 다른 보호 페이지도 통과

  try {
    if (sessionStorage.getItem(SKEY) === "1") return; // 이미 통과 → 게이트 표시 안 함
  } catch (e) {}

  var root = document.documentElement;

  // 본문 깜빡임(플래시) 방지: 통과 전엔 body 숨김, 게이트만 보이게
  var hideStyle = document.createElement("style");
  hideStyle.setAttribute("data-welp-gate", "");
  hideStyle.textContent =
    "body{visibility:hidden!important}" +
    "#welpGate{visibility:visible!important}" +
    "#welpGate{position:fixed;inset:0;z-index:2147483647;display:flex;align-items:center;justify-content:center;" +
    "background:linear-gradient(180deg,#262524,#1a1918);padding:20px;" +
    "font-family:'Pretendard',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Malgun Gothic',sans-serif}" +
    "#welpGate .gc{background:#2f2d2b;border:1px solid #45423f;border-radius:14px;padding:34px 28px;max-width:344px;" +
    "width:100%;text-align:center;box-shadow:0 18px 50px rgba(0,0,0,.45)}" +
    "#welpGate .mk{font-size:11px;letter-spacing:.28em;color:#c9a24b;font-weight:700;text-transform:uppercase}" +
    "#welpGate h2{margin:10px 0 4px;font-size:18px;color:#f3efe9;font-weight:600}" +
    "#welpGate p{margin:0;font-size:12px;color:#a8a39c;line-height:1.5}" +
    "#welpGate input{width:100%;box-sizing:border-box;text-align:center;padding:11px;margin-top:16px;" +
    "border:1px solid #45423f;border-radius:8px;background:#1f1d1c;color:#f3efe9;font:13px inherit;outline:none}" +
    "#welpGate input:focus{border-color:#c9a24b}" +
    "#welpGate button{width:100%;margin-top:10px;padding:11px;border:0;border-radius:8px;cursor:pointer;" +
    "background:#c9a24b;color:#1a1918;font:600 13px inherit}" +
    "#welpGate button:hover{background:#d8b55f}" +
    "#welpGate .er{color:#e06a5a;font-size:12px;margin-top:10px;min-height:16px}";
  root.appendChild(hideStyle);

  function unlock() {
    try { sessionStorage.setItem(SKEY, "1"); } catch (e) {}
    var s = document.querySelector('style[data-welp-gate]');
    if (s) s.parentNode.removeChild(s);
    var g = document.getElementById("welpGate");
    if (g) g.parentNode.removeChild(g);
    // 페이지가 게이트 통과 후 초기화를 원하면 startApp() 호출 (있을 때만)
    if (typeof window.startApp === "function" && !window.__welpStarted) {
      window.__welpStarted = true;
      try { window.startApp(); } catch (e) {}
    }
  }

  function build() {
    if (document.getElementById("welpGate")) return;
    var ov = document.createElement("div");
    ov.id = "welpGate";
    ov.innerHTML =
      '<div class="gc">' +
      '<div class="mk">WELLPERION</div>' +
      '<h2>사내 전용</h2>' +
      '<p>접근 비밀번호를 입력하세요.</p>' +
      '<input type="password" id="welpGatePw" placeholder="접근 비밀번호" autocomplete="current-password">' +
      '<button type="button" id="welpGateBtn">입장</button>' +
      '<div class="er" id="welpGateErr"></div>' +
      '</div>';
    (document.body || root).appendChild(ov);

    var input = document.getElementById("welpGatePw");
    var err = document.getElementById("welpGateErr");

    function attempt() {
      var v = (input.value || "").trim();
      if (!v) { err.textContent = "비밀번호를 입력해 주세요."; return; }
      if (v !== GATE_PW) { err.textContent = "비밀번호가 올바르지 않습니다."; input.select(); return; }
      unlock();
    }
    document.getElementById("welpGateBtn").addEventListener("click", attempt);
    input.addEventListener("keydown", function (e) { if (e.key === "Enter") attempt(); });
    setTimeout(function () { try { input.focus(); } catch (e) {} }, 30);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", build);
  } else {
    build();
  }
})();
