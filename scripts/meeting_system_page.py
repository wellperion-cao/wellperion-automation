# -*- coding: utf-8 -*-
"""meeting_system_page.py — 회의 체계 화면 생성 (배 2706).

왜: GM 2026-09-16 17:0x 「리마인드가 체계야? 그냥 알리는 거지? 페이지를 통해서 계속 체크할 수 있게 해줘야 해」.
    회장님 말씀 2026-09-16 의 회의 2종을 알림이 아니라 원장 + 화면으로 굴린다. 알림은 원장에서 파생된다.

원천(읽기만 · 어느 원천도 고치지 않는다)
  ① status/meeting_system.json   회의 2종 정의 + 회차(날짜·체크·자료·녹음·요약·결정)  ← 정본
  ② status/schedule_ssot.json    전사일정 — 같은 회의의 next_due 와 원장 date 가 다르면 ⚠ 한 줄만 표시

내는 것: 3. 웰페리온 가이드/coo/chairman/회의체계.html (+ --check 로 같은 이름 .png)
화면용 1열(스크롤) · 인쇄하면 A4 세로. CSS 팔레트·글꼴 = scripts/meeting_brief_a3.py 와 같다.

쓰는 법
  C:/Python314/python.exe scripts/meeting_system_page.py [--out 경로] [--check] [--open]
    --check  헤드리스 렌더 → png 저장 + 콘솔 오류 수 확인(오류 있으면 rc=1)
    --open   scripts/open_primary.ps1 로 GM 주 모니터에 띄움(기본 안 함)
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE = os.path.join(ROOT, "3. 웰페리온 가이드")
LEDGER = os.path.join(ROOT, "status", "meeting_system.json")
SCHED = os.path.join(ROOT, "status", "schedule_ssot.json")
OUT = os.path.join(GUIDE, "coo", "chairman", "회의체계.html")
RED_DAYS = 10  # 회의 창이 열리기 D-10 안인데 날짜가 미정이면 빨강


def esc(s) -> str:
    return html.escape(str(s or ""), quote=False)


def read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_date(s) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def schedule_due(sched: dict) -> dict:
    """전사일정 items → {id: next_due}. 읽기만."""
    return {it.get("id"): it.get("next_due") for it in sched.get("items", []) if it.get("id")}


def date_cell(rnd: dict, today: dt.date) -> tuple[str, str]:
    """(표시 문구, 색 class). 확정=초록 · 미정이고 창이 D-10 안=빨강 · 그 밖=중립."""
    if rnd.get("date"):
        return f"{rnd['date']} · {rnd.get('date_status', '확정')}", "ok"
    win = parse_date(rnd.get("window_start"))
    txt = rnd.get("date_status") or "미정"
    if win and (win - today).days <= RED_DAYS:
        d = (win - today).days
        return f"{txt} · 회의 창 {win} (D{d:+d})", "red"
    return txt + (f" · 회의 창 {win}" if win else ""), "mute"


def checks_html(rnd: dict) -> tuple[str, int, int]:
    items = rnd.get("checks", {})
    done = sum(1 for v in items.values() if v)
    li = "".join(
        f'<li class="{"c-on" if v else "c-off"}">{"☑" if v else "☐"} {esc(k)}</li>'
        for k, v in items.items()
    )
    return f'<ul class="ck">{li}</ul>' or "", done, len(items)


def summary_link(rnd: dict) -> str:
    """요약 파일은 같은 폴더(coo/chairman) 기준 상대 경로로 건다. 없으면 「없음」."""
    name = rnd.get("summary")
    if not name:
        return '<span class="mute">없음</span>'
    if not os.path.exists(os.path.join(GUIDE, "coo", "chairman", name)):
        return f'{esc(name)} <span class="red">(파일 없음)</span>'
    return f'<a href="{esc(name)}">{esc(name)}</a>'


def round_card(mt: dict, rnd: dict, today: dt.date, due: dict) -> str:
    txt, cls = date_cell(rnd, today)
    ck, done, total = checks_html(rnd)
    warn = ""
    ev = mt.get("schedule_event")
    nd = due.get(ev)
    if rnd.get("date") and nd and nd != rnd["date"]:
        warn = (f'<div class="warn">⚠ 전사일정과 다름 — 원장 {esc(rnd["date"])} · 전사일정 {esc(nd)} '
                f'({esc(ev)}) · 이 화면은 읽기만 한다</div>')
    elif not rnd.get("date") and nd:
        warn = f'<div class="note">전사일정 next_due = {esc(nd)} · 원장은 아직 미정</div>'
    mats = "".join(f"<li>{esc(m)}</li>" for m in mt.get("materials", []))
    if mt.get("materials_note"):
        mats += f'<li class="mute">{esc(mt["materials_note"])}</li>'
    dec = rnd.get("decisions") or []
    dec_html = (f'<a href="GM업무.html">{len(dec)}건 — {esc(" · ".join(dec))}</a>' if dec
                else '<span class="mute">없음</span>')
    rec = esc(rnd.get("recording")) if rnd.get("recording") else (
        '<span class="mute">미등록</span>' if mt.get("recording") else '<span class="mute">해당 없음</span>')
    return f"""
  <div class="card">
    <h2>{esc(mt['name'])} <span class="ym">{esc(rnd['ym'])}</span>
        <span class="pill {'g' if rnd.get('status') == '완료' else 'y'}">{esc(rnd.get('status'))}</span></h2>
    <div class="kv"><span class="k">날짜</span><b class="{cls}">{esc(txt)}</b></div>
    <div class="kv"><span class="k">규칙</span>{esc(mt.get('rule'))}</div>
    <div class="kv"><span class="k">참석</span>{esc(' · '.join(mt.get('attendees', [])))}</div>
    {warn}
    <div class="kv"><span class="k">준비 {done}/{total}</span></div>
    {ck}
    <div class="kv"><span class="k">자료</span></div><ul class="mat">{mats}</ul>
    <div class="kv"><span class="k">녹음</span>{rec}</div>
    <div class="kv"><span class="k">요약</span>{summary_link(rnd)}</div>
    <div class="kv"><span class="k">결정·지시</span>{dec_html}</div>
  </div>"""


TEMPLATE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>회의 체계 — 중간회의 · 월말 결산 회의</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&family=Noto+Serif+KR:wght@600;800&display=swap" rel="stylesheet">
<style>
:root{{--ink:#1a1815;--sub:#5f5a54;--line:#d9d3cc;--navy:#1f2f4a;--gold:#b58a3a;--bg:#faf8f5;--red:#a33a2a;--ok:#2f6f4e}}
@page{{size:A4 portrait;margin:12mm}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);font-family:'Noto Sans KR',sans-serif;color:var(--ink);font-size:14px;line-height:1.6}}
.wrap{{max-width:900px;margin:0 auto;padding:26px 20px 40px}}
.hd{{border-bottom:3px solid var(--navy);padding-bottom:10px}}
.brand{{font:700 12px/1 'Noto Serif KR',serif;letter-spacing:.32em;color:var(--gold)}}
h1{{font:800 26px/1.25 'Noto Serif KR',serif;margin:8px 0 6px;color:var(--navy)}}
.sub{{font-size:13.5px;color:var(--sub)}}
.meta{{font-size:12px;color:var(--sub);margin-top:6px}}
.card{{background:#fff;border:1px solid var(--line);border-radius:8px;padding:14px 16px 12px;margin-top:14px}}
.card h2{{margin:0 0 8px;font-size:17px;font-weight:900;color:var(--navy);border-left:4px solid var(--gold);padding-left:9px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.ym{{font-size:13px;color:var(--sub);font-weight:700}}
.kv{{margin:3px 0}}
.k{{display:inline-block;min-width:88px;font-weight:700;color:var(--navy)}}
.ok{{color:var(--ok);font-weight:700}}.red{{color:var(--red);font-weight:700}}.mute{{color:var(--sub)}}
.pill{{font-size:11px;font-weight:700;padding:1px 7px;border-radius:3px;background:#eef2f7;color:var(--navy)}}
.pill.g{{background:#e6f2ea;color:var(--ok)}}.pill.y{{background:#faf1dc;color:#7a5a12}}
ul.ck,ul.mat{{margin:4px 0 8px;padding-left:4px;list-style:none}}
ul.ck li,ul.mat li{{margin:2px 0}}
ul.mat li{{padding-left:14px;text-indent:-14px}}
ul.mat li:before{{content:"· "}}
.c-off{{color:var(--red);font-weight:700}}
.c-on{{color:var(--ok)}}
.warn{{margin:6px 0;padding:6px 9px;border-radius:5px;background:#f7e8e5;color:var(--red);font-weight:700}}
.note{{margin:6px 0;padding:6px 9px;border-radius:5px;background:#f1eee9;color:var(--sub)}}
table{{width:100%;border-collapse:collapse;margin-top:6px;font-size:13.5px}}
th{{background:#f1eee9;text-align:left;padding:5px 7px;border:1px solid var(--line);font-weight:700}}
td{{padding:6px 7px;border:1px solid var(--line);vertical-align:top}}
a{{color:var(--navy)}}
h3{{margin:26px 0 0;font-size:15px;font-weight:900;color:var(--navy)}}
.ft{{border-top:1px solid var(--line);margin-top:22px;padding-top:8px;font-size:11.5px;color:var(--sub)}}
</style></head><body>
<div class="wrap">
  <div class="hd">
    <div class="brand">WELLPERION</div>
    <h1>회의 체계 — 중간회의 · 월말 결산 회의</h1>
    <div class="sub">회장님 말씀 2026-09-16 — 매월 중간회의(회장님·대표님·GM)와 월말 결산 회의(팀 리더 포함 · 녹음 + AI 요약).</div>
    <div class="meta">원장 status/meeting_system.json · 생성 scripts/meeting_system_page.py · {stamp}</div>
  </div>

  <h3>이번 회차</h3>
  {current}

  <h3>지난 회차</h3>
  <table>
    <tr><th style="width:190px">회차</th><th style="width:120px">날짜</th><th style="width:80px">결정</th><th>요약</th></tr>
    {past}
  </table>

  <h3>알림(원장에서 파생)</h3>
  <div class="card">
    <div class="kv">알림 예정 — 매월 <b>5일</b>(중간회의 일정 확인) · 매월 <b>20일</b>(결산 회의 날짜)</div>
    {alerts}
    <div class="note">발신 = scripts/monthly_meeting_reminders.py(시토 · 07:5x GM 봇방 한 줄). 체계는 이 원장과 화면이고,
      알림은 거기서 파생된다 — 「날짜 미정·자료 미제출」일 때만 보내도록 잇는 것이 다음 걸음이다.</div>
  </div>

  <div class="ft">이 화면은 원장을 읽어 그린다 — 손으로 고치지 않는다(고칠 곳 = status/meeting_system.json).
    전사일정(status/schedule_ssot.json)은 읽기만 하고 어긋나면 ⚠ 로 보인다.</div>
</div>
</body></html>
"""


