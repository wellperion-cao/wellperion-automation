#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ops_fill_board.py — 실무진 업무판 '채움 보드' 생성기 (시우/COO · 2026-07-23 신설)

무엇을 만드나
  업무 현황 SSOT(GAS todo_list) + 월간 운영계획(status/monthly_ops_plan.json)을 읽어
  실무진이 '조금만 채우면 끝나는 것'을 한 장으로 보여주는 HTML 보드를 만든다.

왜 있나 (GM 2026-07-23 지시)
  두 포인트로 본다 — ①업무판에 아직 안 올라온 일 ②올라왔는데 잠시 쉬고 있는 일.
  세부는 마감일 미기재. 톤은 '기분 좋게' — 질책 어휘를 쓰지 않는다.

정직 원칙
  · 모든 수치는 실행 시점 실측. 추정·예시값 0 (약속 L05).
  · 경영진(김남욱GM·이정헌 소장) 담당 건은 월간 운영계획에서 부서 목표로 관리하므로 제외하고,
    '왜 없는지'를 보드 머리에 밝힌다(숨기지 않는다).

출력 2곳 — 같은 실행에서 함께 쓰므로 손사본이 아니다(드리프트 0)
  ① 3. 웰페리온 가이드/coo/todo/업무판 채움 보드.html  = 실무진 공개 주소(GitHub Pages)
  ② status/boards/s3_cleanup_board.html                = GM 아티팩트 소스

사용
  python scripts/ops_fill_board.py            # 보드 생성 + 요약 출력
  python scripts/ops_fill_board.py --json     # 수치만 JSON 으로(발신 스크립트에서 사용)

