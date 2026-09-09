# -*- coding: utf-8 -*-
"""주간 일정 공유 — 이번 주(월~토) 전사일정을 카톡 세 방에 같은 글로 보낸다.

GM 지시 2026-09-09: "1주일이면 오늘 9일 ~ 11일(금)까지야 5일간 이번주간 일정만 보내주면
되잖아 다른 운영부방, 중간관리자방이랑 같게 보내줘 // 혹시 토요일까지 넣어두는걸로 셋업
업데이트해줄 수도 있어?"

- 주간 = 월요일부터 토요일까지. 웰페리온은 토요일에 문을 여니 토요일이 주간에 들어간다.
- 주 중간에 돌리면 오늘부터 토요일까지만 남긴다 — 지나간 날을 다시 보내지 않는다.
- 방 둘 = ★관리부 · ★운영부. 중간관리자 방은 관리부와 멤버가 겹쳐 뺐다(GM 지시 2026-09-09).
- 발신 관문은 kakao_report_sender 하나뿐이다. 여기서 새 발신 경로를 만들지 않는다(약속 L21).

실행:
    C:/Python314/python.exe scripts/weekly_schedule_notice.py            # 미리보기(기본)
    C:/Python314/python.exe scripts/weekly_schedule_notice.py --live     # 실제 발송
    C:/Python314/python.exe scripts/weekly_schedule_notice.py --selftest # 자체 점검
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

PYTHON = r"C:/Python314/python.exe"
# ★중간관리자 방은 넣지 않는다 — 관리부 방과 멤버가 겹치고, 나우열M 은 텔레그램
# 업무관리 방으로 따로 받는다(GM 지시 2026-09-09). 같은 사람이 같은 글을 두 번 받으면
# 어느 쪽을 봐야 하는지 흐려진다.
ROOMS = ["★관리부", "★운영부"]
WEEKDAY_KR = "월화수목금토일"


def week_range(today: dt.date) -> tuple[dt.date, dt.date]:
    """이번 주 남은 구간 (시작, 끝=토요일).

    월요일에 돌면 월~토 엿새를 다 낸다. 주 중간이면 오늘부터 토요일까지만 낸다 —
    이미 지나간 날을 다시 보내면 읽는 사람이 무엇이 남았는지 못 고른다.
    일요일은 휴관일이라 주간에 넣지 않는다. 일요일에 돌면 다음 주 월~토를 낸다.
    """
    if today.weekday() == 6:                       # 일요일 → 다음 주
        start = today + dt.timedelta(days=1)
        return start, start + dt.timedelta(days=5)
    saturday = today + dt.timedelta(days=5 - today.weekday())
    return today, saturday


def collect(start: dt.date, end: dt.date) -> list[tuple[dt.date, str, str]]:
    """전사일정에서 그 구간의 (날짜, 이름, 담당). 날짜 키는 항목마다 다르므로 앞선 것 하나만 본다."""
    import schedule_ssot as S

    data = S.load()
    items = data.get("items") if isinstance(data, dict) else data
    out = []
    for e in items or []:
        for key in ("next_due", "date", "due", "start_date"):
            raw = str(e.get(key) or "")[:10]
            if len(raw) != 10:
                continue
            try:
                day = dt.date.fromisoformat(raw)
            except ValueError:
                break
            if start <= day <= end:
                name = str(e.get("name") or e.get("title") or "").strip()
                who = str(e.get("assignee") or "").split("·")[0].strip()
                if name:
                    out.append((day, name, who))
            break
    return sorted(out)


def build_message(rows, start: dt.date, end: dt.date) -> str:
    head = (f"이번 주 남은 일정입니다 "
            f"({start.month}/{start.day} {WEEKDAY_KR[start.weekday()]} ~ "
            f"{end.month}/{end.day} {WEEKDAY_KR[end.weekday()]})")
    if not rows:
        return head + "\n▪ 등록된 일정이 없습니다\n👉 확인만 해 주시면 됩니다.\n웰페리온 AI 드림"
    lines = [head]
    for day, name, who in rows:
        line = f"▪ {day.month}/{day.day}({WEEKDAY_KR[day.weekday()]}) {name}"
        if who:
            line += f" — {who}"
        lines.append(line[:78])
    lines.append("👉 확인만 해 주시면 됩니다. 담당·날짜가 다르면 알려 주세요.")
    lines.append("웰페리온 AI 드림")
    return "\n".join(lines)


def send(message: str, live: bool) -> int:
    failed = 0
    for room in ROOMS:
        cmd = [PYTHON, str(BASE_DIR / "scripts" / "kakao_report_sender.py"),
               "--sender", "웰리", "--only-room", room, "--message", message]
        if not live:
            cmd.append("--dry-run")
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=400, cwd=str(BASE_DIR))
        ok = "전송 완료" in (r.stdout or "") or "DRY-RUN" in (r.stdout or "")
        print(f"{room}: {'ok' if ok else '실패'}")
        if not ok:
            failed += 1
            print((r.stdout or "")[-400:])
    return failed


def selftest() -> None:
    # 주 중간(수)에 돌리면 오늘부터 토요일까지
    wed = dt.date(2026, 9, 9)
    assert week_range(wed) == (wed, dt.date(2026, 9, 12)), week_range(wed)
    # 월요일에 돌리면 월~토 엿새
    mon = dt.date(2026, 9, 7)
    assert week_range(mon) == (mon, dt.date(2026, 9, 12)), week_range(mon)
    # 토요일에 돌리면 그날 하루
    sat = dt.date(2026, 9, 12)
    assert week_range(sat) == (sat, sat), week_range(sat)
    # 일요일은 다음 주 월~토
    sun = dt.date(2026, 9, 13)
    assert week_range(sun) == (dt.date(2026, 9, 14), dt.date(2026, 9, 19)), week_range(sun)
    # 빈 목록도 문장이 되어야 한다 — 일정이 없다고 발송이 깨지면 안 된다
    msg = build_message([], wed, dt.date(2026, 9, 12))
    assert "등록된 일정이 없습니다" in msg and msg.endswith("웰페리온 AI 드림")
    msg2 = build_message([(wed, "승강기 자체점검", "시설부")], wed, dt.date(2026, 9, 12))
    assert "▪ 9/9(수) 승강기 자체점검 — 시설부" in msg2, msg2
    print("SELFTEST OK — 주간 구간 4종 · 본문 2종")


def main() -> int:
    ap = argparse.ArgumentParser(description="주간 일정 공유(월~토) — 카톡 세 방")
    ap.add_argument("--live", action="store_true", help="실제 발송(기본은 미리보기)")
    ap.add_argument("--date", help="기준일 YYYY-MM-DD(시험용)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return 0
    today = dt.date.fromisoformat(a.date) if a.date else dt.date.today()
    start, end = week_range(today)
    rows = collect(start, end)
    message = build_message(rows, start, end)
    print(message)
    print("─" * 40)
    return send(message, a.live)


if __name__ == "__main__":
    sys.exit(main())