def next_round(led: dict, meeting: str) -> dict | None:
    """그 회의의 다음(완료 아닌 · ym 가장 이른) 회차 — 없으면 None."""
    todo = [r for r in led.get("rounds", []) if r.get("meeting") == meeting and r.get("status") != "완료"]
    todo.sort(key=lambda r: r.get("ym", ""))
    return todo[0] if todo else None


def reminder_verdict(meeting: str, rnd: dict) -> tuple[bool, str]:
    """리마인드가 나가야 하나 — 화면 「알림(원장에서 파생)」 절과 monthly_meeting_reminders.py 가 같이 쓰는 판정 하나(순수 함수).
    중간회의(mid) = 날짜가 비어 있으면 나감. 결산 회의(closing) = 「리더별 결산 한 장」 체크 중 미제출이 있으면 나감(날짜 미정도 나감).
    돌려주는 값 = (나감 여부, 사람이 읽는 이유)."""
    if not rnd.get("date"):
        return True, "날짜 미정"
    checks = rnd.get("checks", {}) or {}
    if meeting == "closing":
        missing = [k for k, v in checks.items() if k.startswith("리더별 결산 한 장") and not v]
        if missing:
            return True, f"리더별 결산 한 장 미제출 {len(missing)}건"
        return False, "날짜 확정 · 리더별 결산 한 장 제출 완료"
    open_n = sum(1 for v in checks.values() if not v)
    return (False, "날짜 확정 · 준비 완료") if not open_n else (False, f"날짜 확정 · 남은 준비 {open_n}건(리마인드 대상 아님)")


