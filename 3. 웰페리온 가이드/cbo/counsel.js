/* 상담봇 화면 셋(상담봇·상담 내역·FAQ) 공통 부품.
   업체 목록·업체 탭·하위 메뉴를 한 곳에서 만든다 — 화면마다 목록을 따로 들고 있다가
   하나가 낡는 일을 막는다(2026-09-11: 관리 화면이 없어진 업체를 가리키고 있었다). */
(function (g) {
  "use strict";

  var PAGES = [
    { file: "counsel_admin.html", name: "상담봇" },
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

  /* 업체 목록을 읽고 지금 고른 업체를 정한다(?t=). 목록을 못 읽으면 화면이 빈 채로 서지 않게 오류를 올린다. */
  function load() {
    return j("counsel_tenants.json").then(function (d) {
      var list = d.tenants || [];
      if (!list.length) throw new Error("업체 목록이 비어 있다");
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
      return '<a href="' + p.file + '?t=' + encodeURIComponent(ctx.cur.id) + '"' +
        (p.file === activeFile ? ' class="on"' : '') + '>' + esc(p.name) + '</a>';
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
