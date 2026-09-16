# -*- coding: utf-8 -*-
"""meeting_brief_a3.py — 회의 요약 A3 한 장(「지난 보고 이후 달라진 것」) 자동 생성 (배 2705).

틀 = coo/chairman/260916_회장님회의_요약_A3.html(손 판 · GM 2026-09-16 「이런식으로 GM업무 + 중간관리자
업무 + 전사일정 + 업무&결재SSOT 연동을 원했던거야」). CSS·3열 구성은 손 판 그대로, 내용만 네 원천에서 읽는다.

원천 4 (읽기만 · 어느 원천도 고치지 않는다)
  ① GM업무 카드      status/monthly_ops_plan.json  months[*].objectives
  ② 중간관리자 원장  1. AI자료_아카이브/11_카카오톡/★중간관리자/_digest_ledger.json  (같은 no 는 마지막 날짜가 최신)
  ③ 전사일정         status/schedule_ssot.json  items[] (name·next_due·assignee·plan_id)
  ④ 업무&결재 SSOT   GAS todo_list (gmkey 포함 — GM 행은 이 키 없이는 안 나온다)

규칙 = 추정 문장 없음 · 원천에 없는 값은 「미정」 · 「여쭙」류 금지(「말씀 나누실」) · 넘침 0(--check 로 실측).

쓰는 법
  .venv/Scripts/python.exe scripts/meeting_brief_a3.py [--since 2026-09-09] [--out 경로] [--check] [--open]
    --since  기준일(기본 = 7일 전) · --check  헤드리스로 scrollHeight 실측 + png 저장 · 넘치면 글자 단계 축소 재렌더
    --open   scripts/open_primary.ps1 로 GM 주 모니터에 띄움(기본 안 함)

# ponytail: 글자 축소는 li·td 한 변수(--fs) 단계 5개 — 그래도 넘치면 마지막 단계 값과 넘침을 그대로 찍고 rc=2.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
GUIDE = os.path.join(ROOT, "3. 웰페리온 가이드")
PLAN = os.path.join(ROOT, "status", "monthly_ops_plan.json")
LEDGER = os.path.join(ROOT, "1. AI자료_아카이브", "11_카카오톡", "★중간관리자", "_digest_ledger.json")
SCHED = os.path.join(ROOT, "status", "schedule_ssot.json")
OUT = os.path.join(GUIDE, "coo", "chairman", "회의요약_A3.html")
PAGE_H = 1123
FS_STEPS = [12.4, 12, 11.5, 11, 10.5]
DATE_RE = re.compile(r"(20\d\d)-(\d\d)-(\d\d)")
SHORT_RE = re.compile(r"~?\s*(\d{1,2})/(\d{1,2})")
STRIP_TAGS = re.compile(r"\[(회장님|대표님) (지시|보고)\]|\((GM 직접|대표님 지시|대표님 보고)\)|\[병합\]|\[GM업무\]|\[결재\]")
TAG_CHAIRMAN = re.compile(r"회장님 지시")
TAG_CEO = re.compile(r"대표님 (지시|보고)")


def esc(s) -> str:
    return html.escape(str(s or ""), quote=False)


def nim(name: str) -> str:
    """직함 뒤 「님」(GM 09-16). 데이터 값(담당자 칸)을 보여 줄 때만 보정한다."""
    return re.sub(r"(실장|소장|원장|팀장|고문|대표|회장|프로|사원|주임)(?!님)(?=[\s·,]|$)", r"\1님", name or "")


def cut(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", (s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def short_title(t: str) -> str:
    t = STRIP_TAGS.sub("", t or "").strip(" ·—-")
    return cut(t.split(" — ")[0].split("(")[0], 22)


def md(d: dt.date) -> str:
    return f"{d.month}/{d.day}"


def parse_date(s) -> dt.date | None:
    for m in DATE_RE.finditer(str(s or "")):  # 카드 id(2026-08-57)처럼 날짜 꼴이지만 날짜가 아닌 것은 건너뛴다
        try:
            return dt.date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            continue
    return None


def emph(s: str) -> str:
    """「미정」·「대기」를 굵게 — 손 판이 그렇게 강조했다."""
    return re.sub(r"(\(?미정\)?|GM 결정 대기|결정 대기)", r"<b>\1</b>", esc(s))


# ── ① GM업무 카드 ───────────────────────────────────────────────
def load_cards() -> list[dict]:
    p = json.load(open(PLAN, encoding="utf-8"))
    cards = []
    for mk, m in sorted(p["months"].items()):
        for o in m.get("objectives") or []:
            o = dict(o)
            o["_month"] = mk
            o["_lines"] = note_lines(o.get("progress_note") or "")
            cards.append(o)
    return cards


def note_lines(note: str) -> list[tuple[dt.date | None, str]]:
    """progress_note 줄 → (그 줄의 날짜, 본문). 날짜는 [YYYY-MM-DD]·▶[… YYYY-MM-DD] 어디에 있어도 잡는다."""
    out = []
    for ln in note.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith(("■", "▸ 경위", "(아래는 기록")):
            continue
        out.append((parse_date(ln), ln))
    return out


def clean_line(ln: str) -> str:
    ln = re.sub(r"^[▶▸·□☑✅\-\s]*(\[[^\]]*\])?\s*", "", ln)
    ln = re.sub(r"\*\*", "", ln)
    return ln.strip(" —·")


def latest_line(card: dict, today: dt.date) -> tuple[dt.date | None, str]:
    dated = [(d, l) for d, l in card["_lines"] if d and d <= today]
    if dated:
        d, l = max(dated, key=lambda x: x[0])
        return d, clean_line(l)
    if card["_lines"]:
        return None, clean_line(card["_lines"][0][1])
    return None, card.get("target") or "미정"


def card_done_at(card: dict, today: dt.date) -> dt.date | None:
    if card.get("status") != "완료":
        return None
    ds = [d for d, _ in card["_lines"] if d and d <= today]
    return max(ds) if ds else parse_date(card.get("due"))


def next_check(card: dict, today: dt.date) -> tuple[dt.date | None, str]:
    """가장 가까운 □ 체크 — (~9/10)·YYYY-MM-DD 어느 쪽이든 날짜가 있는 첫 미체크 줄."""
    best = None
    for _, ln in card["_lines"]:
        if not ln.lstrip("▶▸ ").startswith("□"):
            continue
        d = parse_date(ln)
        if not d:
            m = SHORT_RE.search(ln.split("—")[0]) or SHORT_RE.search(ln)
            if m:
                yr = today.year + (1 if int(m[1]) < today.month - 6 else 0)
                try:
                    d = dt.date(yr, int(m[1]), int(m[2]))
                except ValueError:
                    d = None
        if d and d >= today - dt.timedelta(days=1) and (best is None or d < best[0]):
            txt = re.sub(r"^\(?~?\d{1,2}/\d{1,2}\)?(\([월화수목금토일]\))?\s*(까지)?\s*", "", clean_line(ln))
            best = (d, cut(re.sub(r"\s*\(~?\d{1,2}/\d{1,2}\)\s*$", "", txt), 16))
    return best or (None, "")


def is_gm_direct(c: dict) -> bool:
    return "(GM 직접)" in (c.get("title") or "") or "김남욱" in (c.get("owner") or "")


# ── ② 중간관리자 원장 ─────────────────────────────────────────────
def load_ledger() -> dict[int, tuple[str, dict]]:
    last: dict[int, tuple[str, dict]] = {}
    for day in json.load(open(LEDGER, encoding="utf-8")):
        for it in day.get("issues") or []:
            if it.get("no") is not None:
                last[int(it["no"])] = (day["date"], it)
    return last


# ── ③ 전사일정 ────────────────────────────────────────────────
def load_schedule() -> list[dict]:
    items = json.load(open(SCHED, encoding="utf-8"))["items"]
    return [x for x in items if x.get("next_due") and x.get("applies") != "해당없음"]


# ── ④ 업무&결재 SSOT ──────────────────────────────────────────────
def load_todos(log) -> list[dict] | None:
    try:
        from collectors.ops_shared import gas_get, SSOT_API_URL
        from gm_handoff import GM_KEY
    except Exception as e:  # noqa: BLE001
        log(f"todo_list import 실패: {e}")
        return None
    r = gas_get(SSOT_API_URL, params={"action": "todo_list", "include_gm": "1", "gmkey": GM_KEY},
                label="업무SSOT", log_fn=log)
    if r is None:
        return None
    try:
        return r.json().get("data") or []
    except Exception as e:  # noqa: BLE001
        log(f"todo_list 응답 파싱 실패: {e}")
        return None


def tdate(s) -> dt.date | None:
    return parse_date((s or "")[:10])


# ── 조립 ─────────────────────────────────────────────────────────
def pill(d: dt.date | None, today: dt.date, text: str = "") -> str:
    if d is None:
        return f'<span class="pill">{esc(text or "미정")}</span>'
    cls = " r" if d < today else (" y" if d <= today + dt.timedelta(days=7) else "")
    label = f"{md(d)} {text}".strip() if text else md(d)
    return f'<span class="pill{cls}">{esc(cut(label, 22))}</span>'


def build(since: dt.date, today: dt.date, now: dt.datetime, log) -> tuple[str, dict]:
    cards = load_cards()
    ledger = load_ledger()
    sched = load_schedule()
    todos = load_todos(log)
    soon = today + dt.timedelta(days=14)
    counts: dict[str, int] = {}

    # 이번 달 카드 + 지난 달 카드 중 기준일 이후 기록이 있는 것(= 「지난 보고 이후 달라진 것」)
    ym = today.strftime("%Y-%m")
    active = [c for c in cards if c.get("status") in ("진행", "계획")
              and (c["_month"] == ym or ((latest_line(c, today)[0] or dt.date.min) >= since))]
    sched_by_plan = {}
    for x in sched:
        if x.get("plan_id"):
            sched_by_plan.setdefault(x["plan_id"], []).append(x)

    def card_next(c) -> tuple[dt.date | None, str]:
        d, txt = next_check(c, today)
        if d:
            return d, txt
        ev = sorted((x for x in sched_by_plan.get(c["id"], []) if parse_date(x["next_due"]) >= today),
                    key=lambda x: x["next_due"])
        if ev:
            return parse_date(ev[0]["next_due"]), cut(ev[0]["name"], 16)
        return parse_date(c.get("due")), "기한"

    # 1열 — 👑 회장님 지시
    chair = [c for c in active if TAG_CHAIRMAN.search(c.get("title") or "")]
    chair_li = []
    for c in chair:
        d, ln = latest_line(c, today)
        chair_li.append(f'<li><span class="k">{esc(short_title(c["title"]))}</span> {emph(cut(ln, 150))}'
                        + (f' <span class="pill">{md(d)}</span>' if d else "") + "</li>")
    counts["회장님 지시"] = len(chair)

    # 1열 — 📅 기준일 이후 마친 일
    done_li = []
    done_cards = [(card_done_at(c, today), c) for c in cards]
    done_cards = sorted(((d, c) for d, c in done_cards if d and d >= since), key=lambda x: x[0], reverse=True)
    for d, c in done_cards[:4]:
        _, ln = latest_line(c, today)
        done_li.append(f'<li><span class="k">{esc(short_title(c["title"]))}</span> {esc(cut(ln, 120))} '
                       f'<span class="pill g">카드 완료 {md(d)}</span></li>')
    appr_done = []
    if todos is not None:
        appr_done = sorted((x for x in todos if tdate(x.get("결재완료시각")) and tdate(x["결재완료시각"]) >= since),
                           key=lambda x: x["결재완료시각"], reverse=True)
    for x in appr_done[:4]:
        done_li.append(f'<li><span class="k">결재 완료</span> {esc(cut(STRIP_TAGS.sub("", x["업무명"]), 70))} — '
                       f'{esc(nim(x.get("담당자")))} <span class="pill g">{md(tdate(x["결재완료시각"]))}</span></li>')
    ledger_closed = [(d, it) for d, it in ledger.values()
                     if it.get("status") in ("resolved", "closed") and (parse_date(it.get("resolved_at")) or parse_date(d)) >= since]
    if ledger_closed:
        done_li.append(f'<li><span class="k">중간관리자 원장</span> 회신 마감 <b>{len(ledger_closed)}건</b>(#번호 기준 · {md(since)} 이후)</li>')
    counts["마친 일"] = len(done_cards) + len(appr_done)

    # 1열 — 🏗 체계
    sys_kw = re.compile(r"시스템|자동화|체계|ERP|AWS|서버|자동")
    system = [c for c in active if c.get("status") == "진행" and (
        sys_kw.search(c.get("category") or "") or (c.get("owner") or "") in ("ceo", "cto") or sys_kw.search(c.get("title") or ""))]
    system.sort(key=lambda c: (not is_gm_direct(c), c.get("due") or "9999"))
    sys_li = []
    for c in system[:4]:
        d, ln = latest_line(c, today)
        sys_li.append(f'<li><span class="k">{esc(short_title(c["title"]))}</span> {emph(cut(ln, 120))}</li>')
    counts["체계"] = len(system)

    # 2열 — 🚀 진행 중 핵심 표
    rows = []
    seen_cards = set()
    for c in active:
        if c.get("status") != "진행" or c["id"] in seen_cards:
            continue
        due = parse_date(c.get("due"))
        if not (is_gm_direct(c) or (due and due <= soon)):
            continue
        if TAG_CEO.search(c.get("title") or ""):
            continue  # ⚠ 대표님 지시 칸에 따로 실린다
        seen_cards.add(c["id"])
        d, nxt = card_next(c)
        _, ln = latest_line(c, today)
        rows.append((d or dt.date(9999, 1, 1), f'<tr><td class="n">{esc(short_title(c["title"]))}</td>'
                     f'<td>{emph(cut(ln, 110))}</td><td>{pill(d, today, nxt if nxt != "기한" else "")}</td></tr>'))
    linked = {x.get("plan_id") for x in sched if x.get("plan_id")}
    for x in sched:
        d = parse_date(x["next_due"])
        if not (today <= d <= soon) or x.get("repeat") or (x.get("plan_id") in seen_cards):
            continue
        rows.append((d, f'<tr><td class="n">{esc(cut(x["name"].split(" — ")[0], 22))}</td>'
                     f'<td>{esc(cut(x["name"], 90))} — {esc(nim(x.get("assignee") or "미정"))}</td><td>{pill(d, today, "전사일정")}</td></tr>'))
    rows.sort(key=lambda r: r[0])
    counts["진행 중 핵심"] = len(rows)
    rows = rows[:10]

    # 3열 — 🗣 말씀 나누실 주제
    topics = []
    pri = sorted(active, key=lambda c: (not TAG_CHAIRMAN.search(c.get("title") or ""), not is_gm_direct(c)))
    for c in pri:
        hit = next((clean_line(l) for _, l in c["_lines"] if re.search(r"미정|GM 결정 대기|결정 대기", l)), None)
        if hit and c.get("status") == "진행":
            topics.append(f'<b>{esc(short_title(c["title"]))}</b> — {emph(cut(hit, 90))}')
    if todos is not None:
        for x in todos:
            if x.get("결재요청") and not x.get("결재상태") and x.get("상태") != "완료" and "GM" in x["결재요청"] and not x.get("GM싸인"):
                topics.append(f'<b>{esc(cut(STRIP_TAGS.sub("", x["업무명"]), 30))}</b> — 결재 대기(GM 차례) · {esc(nim(x.get("담당자")))}')
    counts["말씀 나누실 주제"] = len(topics)
    topics = topics[:5]
    talk_li = [f'<li><span class="q">{i}</span>{t}</li>' for i, t in enumerate(topics, 1)]

    # 3열 — ✅ 기준일 이후 끝난 것(한 줄)
    fin = [short_title(c["title"]) for _, c in done_cards]
    fin += [cut(STRIP_TAGS.sub("", x["업무명"]), 28) for x in appr_done]
    if todos is not None:
        fin += [cut(x["업무명"], 28) for x in todos
                if x.get("상태") == "완료" and tdate(x.get("완료일")) and tdate(x["완료일"]) >= since
                and not tdate(x.get("결재완료시각"))]
    fin_n = len(fin)
    fin_txt = " · ".join(dict.fromkeys(fin[:14])) + (f" 외 {fin_n - 14}건" if fin_n > 14 else "")
    if ledger_closed:
        fin_txt += f" · 중간관리자 원장 회신 마감 {len(ledger_closed)}건"
    counts["끝난 것"] = fin_n + len(ledger_closed)

    # 3열 — ⚠ 대표님 지시
    ceo = [c for c in active if TAG_CEO.search(c.get("title") or "")]
    ceo_li = []
    for c in ceo:
        _, ln = latest_line(c, today)
        ceo_li.append(f'<li><span class="k">{esc(short_title(c["title"]))}</span> {emph(cut(ln, 100))} — {esc(nim(c.get("owner") or "미정"))}</li>')
    counts["대표님 지시"] = len(ceo)

    # 3열 — 📋 중간관리자 미회신
    open_by: dict[str, list[int]] = {}
    for d, it in ledger.values():
        if it.get("status") == "open":
            ref = parse_date(it.get("sent_at")) or parse_date(d) or today
            open_by.setdefault(it.get("owner") or "담당 미정", []).append((today - ref).days)
    mgr_li = [f'<li><span class="k">{esc(nim(o))}</span> {len(v)}건 · 최장 {max(v)}일</li>'
              for o, v in sorted(open_by.items(), key=lambda kv: -len(kv[1]))[:6]]
    counts["미회신"] = sum(len(v) for v in open_by.values())

    # 3열 — 📌 근거
    todo_src = f"업무&결재 SSOT {len(todos)}행" if todos is not None else "업무&결재 SSOT <b>조회 실패(미반영)</b>"
    basis = (f"GM업무 카드 {len(cards)}장(진행 {len(active)}) · 중간관리자 원장 #{len(ledger)}건(미회신 {counts['미회신']}) · "
             f"전사일정 {len(sched)}건 · {todo_src} — 기준일 {since.isoformat()} · 추정 없음 · 미정은 「미정」")

    doc_no = f"WP-GM-{now:%y%m%d}-BRIEF"
    wd = "월화수목금토일"[now.weekday()]
    stamp = f"{now.year}. {now.month:02d}. {now.day:02d}. ({wd}) {now:%H:%M}"
    ctx = dict(since=md(since), stamp=stamp, doc_no=doc_no,
               sub=f"회장님 지시 진행 {len(chair)}건 · {md(since)} 이후 마친 일 {counts['마친 일']}건 · 진행 중 핵심 {len(rows)}건 · 말씀 나누실 주제 {len(topics)} — 한 장",
               chair=chair_li, done=done_li, sys=sys_li, rows=[r for _, r in rows], talk=talk_li, fin=fin_txt,
               ceo=ceo_li, mgr=mgr_li, basis=basis, n_chair=len(chair), n_done=len(done_li), n_talk=len(topics))
    return ctx, counts


def ul(items: list[str], empty="해당 없음") -> str:
    return "<ul>" + ("".join(items) if items else f"<li>{empty}</li>") + "</ul>"


TEMPLATE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>회의 요약 — 지난 보고({since}) 이후 달라진 것</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&family=Noto+Serif+KR:wght@600;800&display=swap" rel="stylesheet">
<style>
:root{{--ink:#1a1815;--sub:#5f5a54;--line:#d9d3cc;--navy:#1f2f4a;--gold:#b58a3a;--bg:#faf8f5;--red:#a33a2a;--ok:#2f6f4e;--fs:{fs}px}}
@page{{size:A3 landscape;margin:0}}
*{{box-sizing:border-box}}
body{{margin:0;background:#8A9099;font-family:'Noto Sans KR',sans-serif;color:var(--ink);-webkit-print-color-adjust:exact;print-color-adjust:exact}}
.page{{width:1587px;height:1123px;background:#fff;margin:66px auto 30px;padding:28px 34px 20px;display:flex;flex-direction:column;box-shadow:0 4px 20px rgba(0,0,0,.35);overflow:hidden}}
@media print{{body{{background:#fff}}.page{{margin:0!important;box-shadow:none!important}}}}
.hd{{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:3px solid var(--navy);padding-bottom:8px}}
.brand{{font:700 12px/1 'Noto Serif KR',serif;letter-spacing:.32em;color:var(--gold)}}
h1{{font:800 27px/1.2 'Noto Serif KR',serif;margin:6px 0 4px;color:var(--navy)}}
.sub{{font-size:13.5px;color:var(--sub)}}
.meta{{text-align:right;font-size:12px;color:var(--sub);line-height:1.6}}
.meta b{{color:var(--ink)}}
.grid{{display:grid;grid-template-columns:1.05fr 1.15fr 1fr;gap:14px;margin-top:12px;flex:1;min-height:0}}
.col{{display:flex;flex-direction:column;gap:12px;min-height:0}}
.box{{border:1px solid var(--line);border-radius:6px;padding:10px 12px 8px;background:#fff}}
.box h2{{margin:0 0 6px;font-size:14px;font-weight:900;color:var(--navy);display:flex;align-items:center;gap:6px;border-left:4px solid var(--gold);padding-left:8px}}
.box h2 .tag{{font-size:10.5px;font-weight:700;color:#fff;background:var(--navy);border-radius:3px;padding:1px 6px}}
.box.top{{background:var(--navy);color:#fff;border-color:var(--navy)}}
.box.top h2{{color:#fff;border-left-color:var(--gold)}}
.box.top li{{color:#e9edf3}}
.box.top .k{{color:var(--gold)}}
ul{{margin:0;padding-left:16px}}
li{{font-size:var(--fs);line-height:1.55;margin:2px 0}}
li b{{font-weight:700}}
.k{{display:inline-block;min-width:74px;font-weight:700;color:var(--navy)}}
.ok{{color:var(--ok);font-weight:700}}.red{{color:var(--red);font-weight:700}}
table{{width:100%;border-collapse:collapse;font-size:calc(var(--fs) + .6px)}}
th{{background:#f1eee9;text-align:left;padding:4px 6px;border:1px solid var(--line);font-weight:700}}
td{{padding:6px 7px;border:1px solid var(--line);vertical-align:top;line-height:1.5}}
td.n{{font-weight:700;color:var(--navy);white-space:nowrap}}
.pill{{display:inline-block;font-size:10.5px;font-weight:700;padding:1px 6px;border-radius:3px;background:#eef2f7;color:var(--navy)}}
.pill.g{{background:#e6f2ea;color:var(--ok)}}.pill.r{{background:#f7e8e5;color:var(--red)}}.pill.y{{background:#faf1dc;color:#7a5a12}}
.ft{{display:flex;justify-content:space-between;border-top:1px solid var(--line);margin-top:10px;padding-top:6px;font-size:11px;color:var(--sub)}}
.talk li{{font-size:calc(var(--fs) + .4px)}}
.talk .q{{display:inline-block;width:22px;height:22px;border-radius:50%;background:var(--gold);color:#fff;text-align:center;line-height:22px;font-weight:900;font-size:12px;margin-right:6px}}
</style></head><body>
<div class="page">
  <div class="hd">
    <div>
      <div class="brand">WELLPERION</div>
      <h1>회의 요약 — 지난 보고({since}) 이후 달라진 것</h1>
      <div class="sub">{sub}</div>
    </div>
    <div class="meta">보고 <b>김남욱 GM</b> · 작성 <b>AI 웰리</b><br>{stamp} · 문서번호 {doc_no}</div>
  </div>

  <div class="grid">
    <!-- 1열 -->
    <div class="col">
      <div class="box top">
        <h2>👑 회장님 지시 진행 <span class="tag">{n_chair}건</span></h2>
        {chair}
      </div>
      <div class="box">
        <h2>📅 {since} 이후 마친 일 <span class="tag">{n_done}건</span></h2>
        {done}
      </div>
      <div class="box">
        <h2>🏗 체계 — 지시 없이 돌게 만드는 것</h2>
        {sys}
      </div>
    </div>

    <!-- 2열 -->
    <div class="col">
      <div class="box" style="flex:1">
        <h2>🚀 진행 중 핵심 — 숫자·기한</h2>
        <table>
          <tr><th style="width:150px">건</th><th>현재</th><th style="width:118px">다음</th></tr>
          {rows}
        </table>
      </div>
    </div>

    <!-- 3열 -->
    <div class="col">
      <div class="box">
        <h2>🗣 말씀 나누실 주제 <span class="tag">{n_talk}</span></h2>
        {talk}
      </div>
      <div class="box">
        <h2>✅ {since} 이후 끝난 것</h2>
        <ul><li>{fin}</li></ul>
      </div>
      <div class="box">
        <h2>⚠ 대표님 지시 진행</h2>
        {ceo}
      </div>
      <div class="box">
        <h2>📋 중간관리자 미회신 — 사람별</h2>
        {mgr}
      </div>
      <div class="box">
        <h2>📌 이 종이의 근거</h2>
        <ul><li>{basis}</li></ul>
      </div>
    </div>
  </div>

  <div class="ft"><span>이 종이 한 장 = 회의용 요약 · 상세는 GM업무 화면(erp.wellperion.com/coo/chairman/GM업무.html) · 생성 scripts/meeting_brief_a3.py</span><span>AI 웰리 · {stamp}</span></div>
</div>
</body></html>
"""