관련: 배9819(S3 소유·위생) · 배9836(보류 재부상·보고 카드화) · coo/todo/업무·결재 운영 기준.html
"""
from __future__ import annotations

import argparse
import collections
import datetime
import html as html_mod
import io
import json
import os
import sys
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = r"C:\Users\jjky0\welperion-automation"
PLAN = os.path.join(BASE, "status", "monthly_ops_plan.json")
TODO_URL = ("https://script.google.com/macros/s/"
            "AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"
            "?action=todo_list")
OUTS = [
    os.path.join(BASE, "3. 웰페리온 가이드", "coo", "todo", "업무판 채움 보드.html"),
    os.path.join(BASE, "status", "boards", "s3_cleanup_board.html"),
]
_SCRIPTS_DIR_FOR_WORKLOG = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR_FOR_WORKLOG not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR_FOR_WORKLOG)

try:  # 작업 현황 로그(best-effort) — 임포트 실패해도 보드 생성 흐름 무영향
    from worklog import log as worklog_log
except Exception:
    def worklog_log(*a, **k):
        return False

PAGES = "https://wellperion-cao.github.io/wellperion-automation/coo/todo/"
LINK_TODO = PAGES + "%EC%97%85%EB%AC%B4%20%ED%98%84%ED%99%A9%20SSOT.html"
LINK_RULE = PAGES + "%EC%97%85%EB%AC%B4%C2%B7%EA%B2%B0%EC%9E%AC%20%EC%9A%B4%EC%98%81%20%EA%B8%B0%EC%A4%80.html"

# 경영진 — 월간 운영계획에서 부서 목표로 관리하므로 이 보드에서 제외
EXEC_OWNERS = ("김남욱GM", "이정헌 소장")
DEPT_OF = {"최준용M": "운영부", "나우열M": "파트너·인사", "윤병현AM": "운영부",
           "이경연 실장": "운영부", "이정헌 소장": "시설부", "김남욱GM": "GM"}
STALE_DAYS = 30          # 이 일수를 넘겨 손이 안 닿으면 '잠시 쉬는 중'
e = html_mod.escape


def g(x, k):
    return str(x.get(k, "") or "").strip()


def is_exec(x):
    return any(n in g(x, "담당자") for n in EXEC_OWNERS)


def dept_of(owner):
    for k, v in DEPT_OF.items():
        if k in owner:
            return v
    return "공동"


def fetch_todo():
    with urllib.request.urlopen(TODO_URL, timeout=120) as r:
        return json.loads(r.read()).get("data", [])


def collect(today: datetime.date):
    rows = fetch_todo()
    mon = today.strftime("%Y-%m")
    prev = (today.replace(day=1) - datetime.timedelta(days=1)).strftime("%Y-%m")
    now = datetime.datetime(today.year, today.month, today.day)

    def days(x):
        v = g(x, "수정일") or g(x, "생성일")
        try:
            return (now - datetime.datetime.strptime(v[:10], "%Y-%m-%d")).days
        except Exception:
            return 0

    def miss(x):
        m = []
        if not g(x, "시작일"):
            m.append("시작일")
        if not g(x, "종료일"):
            m.append("종료일")
        return m

    all_act = [x for x in rows if g(x, "상태") in ("진행중", "보류")]
    act = [x for x in all_act if not is_exec(x)]
    done = [x for x in rows if g(x, "상태") == "완료" and not is_exec(x)]
    cur = [x for x in done if g(x, "완료일")[:7] == mon]
    byday = collections.Counter(g(x, "완료일")[:10] for x in cur)
    best = byday.most_common(1)[0] if byday else ("", 0)

    items = [{"id": g(x, "id"), "o": g(x, "담당자"), "t": g(x, "업무명"),
              "c": g(x, "카테고리"), "s": g(x, "상태"), "miss": miss(x), "d": days(x)}
             for x in act]

    plan = json.load(open(PLAN, encoding="utf-8"))
    objs = plan.get("months", {}).get(mon, {}).get("objectives", []) or []
    unlinked = []
    for o in objs:
        s = o.get("sync") or {}
        if not s.get("source") or s.get("source") == "manual":
            pg = o.get("progress")
            unlinked.append({"t": o.get("title"), "dept": o.get("dept"),
                             "pg": (pg if isinstance(pg, int) else "—")})

    stats = {
        "date": today.strftime("%Y-%m-%d"), "month": mon,
        "act": len(act), "excluded": len(all_act) - len(act),
        "done_month": len(cur), "done_today": byday.get(today.strftime("%Y-%m-%d"), 0),
        "done_prev": sum(1 for x in done if g(x, "완료일")[:7] == prev),
        "new_month": sum(1 for x in rows if g(x, "생성일")[:7] == mon and not is_exec(x)),
        "appr_month": sum(1 for x in rows if g(x, "결재상태") == "결재완료"
                          and g(x, "결재완료시각")[:7] == mon and not is_exec(x)),
        "best_day": best[0], "best_n": best[1],
        "complete": sum(1 for i in items if not i["miss"]),
        "need_sched": sum(1 for i in items if "종료일" in i["miss"]),
        # ★2026-08-21 GM 확정 — 난이도(중요도)는 업무 SSOT 에서 뺐다. 실무자가 고민할 칸이 아니고,
        #   업무 점수는 분기별로 CHRO 가 정해진 기준으로 매긴다. 지표도 함께 내린다.
        "need_score": 0,
        "rest": sum(1 for i in items if i["d"] >= STALE_DAYS),
        "unlinked": len(unlinked),
    }
    return stats, items, unlinked


def build_html(S, items, unlinked):
    rest = [x for x in items if x["d"] >= STALE_DAYS]
    own = {}
    for x in items:
        o = x["o"] or "(미지정)"
        own.setdefault(o, []).append(x)
    order = sorted(own, key=lambda k: -len(own[k]))

    cards = []
    for who in order:
        lst = own[who]
        done_n = sum(1 for x in lst if not x["miss"])
        pct = round(done_n / len(lst) * 100) if lst else 0
        tone = "full" if pct == 100 else ("high" if pct >= 60 else ("mid" if pct >= 30 else "low"))
        need = sum(len(x["miss"]) for x in lst)
        rows = "".join(
            f'<li><span class="tn">{e(x["t"][:40])}</span>'
            + "".join(f'<span class="tag dt">마감일</span>'
                      for m in x["miss"] if m != "시작일")
            + (f'<span class="tag rest">{x["d"]}일째 쉬는 중</span>' if x["d"] >= STALE_DAYS else "")
            + "</li>"
            for x in sorted(lst, key=lambda y: (-len(y["miss"]), -y["d"]))
            if x["miss"] or x["d"] >= STALE_DAYS)
        msg = "빈칸 없이 완벽합니다 👏" if need == 0 else f"<b>{need}칸</b>만 채우면 완성이에요"
        cards.append(
            f'<section class="owner"><header class="owner-h">'
            f'<h3>{e(who if len(who) < 20 else who[:18] + "…")}</h3>'
            f'<span class="meta">{e(dept_of(who))}</span>'
            f'<span class="count">{len(lst)}건 진행 중</span></header>'
            f'<div class="prog"><div class="bar"><span class="fill {tone}" style="width:{pct}%"></span></div>'
            f'<span class="pct {tone}">{pct}%</span><span class="msg">{msg}</span></div>'
            f'<ul class="list">{rows or "<li class=ok>채울 것도, 쉬는 것도 없습니다 — 그대로 쭉 가시면 됩니다 ✨</li>"}</ul>'
            f'</section>')

    unlink_rows = "".join(
        f'<li><span class="dept">{e(x["dept"] or "-")}</span>'
        f'<span class="tn">{e(x["t"])}</span>'
        f'<span class="tag plan">계획엔 {x["pg"]}</span></li>' for x in unlinked)
    rest_rows = "".join(
        f'<li><span class="dd">{x["d"]}</span><span class="own">{e(x["o"][:12])}</span>'
        f'<span class="tn">{e(x["t"][:44])}</span></li>'
        for x in sorted(rest, key=lambda y: -y["d"]))

    # 이 보드는 매주 월요일 10:00 스냅샷이다 — 화면을 여는 날과 실측일이 다르다.
    # 그래서 '오늘'이라 부르지 않는다(2026-08-26 실사: 8/26 에 열었는데 '오늘 · 08월 24일'로 떠 있었다).
    hint = "이 날 입항 없음 🚢" if S["done_today"] == 0 else "이 날 입항 있었습니다 🎉"
    best = S["best_day"][5:].replace("-", "/") if S["best_day"] else "-"
    mm = int(S["month"].split("-")[1])
    dd = S["date"][5:].replace("-", "월 ") + "일"

    return f"""<title>[운영] 업무판 채움 보드 · {S['date']} 기준</title>