def build(led: dict, sched: dict, now: dt.datetime) -> str:
    today = now.date()
    due = schedule_due(sched)
    meetings = led.get("meetings", {})
    rounds = led.get("rounds", [])

    current, alerts = [], []
    for key, mt in meetings.items():
        todo = [r for r in rounds if r.get("meeting") == key and r.get("status") != "완료"]
        todo.sort(key=lambda r: r.get("ym", ""))
        if not todo:
            current.append(f'<div class="card"><h2>{esc(mt["name"])}</h2>'
                           f'<div class="kv"><span class="mute">예정 회차가 원장에 없다 — 원장에 회차를 넣어야 뜬다</span></div></div>')
            continue
        rnd = todo[0]
        current.append(round_card(mt, rnd, today, due))
        verdict, why = reminder_verdict(key, rnd)
        cls = "red" if verdict else "ok"
        alerts.append(f'<div class="kv"><span class="k {cls}">{"나감" if verdict else "안 나감"}</span>{esc(mt["name"])} {esc(rnd["ym"])} — {esc(why)}</div>')

    past_rows = []
    for r in sorted([x for x in rounds if x.get("status") == "완료"], key=lambda x: x.get("date") or x.get("ym"), reverse=True):
        name = meetings.get(r.get("meeting"), {}).get("name", r.get("meeting"))
        past_rows.append(f'<tr><td>{esc(name)} {esc(r.get("ym"))}</td><td>{esc(r.get("date") or "미정")}</td>'
                         f'<td>{len(r.get("decisions") or [])}건</td><td>{summary_link(r)}</td></tr>')
    if not past_rows:
        past_rows.append('<tr><td colspan="4" class="mute">지난 회차 없음</td></tr>')

    wd = "월화수목금토일"[now.weekday()]
    return TEMPLATE.format(
        stamp=f"{now.year}. {now.month:02d}. {now.day:02d}. ({wd}) {now:%H:%M}",
        current="\n".join(current), past="\n    ".join(past_rows), alerts="\n    ".join(alerts))


