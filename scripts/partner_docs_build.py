#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""partner_docs_build.py — 파트너 프로필 한 파일로 운영전략·소개서 빈칸을 자동 셋팅 (GM 2026-09-18 배 12762).

구조(세 층 · 값은 한 곳에만):
  파트너 프로필  2. 브랜드_자료/{폴더}/partner_profile.json — 대표의 방향·목표·기준선·채널·받은 것·qa 참조.
                받은 값만 적고 못 받은 값은 null → 화면엔 「미수집」. 사실값(주소·시간·규정)은 md/client.json 정본 그대로.
  랩스 BM 정의   erp/admin/company_roadmap.html §2-1 표의 <tr data-module="…"> 행 — 랩스가 제공하는 것의 이름·상품.
                여기서 읽는다(값 복사 금지). 새 모듈은 그 표에 행을 넣으면 된다.
  qa 답 원장     server/counselbot/tenants/{tenant}_qa.json — 남은 번호 수를 센다.
만드는 것:
  erp/admin/{line}/strategy.html   전체를 다시 그린다(북극성 · 재는 숫자 · 목표→랩스가 제공→재는 숫자 · 진단 · 90일 · 빈칸).
  erp/admin/{line}/intro.html      <!-- pb:notyet --> / <!-- pb:foot --> 슬롯만 바꾼다(본문은 손으로 쓴 소개서 그대로).
  erp/admin/company_roadmap.html   <!-- pb:partners --> 슬롯 — 파트너 목표 → 랩스가 제공 → 재는 숫자(파트너별 행).
판 번호 파일(_v1/_v2)은 만들지 않는다 — 같은 이름으로 덮고 이력은 저장소.
손 실행:
  C:/Python314/python.exe scripts/partner_docs_build.py --tenant dc        (jo · all)
  C:/Python314/python.exe scripts/partner_docs_build.py --selfcheck        (빈 프로필 → 미수집만 · 지어낸 값 0)