<!-- 카카오톡·메신저 링크 미리보기용(2026-08-03 GM 지적) — 이 태그가 없으면 카카오가 처음 긁어간
     화면을 캐시로 계속 보여준다. 제목·설명에 기준일을 박아, 방에 뜬 카드만 봐도 언제 것인지 안다. -->
<meta property="og:title" content="업무판 채움 보드 · {S['date']} 기준">
<meta property="og:description" content="오래 멈춘 일 {S['rest']}건 · 마감일 {S['need_sched']}건 — 진행 중 {S['act']}건 기준">
<meta property="og:type" content="website">
<style>{CSS}</style>
<div class="wrap">
<header>
  <div class="eyebrow">운영 · 시우 (AI COO)</div>
  <h1>업무판 채움 보드</h1>
  <div class="stamp">실측 {S['date']} 기준 · 매주 월요일 10:00 자동 재실측(1회성 스냅샷 아님) ·
    업무 현황 SSOT + {mm}월 운영계획 · 실무진 {S['act']}건
    (경영진 {S['excluded']}건은 월간 운영계획에서 따로 관리)</div>
</header>

<div class="cta">
  <span class="lbl"><b>고칠 곳은 업무판입니다.</b> 본인 업무를 열어 마감일·점수를 넣거나, 멈춘 일은 「보류」에 이유 한 줄.</span>
  <a href="{LINK_TODO}">📋 업무판 열기</a>
  <a class="ghost" href="{LINK_RULE}">📖 적는 기준</a>
</div>

<div class="period">
  <div class="p-card today"><span class="k">실측일 · {dd}</span>
    <span class="v">{S['done_today']}</span><span class="n">건 끝냄</span>
    <span class="hint">{hint}</span></div>
  <div class="p-card"><span class="k">{mm}월 누적</span>
    <span class="v good">{S['done_month']}</span><span class="n">건 끝냄</span>
    <span class="hint">새로 올린 일 {S['new_month']}건 · 결재 완료 {S['appr_month']}건 · 지난달 {S['done_prev']}건</span></div>
  <div class="p-card"><span class="k">지금 진행 중</span>
    <span class="v">{S['act']}</span><span class="n">건</span>
    <span class="hint">빈칸 없이 완비 {S['complete']}건</span></div>
