/* 상담봇 화면 셋(상담봇·상담 내역·FAQ) 공통 부품.
   업체 목록·업체 탭·하위 메뉴를 한 곳에서 만든다 — 화면마다 목록을 따로 들고 있다가
   하나가 낡는 일을 막는다(2026-09-11: 관리 화면이 없어진 업체를 가리키고 있었다). */
(function (g) {
  "use strict";

  // 경로는 이 스크립트(cbo/) 기준 — 상담봇 관리 화면은 랩스(erp/admin/)로 옮겨 세 화면이 한 폴더에 있지 않다(배 2513 · 2026-09-16).
  var BASE = (document.currentScript && document.currentScript.src || "").replace(/[^\/]*$/, "");
  var PAGES = [
    { file: "../erp/admin/counsel_admin.html", name: "AI 상담비서" },
    { file: "counsel_log.html", name: "상담 내역" },
    { file: "counsel_faq.html", name: "FAQ" }
  ];

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function j(url, opts) {
    return fetch(url, opts).then(function (r) {
      if (!r.ok) throw new Error(r.status + "");
      return r.json();
    });
  }

  /* 업체 목록을 읽고 지금 고른 업체를 정한다(?t=). 목록을 못 읽으면 화면이 빈 채로 서지 않게 오류를 올린다.
     파트너 계정(perms.tenant)은 자기 센터 하나로 목록을 줄인다 — ?t= 로 다른 센터를 적어도 무시한다
     (배 12768 §12⑤). /auth/me 를 못 읽으면(네트워크 오류 등) 종전처럼 전체 목록 그대로 — 관리자와 같은 동작. */
  function load() {
    return Promise.all([
      j(BASE + "counsel_tenants.json"),
      j("/auth/me").catch(function () { return null; })
    ]).then(function (r) {
      var list = r[0].tenants || [], me = r[1];
      if (!list.length) throw new Error("업체 목록이 비어 있다");
      if (me && me.tenant) {
        list = list.filter(function (t) { return t.id === me.tenant; });
        if (!list.length) throw new Error("허용된 업체가 없다");
      }
      var want = new URLSearchParams(location.search).get("t");
      var cur = list.filter(function (t) { return t.id === want; })[0] || list[0];
      return { list: list, cur: cur, api: "/api/chat/" + cur.id };
    });
  }

  function tabs(el, ctx) {
    el.innerHTML = ctx.list.map(function (t) {
      return '<a href="?t=' + encodeURIComponent(t.id) + '"' +
        (t.id === ctx.cur.id ? ' class="on"' : '') + '>' + esc(t.name) + '</a>';
    }).join("");
  }

  function subnav(el, ctx, activeFile) {
    el.innerHTML = PAGES.map(function (p) {
      return '<a href="' + BASE + p.file + '?t=' + encodeURIComponent(ctx.cur.id) + '"' +
        (p.file.split("/").pop() === activeFile ? ' class="on"' : '') + '>' + esc(p.name) + '</a>';
    }).join("");
  }

  /* 세 화면이 같은 방식으로 시작한다: 목록 읽기 → 탭·하위메뉴 그리기 → 화면별 본문. */
  function start(activeFile, render) {
    load().then(function (ctx) {
      tabs(document.getElementById("tabs"), ctx);
      subnav(document.getElementById("subnav"), ctx, activeFile);
      render(ctx);
    }).catch(function (e) {
      document.getElementById("subline").textContent = "업체 목록을 읽지 못했습니다 — " + e.message;
    });
  }

  g.Counsel = { esc: esc, j: j, start: start, PAGES: PAGES };
})(window);