def render(ctx: dict, fs: float) -> str:
    c = dict(ctx)
    c["chair"] = ul(ctx["chair"], "태그 [회장님 지시] 카드 없음")
    c["done"] = ul(ctx["done"], f"{ctx['since']} 이후 마친 기록 없음")
    c["sys"] = ul(ctx["sys"])
    c["talk"] = '<ul class="talk">' + ("".join(ctx["talk"]) or "<li>미정·결재 대기 항목 없음</li>") + "</ul>"
    c["rows"] = "\n          ".join(ctx["rows"])
    c["ceo"] = ul(ctx["ceo"])
    c["mgr"] = ul(ctx["mgr"], "미회신 없음")
    c["fs"] = fs
    return TEMPLATE.format(**c)


def measure(path: str, png: str | None) -> int:
    """헤드리스로 .page 안 내용의 실제 높이(px). overflow:hidden 이라 눈엔 안 보이는 넘침도 잰다."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1680, "height": 1250})
        pg.goto("file:///" + os.path.abspath(path).replace("\\", "/"))
        pg.wait_for_timeout(600)
        h = pg.evaluate("""() => {
          const page = document.querySelector('.page'); const top = page.getBoundingClientRect().top;
          const bottoms = [...document.querySelectorAll('.box, .ft, td, li')].map(e => e.getBoundingClientRect().bottom - top);
          return Math.ceil(Math.max(page.scrollHeight, Math.max(...bottoms) + 20)); }""")  # 20 = .page 아래 padding
        if png:
            pg.locator(".page").screenshot(path=png)
        b.close()
    return h


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="기준일 YYYY-MM-DD (기본 7일 전)")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--check", action="store_true", help="헤드리스 넘침 실측 + png")
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()
    now = dt.datetime.now()
    today = now.date()
    since = parse_date(a.since) if a.since else today - dt.timedelta(days=7)
    log = lambda m: print("  ·", m)  # noqa: E731

    ctx, counts = build(since, today, now, log)
    png = os.path.splitext(a.out)[0] + ".png"
    h, fs = None, FS_STEPS[0]
    for fs in FS_STEPS:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(render(ctx, fs))
        if not a.check:
            break
        h = measure(a.out, png)
        print(f"  · fs={fs} → 내용 높이 {h}/{PAGE_H}")
        if h <= PAGE_H:
            break
    print(f"저장 {a.out}")
    print(" · ".join(f"{k} {v}" for k, v in counts.items()))
    if a.check:
        print(f"검수 scrollHeight {h}/{PAGE_H} · fs={fs} · png {png}")
    if a.open:
        subprocess.run(["powershell", "-NoProfile", "-File", os.path.join(ROOT, "scripts", "open_primary.ps1"), a.out], check=False)
    return 2 if (a.check and h and h > PAGE_H) else 0


if __name__ == "__main__":
    sys.exit(main())