</div>

<section>
  <div class="sec-h"><span class="num">1</span><h2>오래 멈춘 일</h2>
    <span class="sub">{S['rest']}건 · 숫자는 마지막으로 손댄 뒤 지난 날 — 끝났으면 「완료」, 기다리는 중이면 「보류」에 이유 한 줄</span></div>
  <details open><summary class="fold">{S['rest']}건 보기</summary>
  <div class="panel"><ul>{rest_rows}</ul></div></details>
</section>

<section>
  <div class="sec-h"><span class="num">2</span><h2>마감일·점수가 빈 일</h2>
    <span class="sub">마감일 {S['need_sched']}건 — 업무 점수는 분기별로 인사(CHRO)에서 매깁니다. 담당자가 정하지 않습니다</span></div>
  <details><summary class="fold">담당자별로 보기</summary>
  <div class="grid">{''.join(cards)}</div></details>
</section>

<section>
  <div class="sec-h"><span class="num">3</span><h2>업무판에 아직 없는 일</h2>
    <span class="sub">{mm}월 운영계획에는 있는데 업무판에서는 안 보이는 {S['unlinked']}건 — 올려두면 진척이 자동 반영됩니다</span></div>
  <details><summary class="fold">{S['unlinked']}건 보기</summary>
  <div class="panel"><ul>{unlink_rows}</ul></div></details>
</section>

<footer>실행할 때마다 업무판을 다시 세어 만듭니다 — <code>scripts/ops_fill_board.py</code></footer>
</div>
"""


CSS = """
summary.fold{cursor:pointer;font-size:12.5px;font-weight:700;color:var(--accent);margin:6px 0 8px;list-style:none}
summary.fold::before{content:"▸ "}
details[open]>summary.fold::before{content:"▾ "}