def measure(path: str, png: str) -> list[str]:
    """헤드리스 렌더 → png 저장 + 콘솔 오류 목록."""
    from playwright.sync_api import sync_playwright
    errors: list[str] = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1000, "height": 1400})
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto("file:///" + os.path.abspath(path).replace("\\", "/"))
        pg.wait_for_timeout(700)
        pg.screenshot(path=png, full_page=True)
        b.close()
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--check", action="store_true", help="헤드리스 png + 콘솔 오류 확인")
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()

    led, sched = read_json(LEDGER), read_json(SCHED)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(build(led, sched, dt.datetime.now()))
    n_open = sum(1 for r in led.get("rounds", []) if r.get("status") != "완료")
    print(f"저장 {a.out}")
    print(f"회차 {len(led.get('rounds', []))}건 (진행 {n_open}) · 회의 {len(led.get('meetings', {}))}종")

    rc = 0
    if a.check:
        png = os.path.splitext(a.out)[0] + ".png"
        errs = measure(a.out, png)
        print(f"검수 콘솔 오류 {len(errs)}건 · png {png}")
        for e in errs[:5]:
            print("  ·", e)
        rc = 1 if errs else 0
    if a.open:
        subprocess.run(["powershell", "-NoProfile", "-File", os.path.join(ROOT, "scripts", "open_primary.ps1"), a.out], check=False)
    return rc


def _selfcheck() -> None:
    """원장 없이도 판정 함수가 맞는지 — 날짜 색·체크 집계."""
    today = dt.date(2026, 10, 10)
    assert date_cell({"date": "2026-10-01", "date_status": "확정"}, today)[1] == "ok"
    assert date_cell({"date": "", "date_status": "미정", "window_start": "2026-10-15"}, today)[1] == "red"
    assert date_cell({"date": "", "date_status": "미정", "window_start": "2026-11-15"}, today)[1] == "mute"
    assert checks_html({"checks": {"a": True, "b": False}})[1:] == (1, 2)
    # 리마인드 판정(화면·monthly_meeting_reminders 공용)
    assert reminder_verdict("mid", {"date": ""})[0] is True
    assert reminder_verdict("mid", {"date": "2026-10-16", "checks": {"회의 요약 A3 준비": False}})[0] is False
    assert reminder_verdict("closing", {"date": "2026-10-01", "checks": {"리더별 결산 한 장 — 이경연 실장님": False, "녹음 파일": False}}) == (True, "리더별 결산 한 장 미제출 1건")
    assert reminder_verdict("closing", {"date": "2026-10-01", "checks": {"리더별 결산 한 장 — 이경연 실장님": True}})[0] is False
    led = {"rounds": [{"meeting": "mid", "ym": "2026-11", "status": "준비중"}, {"meeting": "mid", "ym": "2026-10", "status": "준비중"}, {"meeting": "mid", "ym": "2026-09", "status": "완료"}]}
    assert next_round(led, "mid")["ym"] == "2026-10" and next_round(led, "closing") is None
    print("selfcheck ok")


if __name__ == "__main__":
    sys.exit(_selfcheck() if "--selfcheck" in sys.argv else main())