배포는 기존 bash server/deploy_{line}.sh · deploy_labs.sh 그대로.
"""
from __future__ import annotations

import argparse
import html
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADMIN = ROOT / "3. 웰페리온 가이드" / "erp" / "admin"
ROADMAP = ADMIN / "company_roadmap.html"
FOLDERS = {
    "dc": ROOT / "2. 브랜드_자료" / "10_다이어트캠프_브랜드가이드",
    "jo": ROOT / "2. 브랜드_자료" / "11_고척골프_조재오부장님",
}
MISSING = "미수집"


def esc(s) -> str:
    return html.escape(str(s), quote=False)


def v(x) -> str:
    """값이 없으면 미수집 — None 이 화면에 「None」으로 새는 것을 막는 유일한 관문."""
    return esc(x) if x not in (None, "", []) else MISSING


def load_profile(tenant: str) -> dict:
    return json.loads((FOLDERS[tenant] / "partner_profile.json").read_text(encoding="utf-8"))


def labs_modules(text: str | None = None) -> dict[str, dict]:
    """company_roadmap.html §2-1 표 → {id: {name, product}} · 표에 없는 모듈은 화면에 못 나온다."""
    text = text if text is not None else ROADMAP.read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r'<tr data-module="([a-z0-9_]+)"><td>(.*?)</td><td>.*?</td><td>(.*?)</td></tr>', text, re.S):
        out[m.group(1)] = {"name": re.sub(r"<.*?>", "", m.group(2)).strip(), "product": re.sub(r"<.*?>", "", m.group(3)).strip()}
    return out


def qa_counts(p: dict) -> tuple[int | None, int | None]:
    """(답 받은 수, 남은 수) — qa 파일이 없으면 (None, None)."""
    ref = p.get("qa_ref")
    if not ref:
        return None, None
    try:
        rows = json.loads((ROOT / ref).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None, None
    ans = sum(1 for r in rows if r.get("answer") not in (None, ""))
    return ans, len(rows) - ans


# ---------- 조각 ----------

def _chapter(no: int, label: str, title: str, body: str, alt: bool = False, lead: str = "") -> str:
    cls = "dc-chapter alt" if alt else "dc-chapter"
    lead_html = f'\n      <p class="dc-lead">{lead}</p>' if lead else ""
    return (f'<section class="{cls}">\n  <div class="wrap">\n    <div class="chapter-head">\n'
            f'      <span class="dc-label">{no:02d} · {label}</span>\n      <h2>{title}</h2>{lead_html}\n    </div>\n'
            f'{body}\n  </div>\n</section>\n')


def _ul(items: list) -> str:
    return "<ul>" + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>" if items else f"<ul><li>{MISSING}</li></ul>"


def goal_rows(p: dict, mods: dict) -> str:
    rows = []
    for g in p.get("goal_map") or []:
        labs = " · ".join(mods[m]["name"] if m in mods else f"{m}({MISSING})" for m in g.get("labs") or []) or MISSING
        rows.append(f"<tr><td>{v(g.get('goal'))}</td><td>{labs}</td><td>{v(g.get('measure'))}</td>"
                    f"<td>{v(g.get('baseline'))}</td><td>{v(g.get('note'))}</td></tr>")
    if not rows:
        rows.append(f'<tr><td colspan="5">{MISSING} — 목표 공지(공지_목표.md)가 오면 채운다</td></tr>')
    return "\n".join(rows)


def notyet_rows(p: dict, qa: tuple) -> str:
    ans, open_n = qa
    rows = [f"<tr><th>받은 것</th><td>{_ul(p.get('received') or [])}</td></tr>",
            f"<tr><th>아직 못 받은 것</th><td>{_ul(p.get('not_received') or [])}</td></tr>"]
    if open_n is None:
        rows.append(f"<tr><th>번호 질문</th><td>{MISSING}</td></tr>")
    else:
        rows.append(f"<tr><th>번호 질문</th><td>답 받음 {ans}개 · 남은 번호 <b>{open_n}개</b> — 저녁 한 통에 「남은 번호 N개」로만 여쭙습니다</td></tr>")
    return "\n      ".join(rows)


def foot_line(p: dict, doc: str, ver: str) -> str:
    return f'<div class="f-bottom">{doc} {esc(ver)} · {date.today().isoformat()} · 작성 = AI 시보 · 근거 = {esc(p.get("owner") or MISSING)} 답 · 프로필 partner_profile.json</div>'


# ---------- strategy.html 전체 ----------

def render_strategy(p: dict, mods: dict, qa: tuple) -> str:
    m = p.get("metrics") or {}
    ns, le, la = (m.get(k) or {} for k in ("north_star", "leading", "lagging"))
    nstar = p.get("north_star") or {}
    ver = (p.get("docs") or {}).get("strategy_version") or MISSING
    goals = p.get("goals") or {}
    nav = ('<nav class="gc-nav wrap"><a href="intro.html">소개서</a> · <a href="brand.html">브랜드가이드</a> · '
           '<a href="strategy.html">운영전략</a> · <a href="drafts_v0.1.html">초안 페이지</a> · '
           f'<a href="/{v(p.get("line"))}/counsel/">상담 페이지</a></nav>\n\n') if p.get("nav") else ""

    tiles = "".join(f'<div class="dc-tile"><div class="t-num">{v(x.get("tile") or x.get("baseline"))}</div><div class="t-label">{v(x.get("measure"))}</div></div>'
                    for x in (ns, le, la))

    def _mrow(th: str, x: dict, w: str = "") -> str:
        src = f' <span class="tag">{esc(x["source"])}</span>' if x.get("source") else ""
        return f'      <tr><th{w}>{th}</th><td>{v(x.get("what"))} — <b>{v(x.get("measure"))}</b> · 기준선 {v(x.get("baseline"))}{src}</td></tr>\n'
    metrics_tbl = ('<table class="dc-table">\n' + _mrow("북극성", ns, ' style="width:140px"') + _mrow("앞 지표", le) + _mrow("뒤 지표", la) + '    </table>')
    goals_html = ('<div class="dc-card"><span class="tag">' + v(goals.get("source")) + '</span>' + _ul(goals.get("items") or []) + '</div>\n'
                  '    <table class="dc-table" style="margin-top:16px">\n      <tr><th style="width:22%">' + v(p.get("owner_title")) + ' 목표</th><th style="width:22%">랩스가 제공하는 것</th><th>재는 숫자</th><th style="width:14%">기준선</th><th style="width:22%">비고</th></tr>\n      '
                  + goal_rows(p, mods) + '\n    </table>')
    lm = p.get("labs_modules") or {}
    mod_rows = "".join(f'<tr><th style="width:180px">{esc(mods[k]["name"])}</th><td><span class="tag">{v((lm.get(k) or {}).get("status"))}</span>'
                       + (f' {esc((lm.get(k) or {}).get("evidence"))}' if (lm.get(k) or {}).get("evidence") else "") + '</td></tr>'
                       for k in mods)
    mods_tbl = f'<table class="dc-table">{mod_rows or f"<tr><td>{MISSING}</td></tr>"}</table>'
    dg = p.get("diagnosis") or {}
    diag = ('<div class="two-col">\n      <div class="col good"><h4>강점 — 그대로 쓴다</h4>' + _ul(dg.get("strengths") or []) + '</div>\n'
            '      <div class="col bad"><h4>빈틈 — 여기를 채운다</h4>' + _ul(dg.get("gaps") or []) + '</div>\n    </div>')
    steps = "".join(f'<div class="dc-step"><div class="s-dot"></div><div class="s-num">{v(s.get("when"))}{" ✓" if s.get("done") else ""}</div><div class="s-desc">{v(s.get("what"))}</div></div>'
                    for s in (p.get("plan_90") or []))
    if not steps:
        steps = f'<div class="dc-step"><div class="s-dot"></div><div class="s-desc">{MISSING}</div></div>'
    plan = f'<div class="dc-timeline"><div class="dc-timeline-inner">{steps}</div></div>'
    comm = ('<div class="dc-card"><p>' + v(p.get("owner_title")) + '께 가는 것은 저녁 21:00 한 통 + 페이지 링크. 페이지 왼쪽 = 지금, 오른쪽 = 다듬은 뒤 — Before &amp; After. 아침 통은 없습니다.</p>'
            '<p style="margin-top:10px">매달 보고도 같은 틀입니다 — 지난달 숫자(Before) ↔ 이번 달(After).</p></div>')
    notyet = f'<table class="dc-table">\n      {notyet_rows(p, qa)}\n    </table>'

    body = (_chapter(1, "NUMBERS", "재는 숫자", f'    <div class="dc-tiles">{tiles}</div>')
            + _chapter(2, "METRICS", "지표 3층", "    " + metrics_tbl, alt=True)
            + _chapter(3, "GOALS → LABS", f"{v(p.get('owner_title'))} 목표 → 웰페리온 AX 랩스가 제공하는 것 → 재는 숫자", "    " + goals_html)
            + _chapter(4, "MODULES", "지금 돌아가는 것", "    " + mods_tbl, alt=True, lead="웰페리온 AX 랩스가 이 센터에 실제로 켜 둔 자동화 — 안 도는 것은 「미도입 · 준비 중」으로 둡니다.")
            + _chapter(5, "DIAGNOSIS", "지금 자료로 본 진단", "    " + diag)
            + _chapter(6, "90 DAYS", "90일 계획", "    " + plan, alt=True)
            + _chapter(7, "COMMUNICATION", "매 소통은 페이지로", "    " + comm)
            + _chapter(8, "NOT YET", f"빈칸 목록 — {v(p.get('owner_title'))}께 받아야 완성됨", "    " + notyet, alt=True))

    return (f'''<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="../../../assets/wp-ui.css"><meta name="robots" content="noindex">
<title>{v(p.get("name"))} — 운영전략 {esc(ver)}</title>
<link rel="stylesheet" as="style" crossorigin href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css" />
<link rel="stylesheet" href="{v(p.get("css"))}">
</head><body>

{nav}<header class="dc-hero">
  <div class="hero-bg" style="background-image:url('{v(p.get("hero_img"))}')"></div>
  <div class="hero-overlay"></div>
  <div class="wrap hero-inner">
    <img src="{v(p.get("logo"))}" alt="{v(p.get("logo_alt"))}" style="height:44px;background:#fff;padding:6px 12px;border-radius:8px;margin-bottom:14px;display:block;width:max-content">
    <span class="dc-label on-dark">{v(p.get("label_en"))} · OPERATING STRATEGY · {esc(ver)}</span>
    <h1>{v(nstar.get("line"))}</h1>
    <div class="hero-sub">{v(nstar.get("sub"))} <span class="tag">{v(nstar.get("status"))}</span></div>
  </div>
</header>

{body}
<footer class="dc-footer">
  <div class="wrap">
    <div class="f-name">{v(p.get("label_en"))}</div>
    <div class="f-meta">{v(p.get("address_short"))} · {v(p.get("phone"))}</div>
    {foot_line(p, "문서", ver)}
  </div>
</footer>

</body></html>
''')


# ---------- 슬롯 채우기(intro.html · company_roadmap.html) ----------

def fill_slot(text: str, name: str, inner: str) -> str:
    """<!-- pb:name --> … <!-- /pb:name --> 사이만 바꾼다 · 표식이 없으면 실패(조용히 끼워 넣지 않는다)."""
    pat = re.compile(rf"(<!-- pb:{name} -->).*?(<!-- /pb:{name} -->)", re.S)
    if not pat.search(text):
        raise SystemExit(f"슬롯 표식 없음: pb:{name} — 파일에 <!-- pb:{name} --><!-- /pb:{name} --> 를 먼저 둔다")
    return pat.sub(lambda m: f"{m.group(1)}\n{inner}\n{m.group(2)}", text, count=1)


def intro_slots(p: dict, qa: tuple, text: str) -> dict[str, str]:
    ver = (p.get("docs") or {}).get("intro_version") or MISSING
    before = text.split("<!-- pb:notyet -->", 1)[0]
    nums = [int(n) for n in re.findall(r'class="dc-label">(\d{2}) ·', before)]
    no = (max(nums) + 1) if nums else 1
    notyet = _chapter(no, "NOT YET", f"빈칸 목록 — {v(p.get('owner_title'))}께 받아야 완성됨",
                      f'    <table class="dc-table">\n      {notyet_rows(p, qa)}\n    </table>', alt=(no % 2 == 0)).rstrip()
    return {"notyet": notyet, "foot": foot_line(p, "문서", ver)}


def bump_intro_version(text: str, ver: str) -> str:
    text = re.sub(r"(<title>[^<]*?)v\d+\.\d+", rf"\g<1>{ver}", text, count=1)
    return re.sub(r'(COMPANY INTRODUCTION · )v\d+\.\d+', rf"\g<1>{ver}", text, count=1)


def roadmap_partner_rows(profiles: list[dict], mods: dict) -> str:
    rows = []
    for p in profiles:
        first = True
        gm = p.get("goal_map") or []
        for g in gm:
            labs = " · ".join(mods[m]["name"] if m in mods else f"{m}({MISSING})" for m in g.get("labs") or []) or MISSING
            head = f'<td rowspan="{len(gm)}"><b>{v(p.get("name"))}</b><br><span class="note">{v(p.get("owner"))} · {v((p.get("goals") or {}).get("source"))}</span></td>' if first else ""
            first = False
            rows.append(f"<tr>{head}<td>{v(g.get('goal'))}</td><td>{labs}</td><td>{v(g.get('measure'))}</td><td>{v(g.get('baseline'))}</td></tr>")
        if not gm:
            rows.append(f'<tr><td><b>{v(p.get("name"))}</b></td><td colspan="4">{MISSING}</td></tr>')
    return "\n".join(rows)


def build(tenant: str, dry: bool = False) -> list[Path]:
    p = load_profile(tenant)
    mods = labs_modules()
    qa = qa_counts(p)
    line = ADMIN / p["line"]
    written = []
    # strategy.html 전체
    out = render_strategy(p, mods, qa)
    if not dry:
        (line / "strategy.html").write_text(out, encoding="utf-8")
    written.append(line / "strategy.html")
    # intro.html 슬롯
    intro_path = line / "intro.html"
    text = intro_path.read_text(encoding="utf-8")
    for k, inner in intro_slots(p, qa, text).items():
        text = fill_slot(text, k, inner)
    text = bump_intro_version(text, (p.get("docs") or {}).get("intro_version") or MISSING)
    if not dry:
        intro_path.write_text(text, encoding="utf-8")
    written.append(intro_path)
    return written


def build_roadmap(dry: bool = False) -> Path:
    text = ROADMAP.read_text(encoding="utf-8")
    mods = labs_modules(text)
    profiles = [load_profile(t) for t in FOLDERS]
    text = fill_slot(text, "partners", roadmap_partner_rows(profiles, mods))
    if not dry:
        ROADMAP.write_text(text, encoding="utf-8")
    return ROADMAP


# ---------- 자가검사 ----------

EMPTY = {"tenant": "x", "line": "x", "name": None, "label_en": None, "owner": None, "owner_title": None, "css": "dc.css",
         "goals": {}, "north_star": {}, "metrics": {}, "goal_map": [], "labs_modules": {}, "channels": {},
         "received": [], "not_received": [], "diagnosis": {}, "plan_90": [], "docs": {}, "qa_ref": None}


def selfcheck() -> None:
    mods = labs_modules()
    assert {"docs3", "marketing", "counsel", "report"} <= set(mods), f"로드맵 §2-1 data-module 행이 모자란다: {sorted(mods)}"
    out = render_strategy(EMPTY, mods, qa_counts(EMPTY))
    assert MISSING in out and "None" not in out, "빈 프로필인데 None 이 새거나 미수집이 안 찍힌다"
    # 실제 프로필 값이 빈 프로필 출력에 섞이면 지어낸 것이다
    for tok in ("65~80", "430", "고척", "다이어트캠프", "이승기", "조재오"):
        assert tok not in out, f"빈 프로필 출력에 실값 {tok!r} 이 들어 있다"
    slots = intro_slots(EMPTY, (None, None), "<!-- pb:notyet --><!-- /pb:notyet -->")
    assert "01 · NOT YET" in slots["notyet"] and MISSING in slots["notyet"]
    # 실제 프로필 두 장 — 표식·qa 파일·모듈 id 가 다 맞물리는지(파일은 안 쓴다)
    for t in FOLDERS:
        p = load_profile(t)
        for g in p.get("goal_map") or []:
            for m in g.get("labs") or []:
                assert m in mods, f"{t} goal_map 모듈 {m} 이 로드맵 §2-1 에 없다"
        ans, open_n = qa_counts(p)
        assert ans is not None, f"{t} qa 파일을 못 읽는다"
        build(t, dry=True)
    build_roadmap(dry=True)
    print("partner_docs_build selfcheck 통과 · 모듈", sorted(mods))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", choices=[*FOLDERS, "all"], help="dc · jo · all")
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        selfcheck()
        return
    if not a.tenant:
        ap.error("--tenant 또는 --selfcheck")
    tenants = list(FOLDERS) if a.tenant == "all" else [a.tenant]
    for t in tenants:
        for f in build(t, dry=a.dry_run):
            print(("[dry] " if a.dry_run else "") + str(f.relative_to(ROOT)))
    print(("[dry] " if a.dry_run else "") + str(build_roadmap(dry=a.dry_run).relative_to(ROOT)))


if __name__ == "__main__":
    main()