:root{--ground:#F5F7F8;--surface:#FFFFFF;--surface-2:#FAFBFC;--ink:#171B1F;--ink-soft:#5A656D;
  --ink-faint:#8B959C;--line:#DDE2E5;--line-soft:#EAEEF0;--accent:#8A6A21;
  --good:#2F7A63;--mid:#AC7524;--low:#A6603A;--cool:#3A6B96}
@media (prefers-color-scheme:dark){:root{--ground:#131619;--surface:#1A1E22;--surface-2:#1E2328;
  --ink:#E6E9EA;--ink-soft:#98A3AA;--ink-faint:#6E7982;--line:#292F35;--line-soft:#232930;
  --accent:#C7A353;--good:#5CB39A;--mid:#CFA055;--low:#D08A62;--cool:#7FAFD6}}
:root[data-theme="dark"]{--ground:#131619;--surface:#1A1E22;--surface-2:#1E2328;--ink:#E6E9EA;
  --ink-soft:#98A3AA;--ink-faint:#6E7982;--line:#292F35;--line-soft:#232930;--accent:#C7A353;
  --good:#5CB39A;--mid:#CFA055;--low:#D08A62;--cool:#7FAFD6}
:root[data-theme="light"]{--ground:#F5F7F8;--surface:#FFFFFF;--surface-2:#FAFBFC;--ink:#171B1F;
  --ink-soft:#5A656D;--ink-faint:#8B959C;--line:#DDE2E5;--line-soft:#EAEEF0;--accent:#8A6A21;
  --good:#2F7A63;--mid:#AC7524;--low:#A6603A;--cool:#3A6B96}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font-size:15px;line-height:1.55;
  word-break:keep-all;font-family:-apple-system,"Segoe UI Variable Text","Segoe UI","Malgun Gothic",sans-serif}
.wrap{padding:36px 40px 72px;display:flex;flex-direction:column;gap:32px}
.eyebrow{font-size:11.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);font-weight:700}
h1{font-family:"Iowan Old Style","Palatino Linotype",Palatino,"Malgun Gothic",serif;
  font-size:clamp(26px,3vw,38px);line-height:1.22;margin:6px 0 0;font-weight:600;text-wrap:balance}
.lede{margin:10px 0 0;color:var(--ink-soft);max-width:64ch}
.stamp{margin-top:12px;font-size:12.5px;color:var(--ink-faint);
  font-family:ui-monospace,"Cascadia Mono",Consolas,monospace}
.cta{display:flex;flex-wrap:wrap;gap:10px;align-items:center;background:var(--surface);
  border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:3px;padding:14px 18px}
.cta .lbl{font-size:13.5px;color:var(--ink-soft);flex:1;min-width:220px}
.cta .lbl b{color:var(--ink)}
.cta a{display:inline-flex;align-items:center;gap:6px;padding:10px 16px;border-radius:3px;
  font-size:13.5px;font-weight:700;text-decoration:none;white-space:nowrap;
  background:var(--accent);color:var(--surface)}
.cta a.ghost{background:transparent;color:var(--accent);border:1px solid var(--accent)}
.cta a:hover{opacity:.9}
.period{display:grid;grid-template-columns:repeat(auto-fit,minmax(178px,1fr));gap:12px}
.p-card{background:var(--surface);border:1px solid var(--line);border-radius:3px;padding:14px 16px;
  display:grid;grid-template-columns:auto auto;gap:0 7px;align-items:baseline}
.p-card.today{border-left:3px solid var(--accent)}
.p-card .k{grid-column:1/-1;font-size:11px;letter-spacing:.09em;color:var(--ink-faint);font-weight:700;margin-bottom:4px}
.p-card .v{font-family:"Iowan Old Style",Palatino,serif;font-size:32px;line-height:1;font-variant-numeric:tabular-nums}
.p-card .v.good{color:var(--good)}
.p-card .n{font-size:12.5px;color:var(--ink-soft)}
.p-card .hint{grid-column:1/-1;font-size:11.5px;color:var(--ink-faint);margin-top:7px;line-height:1.45}
h2{font-size:17px;margin:0;font-weight:700}
.sec-h{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;border-bottom:2px solid var(--ink);
  padding-bottom:9px;margin-bottom:16px}
.sec-h .num{font-family:"Iowan Old Style",Palatino,serif;font-size:15px;color:var(--accent);font-weight:700}
.sec-h .sub{font-size:13px;color:var(--ink-soft)}
.ask{margin:0 0 16px;padding:12px 15px;background:var(--surface-2);border-left:3px solid var(--accent);
  font-size:13.5px;color:var(--ink-soft);max-width:74ch}
.ask b{color:var(--ink)}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:3px;overflow:hidden}
.panel ul{list-style:none;margin:0;padding:0}
.panel li{display:flex;align-items:baseline;gap:11px;padding:9px 16px;border-bottom:1px solid var(--line-soft)}
.panel li:last-child{border-bottom:0}
.dept{font-size:11px;color:var(--ink-faint);min-width:8ch;white-space:nowrap}
.own{font-size:11.5px;color:var(--ink-faint);min-width:8ch;white-space:nowrap}
.tn{flex:1;font-size:13.5px}
.dd{font-family:"Iowan Old Style",Palatino,serif;font-size:18px;min-width:2.6ch;text-align:right;
  font-variant-numeric:tabular-nums;color:var(--cool);font-weight:600}
.dd::after{content:"일";font-size:10px;margin-left:1px;opacity:.6}
.tag{font-size:10.5px;font-weight:700;padding:2px 7px;border-radius:2px;white-space:nowrap}
.tag.dt{color:var(--cool);background:color-mix(in srgb,var(--cool) 13%,transparent)}
.tag.sc{color:var(--mid);background:color-mix(in srgb,var(--mid) 15%,transparent)}
.tag.rest{color:var(--low);background:color-mix(in srgb,var(--low) 13%,transparent)}
.tag.plan{color:var(--good);background:color-mix(in srgb,var(--good) 13%,transparent)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:16px}
.owner{background:var(--surface);border:1px solid var(--line);border-radius:3px;overflow:hidden}
.owner-h{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--line-soft);flex-wrap:wrap}
.owner-h h3{margin:0;font-size:14.5px;font-weight:700}
.owner-h .meta{font-size:11.5px;color:var(--ink-faint)}
.owner-h .count{margin-left:auto;font-size:12px;color:var(--ink-soft);font-variant-numeric:tabular-nums}
.prog{display:flex;align-items:center;gap:10px;padding:11px 16px;background:var(--surface-2);
  border-bottom:1px solid var(--line-soft);flex-wrap:wrap}
.bar{flex:1;min-width:110px;height:7px;background:var(--line);border-radius:99px;overflow:hidden}
.fill{display:block;height:100%;border-radius:99px}
.fill.full,.fill.high{background:var(--good)} .pct.full,.pct.high{color:var(--good)}
.fill.mid{background:var(--mid)} .pct.mid{color:var(--mid)}
.fill.low{background:var(--low)} .pct.low{color:var(--low)}
.pct{font-size:12.5px;font-weight:700;font-variant-numeric:tabular-nums;min-width:4ch;text-align:right}
.prog .msg{font-size:12.5px;color:var(--ink-soft);width:100%}
.prog .msg b{color:var(--ink)}
.owner .list{list-style:none;margin:0;padding:0}
.owner .list li{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;padding:8px 16px;
  border-bottom:1px solid var(--line-soft);font-size:13px}
.owner .list li:last-child{border-bottom:0}
.owner .list li.ok{color:var(--good);font-weight:600}
code{font-family:ui-monospace,"Cascadia Mono",Consolas,monospace;font-size:12px;
  background:var(--surface-2);padding:1px 5px;border-radius:2px}
footer{font-size:12.5px;color:var(--ink-faint);border-top:1px solid var(--line);padding-top:16px}
@media (max-width:640px){.wrap{padding:24px 18px 56px}.grid{grid-template-columns:1fr}.dept,.own{display:none}}
@media print{body{background:#fff;font-size:11pt}.wrap{padding:0;gap:20px}
  .grid{grid-template-columns:1fr 1fr}.owner,.panel{break-inside:avoid}.cta{display:none}}
"""


def make_card(png_path: str) -> bool:
    """보드 상단(제목+기간 카드)을 잘라 카톡용 카드 이미지로 만든다. 실패해도 보드 생성은 유효."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as ex:
        print(f"[WARN] playwright 없음 — 카드 생략: {ex}")
        return False
    src = "file:///" + OUTS[0].replace("\\", "/").replace(" ", "%20")
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_context(viewport={"width": 1200, "height": 1000},
                               device_scale_factor=2).new_page()
            pg.goto(src, wait_until="load", timeout=60000)
            pg.wait_for_timeout(1500)
            h = pg.evaluate("(function(){var s=document.querySelector('.period');"
                            "var r=s.getBoundingClientRect();"
                            "return Math.ceil(r.bottom+window.scrollY+20)})()")
            pg.set_viewport_size({"width": 1200, "height": int(h)})
            pg.wait_for_timeout(500)
            pg.screenshot(path=png_path, clip={"x": 0, "y": 0, "width": 1200, "height": h})
            b.close()
        return os.path.exists(png_path)
    except Exception as ex:
        print(f"[WARN] 카드 생성 실패 — 발송 생략: {type(ex).__name__}: {ex}")
        return False


def build_caption(S) -> str:
    """카톡 본문. 질책 어휘 없이 '이번 주에 이것만' 톤. 링크는 실무진이 열 수 있는 공개 주소."""
    # 2026-08-03 GM 지적 — 본문에 기준일이 없어서, 방에 뜬 링크 미리보기(카카오가 처음 긁어간 화면을
    #   캐시로 계속 보여준다)를 보고 "내용이 7월 것 아니냐"는 의심이 생겼다. 두 가지로 막는다:
    #   ①첫 줄에 기준일을 박는다 ②링크 끝에 날짜를 붙여 매주 다른 주소가 되게 한다(캐시가 갱신된다).
    # 2026-08-03 GM 지적 — "7월건을 정리해도 모자랄 판에 칸 채우기부터 시키느냐". 순서를 뒤집어
    #   **오래 멈춘 것 먼저**, 칸 채우기는 그다음에 말한다.
    # 2026-08-03 GM 지적(2차) — "빈 줄이 많아 세로 스크롤이 길다, 한눈에 이해되게 정리해라".
    #   빈 줄을 2개로 줄이고, 할 일을 ①②로 번호 매겨 무엇을 하라는 건지가 한 번에 읽히게 다시 썼다.
    d = S["date"]
    return (
        f"[웰페리온 운영] 업무판 채움 보드 · {d} 기준\n"
        "AI COO 시우입니다. 이번 주에 손볼 것만 추렸습니다.\n"
        f"── 진행 중 {S['act']}건 · 이 중 {S['complete']}건은 빈칸 없이 완비 ──\n"
        f"① 오래 멈춘 일 {S['rest']}건 (30일 넘게 손 못 댄 것)\n"
        "  → 끝났으면 「완료」로, 기다리는 중이면 「보류」에 이유 한 줄. 때가 되면 자동으로 다시 올라옵니다.\n"
        f"② 칸이 빈 일 — 마감일 {S['need_sched']}건\n"
        "  → 마감일이 있어야 도와드릴 시점을 알 수 있습니다. 업무 점수는 분기별로 인사(CHRO)에서 매깁니다.\n"
        "\n"
        "본인 것만 골라 보기 ↓\n"
        "https://wellperion-cao.github.io/wellperion-automation/coo/todo/"
        "%EC%97%85%EB%AC%B4%ED%8C%90%20%EC%B1%84%EC%9B%80%20%EB%B3%B4%EB%93%9C.html"
        f"?d={d.replace('-', '')}"
    )


def send_kakao(S) -> None:
    """카톡 ★운영부 방 1개에만 발송. 회장님·관리부 방 오발송 방지를 위해 --only-room 고정.

    ★빈칸이 하나도 없으면 보내지 않는다 — 채울 게 없는데 매주 보내면 잔소리가 된다.
    """
    import subprocess
    need = S["need_sched"] + S["rest"] + S["unlinked"]
    if need == 0:
        print("[발송 생략] 채울 빈칸·쉬는 건이 0 — 보낼 이유가 없습니다(잔소리 방지).")
        return
    png = os.path.join(BASE, "status", "boards", "ops_fill_board_card.png")
    if not make_card(png):
        return
    cmd = [sys.executable, os.path.join(BASE, "scripts", "kakao_report_sender.py"),
           # 방 이름은 등록부(scripts/kakao_rooms.json) 표기 그대로 — 공백 없는 '★운영부'.
           # 발신은 공백 무시 대조라 어느 쪽이든 나가지만, 발신 로그에 넘긴 문자열이 그대로 남아
           # 자율현황 「알림 한 장」이 '★ 운영부'와 '★운영부'를 다른 방 둘로 세고 있었다
           # (2026-08-08 GM 검수 지시로 발견). 기능 무변경 · 표기만 통일.
           "--image", png, "--caption", build_caption(S), "--only-room", "★운영부",
           # --sender 업무판채움보드 — kakao_report_sender 사람 방 발신 가드(배 11070 ⑤) 통과용.
           "--sender", "업무판채움보드"]
    print("[발송] 카톡 ★운영부 —", need, "건 남음")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = (r.stdout or "").strip().splitlines()[-3:]
    for t in tail:
        print("   ", t)
    if r.returncode != 0:
        print("[WARN] 카톡 발송 실패(코드 %s) — 보드는 정상 생성됨. GM PC 잠금·카톡 로그인 확인 필요."
              % r.returncode)


def main():
    ap = argparse.ArgumentParser(description="실무진 업무판 채움 보드 생성기")
    ap.add_argument("--json", action="store_true", help="수치만 JSON 출력(파일도 생성)")
    ap.add_argument("--date", help="기준일 YYYY-MM-DD (기본=오늘)")
    ap.add_argument("--send", action="store_true",
                    help="카톡 ★운영부 방에 카드+안내 발송(빈칸 0이면 자동 생략)")
    # 커밋을 여기로 들여온 이유(2026-07-27 시우): 예약 배치(.bat)가 git commit 을 직접 부르면서
    #   한글 경로·한글 메시지를 담고 있었는데, .bat 이 LF 줄바꿈이라 cmd 가 그 줄을 토막 내
    #   배치 전체가 깨졌다(그래도 작업 결과는 0=성공으로 찍혀 아무도 몰랐다). 한글은 파이썬이
    #   다루는 게 안전하므로 .bat 은 영문만 남기고 커밋은 이 관문으로 옮긴다.
    #   커밋 자체도 raw git 이 아니라 safe_commit 을 경유한다(공용 작업트리 규칙).
    ap.add_argument("--commit", action="store_true",
                    help="생성된 보드 파일을 safe_commit 경유로 커밋(예약 배치용)")
    a = ap.parse_args()
    today = (datetime.datetime.strptime(a.date, "%Y-%m-%d").date() if a.date
             else datetime.date.today())

    S, items, unlinked = collect(today)
    html = build_html(S, items, unlinked)
    for out in OUTS:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)

    # 작업 현황 로그(best-effort) — 실행 1회당 보드 생성 요약 1줄
    worklog_log(
        "coo", "업무판",
        f"업무판 채움 보드 갱신 — 진행 {S['act']}건 · 완비 {S['complete']}건 · "
        f"미등록 {S['unlinked']}건 · 쉬는중 {S['rest']}건",
        result="ok",
        detail=f"마감일 미기재 {S['need_sched']}건",
        ref=S["date"],
    )

    # 살아있음 신호(2026-07-25 시우 · 아침 자가점검 발견 배10185).
    # ★왜 필요했나: 침묵 감지기가 이 모듈의 신선도를 판정할 자기 산출물이 없어
    #   '디렉터리 status 내 최신파일 mtime' 폴백으로 판정하고 있었다. status 폴더는 다른
    #   모듈이 수분마다 쓰므로 영구히 "0.0h 전" = 이 모듈이 몇 주 멈춰도 계속 ok 로 떴다
    #   (주간 카톡 ★운영부 발신 모듈이라 멈춰도 아무도 모르는 상태).
    # ★새 파일·새 관례를 만들지 않는다(약속 L21) — 등록부 전 모듈이 이미 쓰는
    #   scripts/module_heartbeat.py 관문에 그대로 합류한다.
    try:
        from module_heartbeat import record_heartbeat  # noqa: PLC0415
        record_heartbeat(
            "coo-ops-fill-board",
            f"채움 보드 갱신 — 진행 {S['act']}·미등록 {S['unlinked']}·쉬는중 {S['rest']}",
            extra={"date": S["date"]},
        )
    except Exception as exc:  # fail-soft — 하트비트 실패가 보드 생성을 막지 않음
        print(f"[WARN] 하트비트 기록 건너뜀: {type(exc).__name__}: {exc}")

    if a.json:
        print(json.dumps(S, ensure_ascii=False))
        return
    for out in OUTS:
        print("생성:", out)
    print(f"진행 {S['act']} · 완비 {S['complete']} · 미등록 {S['unlinked']} · "
          f"쉬는중 {S['rest']} · 마감일 {S['need_sched']} "
          f"· 제외(경영진) {S['excluded']}")
    if a.commit:
        import subprocess  # noqa: PLC0415
        # 하트비트도 같이 담는다(2026-07-28 시우 · 아침 자가점검 발견).
        #   07-27 10:00 예약분은 보드 생성·커밋·카톡 발송까지 전부 성공했는데, 방금 쓴
        #   하트비트만 커밋 목록에 없어 미커밋으로 남았다 → 공용 작업트리를 쓰는 다른 세션의
        #   git 복원에 그날 22:26 통째로 되돌아갔고, 침묵 감지기는 이 모듈을 3일째
        #   멈춘 것으로 읽었다(실제론 정상 가동). 살아있음 신호가 커밋되지 않으면
        #   그 신호는 없는 것과 같다.
        cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                            "safe_commit.py"),
               "-m", "chore(coo): 주간 채움 보드 갱신 (ops_fill_board)", "--"] + list(OUTS) + [
               os.path.join("status", "heartbeats", "coo-ops-fill-board.json")]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=300)
            print((r.stdout or "").strip() or (r.stderr or "").strip())
        except Exception as exc:   # 커밋 실패가 보드 생성을 무효로 만들지는 않는다
            print(f"[WARN] 커밋 건너뜀: {type(exc).__name__}: {exc}")

    if a.send:
        send_kakao(S)


if __name__ == "__main__":
    main()
