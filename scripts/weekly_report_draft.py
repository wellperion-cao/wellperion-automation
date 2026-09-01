# -*- coding: utf-8 -*-
"""주간 리포트 초안 자동 생성 — 3라인 직책체계 §7 (배860 · 시토 2026-09-01)

매주 월 07:00, monthly_ops_sync.bat 말미에서 호출된다(새 예약작업 없음 · 약속 L21).
월요일이 아니면 그냥 종료한다. --force 로 아무 요일이나 미리보기(발송 없음).

양식 = docs/3라인_직책체계_20260831.md §7 (4항목):
  ① 전결 처리 건   — 전사일정에서 지난주 GM(김남욱) 건을 후보로 추출. 왜/결과/비용은 GM 기입.
  ② 회장님 판단 필요 건 — 사람 판단 칸. 빈 줄로 두고 GM 이 채운다. 지어내지 않는다.
  ③ 지적사항 처리 결과 — 회장님 지시 트래킹 원문이 아직 없다(GM PC) → 「자료 대기」 고정.
  ④ 다음 주 예정   — 전사일정 next_due 오늘~+7일.

발신 = wellperion-agents/telegram_notifier.TelegramNotifier(기존 관문)만. 기본 dry-run,
--send 일 때만 업무 보고 방으로 나간다. 이 초안은 GM 검수 후 회장님께 나간다 — 자동 회장님 발송 아님.
"""
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEDULE = ROOT / "status" / "schedule_ssot.json"
DRAFT_DIR = ROOT / "status" / "drafts"
MAX_LINES = 15  # 섹션당 표시 상한 — 넘치면 「외 N건」으로 전사일정 화면을 가리킨다
SCHEDULE_URL = "https://wellperion-cao.github.io/wellperion-automation/coo/check/%EC%A0%84%EC%82%AC_%EC%9D%BC%EC%A0%95.html"
WD_KOR = "월화수목금토일"


def _load_items():
    data = json.loads(SCHEDULE.read_text(encoding="utf-8"))
    return data.get("items", [])


def _parse_due(item):
    raw = (item.get("next_due") or "").strip()[:10]
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _fmt(item, due):
    who = (item.get("assignee") or "").strip()
    t = (item.get("time") or "").strip()
    parts = [f"{due.month}/{due.day}({WD_KOR[due.weekday()]})"]
    if t:
        parts.append(t)
    parts.append((item.get("name") or "(이름 없음)").strip())
    line = " ".join(parts)
    if who:
        line += f" — {who}"
    return "· " + line


def _section(lines):
    if not lines:
        return ["· (해당 없음)"]
    shown = lines[:MAX_LINES]
    if len(lines) > MAX_LINES:
        shown.append(f"· 외 {len(lines) - MAX_LINES}건 — 전사일정 화면 참조")
    return shown


def build_draft(today=None):
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())  # 이번 주 월요일
    last_mon, last_sun = monday - timedelta(days=7), monday - timedelta(days=1)
    week_end = today + timedelta(days=6)

    done_gm, upcoming = [], []
    for it in _load_items():
        due = _parse_due(it)
        if due is None:
            continue
        key = (due, (it.get("time") or "").strip())
        if last_mon <= due <= last_sun and "김남욱" in (it.get("assignee") or ""):
            done_gm.append((key, _fmt(it, due)))
        elif today <= due <= week_end:
            upcoming.append((key, _fmt(it, due)))
    done_gm = [line for _, line in sorted(done_gm)]
    upcoming = [line for _, line in sorted(upcoming)]

    lines = [
        f"📋 주간 리포트 초안 — {today.month}/{today.day}({WD_KOR[today.weekday()]}) · 회장님 보고용",
        "(자동 초안입니다 — GM 검수 후 발송해 주세요. 회장님께 자동으로 나가지 않습니다)",
        "",
        "① 전결 처리 건 — 지난주 GM 건 후보(전사일정 자동 추출 · 처리 여부/왜/결과/비용은 GM 확정)",
        *_section(done_gm),
        "",
        "② 회장님 판단 필요 건 — 배경 / 선택지 / GM 의견 (GM 기입)",
        "· ",
        "",
        "③ 지적사항 처리 결과",
        "· 자료 대기 — 회장님 지시 트래킹 원문 미확보(웰리 배859 작업 중)",
        "",
        "④ 다음 주 예정 — 전사일정 (회장님 참석·확인 필요 건은 GM 표시)",
        *_section(upcoming),
        "",
        f"📎 전사일정 {SCHEDULE_URL}",
        "📄 양식 정본 docs/3라인_직책체계_20260831.md §7",
    ]
    return "\n".join(lines)


def main(argv):
    force = "--force" in argv
    send = "--send" in argv
    today = date.today()
    if today.weekday() != 0 and not force:
        print(f"[skip] 월요일 아님({today}) — 초안 생성 안 함")
        return 0

    text = build_draft(today)
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    out = DRAFT_DIR / f"weekly_report_{today.strftime('%Y%m%d')}.md"
    out.write_text(text + "\n", encoding="utf-8")
    print(f"[ok] 초안 저장 {out}")

    if send:
        sys.path.insert(0, str(ROOT / "wellperion-agents"))
        from telegram_notifier import TelegramNotifier  # 기존 관문(L21)
        TelegramNotifier().send(text)
        print("[ok] 업무 보고 방 발신 완료")
    else:
        print(text)
    return 0


def _self_check():
    # 최소 자가검증 — 발송 없음. 4항목 헤더가 모두 있어야 한다.
    text = build_draft(date(2026, 9, 7))
    for token in ("① 전결 처리 건", "② 회장님 판단", "③ 지적사항", "④ 다음 주 예정", "자료 대기"):
        assert token in text, token
    print("[self-check ok]")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
    else:
        sys.exit(main(sys.argv[1:]))
