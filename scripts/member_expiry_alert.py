# -*- coding: utf-8 -*-
"""
회원 만료 임박(익월 종료일자 기준 만기자) 텔레그램 알림 — 배9253(시포→시토 인계).
2026-07-20 GM 확정: 시포 스펙 채택 — 매월 1회(4주차 첫 월요일), 익월(발송월+1)
종료일자 기준 만기자 전원 대상(잔여일 0~30 주간필터 방식은 폐기).

2026-07-20 GM 최종 결정 — 명단은 페이지로, 텔레그램은 요약+링크로:
회원 명단(이름·종목·강사)은 `3. 웰페리온 가이드/cpo/member/renewal.html` 의 새 패널
('이번 재등록 대상', PIN 게이트 뒤)에서 라이브로 보여준다. 이 스크립트는 더 이상 명단을
텔레그램에 싣지 않는다 — 요약 숫자 1줄 + 대시보드 링크만 발송(단일 메시지, 분할 로직 불필요).
동시에 페이지가 읽을 **집계 숫자 전용**(PII 없음) 스냅샷을 status/member_expiry_summary.json
으로 떨어뜨린다 — 페이지·텔레그램 두 표면이 같은 숫자를 쓰게 해 판정 기준이 갈리지 않게 한다.
⚠️ 상세 명단(이름 포함)은 이 JSON에 넣지 않는다 — 이 파일은 GitHub Pages/raw.githubusercontent
로 누구나 인증 없이 받을 수 있어, PII를 넣으면 그게 곧 무인증 공개가 된다(페이지 쪽 PIN 게이트가
막아도 소용없음 — 원본 파일 자체가 공개 URL이므로). 상세 명단은 페이지가 PIN 통과 후 funnel GAS
에서 직접(라이브) 받아온다 — renewal.html 참고.

기존 인프라 재활용(맨땅 신축 금지):
- 데이터: GAS action `member_active_list&scope=valid` (구현 .deploy-funnel-v2/Survey.js:3855-3949).
- 조회 헬퍼·Exec URL: scripts/cpo_report.py 의 _gas_get()/FUNNEL_EXEC_URL 재사용(신규 작성 금지).
- 발송: telegram_bot 계열과 동일한 requests.post(sendMessage) 패턴 + scripts/tg_outbound_log.py
  의 pace()/log_outbound() 로 전역 페이싱·로깅에 편입.

⚠️ gviz 직독 금지(유효회원 탭 숨김열로 헤더 깨짐) — 반드시 GAS action 경유.
⚠️ 헤더 매칭 = 정확일치만 사용(ssot/incidents.json INC-020 계열 버그 재발 방지).
   GAS 응답 data[] 의 각 행은 시트 원본 헤더 문자열(줄바꿈 포함)을 키로 그대로 반환하므로,
   Survey.js:3904 _aaIdx() 같은 indexOf 부분일치 재구현 없이 리터럴 키로 바로 접근한다.
⚠️ 담당자 칸에는 빈 값 외에 '담당자 X' 같은 플레이스홀더 문자열이 실제로 들어있는 행이
   있다(GM 확인, 2026-07-20). 이를 실제 강사 이름으로 오인하면 통계가 오염된다 —
   _normalize_owner() 로 빈값과 동일하게 처리한다. renewal.html 의 JS 도 이 필터·정규화
   규칙을 그대로 미러링해야 한다(판정 기준이 두 곳에서 갈리면 사고 — 약속 L01).
⚠️ 컨택완료 판정 = 새 칸을 만들지 않고 기존 '재등록상담 날짜'/'재등록상담 내용' 값 존재
   여부로만 판단한다(GM 지시, 2026-07-20).

GM 절대 제약:
- 연락처(휴대폰) 어떤 필드도 메시지·요약 JSON에 포함 금지.
- 발송 대상은 GM 개인방(8254867551) 한 곳만 — 실무진 방 발송·다른 chat_id 인자 없음.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import requests

from cpo_report import GM_CHAT_ID, TELEGRAM_TOKEN, _gas_get, _today_str

try:  # 발신 관문(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import send as _tg_send
except Exception:
    def _tg_send(*a, **k):
        return False

REPO_ROOT = Path(__file__).resolve().parent.parent
SUMMARY_PATH = REPO_ROOT / "status" / "member_expiry_summary.json"
DASHBOARD_URL = "https://wellperion-cao.github.io/wellperion-automation/cpo/member/renewal.html"

# ── 유효회원 시트(GAS member_active_list) 리터럴 헤더 키 — 정확일치 전용 ────────
NAME_KEY = "회원명"
END_KEY = "종료\n일자"       # 익월 만기자 필터 기준(잔여일 역산 금지 — GM 지시)
OWNER_KEY = "담당자"         # A열, 멤버십(신규·재등록 상담) 담당
CONTACT_DATE_KEY = "재등록상담 날짜"
CONTACT_NOTE_KEY = "재등록상담 내용"

# 강습 종목(표시명) → 유효회원 시트 담당자 헤더(정확일치). P.L 담당자 = 필라테스.
SUBJECT_TEACHER_KEYS = [
    ("PT", "PT 담당자"),
    ("골프", "골프 담당자"),
    ("필라테스", "P.L 담당자"),
    ("스쿼시", "스쿼시 담당자"),
    ("수영", "수영 담당자"),
]

# 담당자 칸에 실제로 들어있는 '미배정' 표기 변형(빈값과 동일 취급). renewal.html JS 미러링 대상.
_UNASSIGNED_MARKERS = {"", "담당자x", "-", "미정", "미배정", "tbd", "n/a"}

_FOOTER = "시포 · 월 1회(4주차 월요일) 정기 발송"


def _normalize_owner(v) -> str:
    """담당자 셀 값 정규화 — 빈값·'담당자 X'류 플레이스홀더를 전부 미배정('')으로 접는다."""
    s = str(v or "").strip()
    if not s:
        return ""
    compact = re.sub(r"\s+", "", s).lower()
    if compact in _UNASSIGNED_MARKERS:
        return ""
    return s


def _next_month_str(today: datetime) -> str:
    y, m = today.year, today.month + 1
    if m > 12:
        y, m = y + 1, 1
    return f"{y:04d}-{m:02d}"


def fetch_next_month_expiring(today: str) -> tuple[str, list[dict]] | None:
    """익월(발송월+1) 종료일자('종료\\n일자' 정확일치) 시작 문자열과 일치하는 유효회원 전원,
    종료일자 오름차순. 조회 실패 시 None(정직 실패 신호)."""
    data = _gas_get("member_active_list", {"scope": "valid"})
    if data is None:
        return None
    next_month = _next_month_str(datetime.strptime(today, "%Y-%m-%d"))
    rows = [r for r in data.get("data", []) if str(r.get(END_KEY) or "").strip().startswith(next_month)]
    rows.sort(key=lambda r: str(r.get(END_KEY) or ""))
    return next_month, rows


def _member_lessons(row: dict) -> list[tuple[str, str]]:
    """회원의 강습 종목·담당강사 목록(정규화 후 실제 배정된 종목만)."""
    out = []
    for subject, key in SUBJECT_TEACHER_KEYS:
        teacher = _normalize_owner(row.get(key))
        if teacher:
            out.append((subject, teacher))
    return out


def _is_contacted(row: dict) -> bool:
    """컨택완료 판정 — '재등록상담 날짜' 또는 '재등록상담 내용' 값이 하나라도 있으면 컨택완."""
    return bool(str(row.get(CONTACT_DATE_KEY) or "").strip()) or bool(str(row.get(CONTACT_NOTE_KEY) or "").strip())


def compute_summary(today: str | None = None) -> dict | None:
    """텔레그램 요약·renewal.html 공개 스냅샷 양쪽이 함께 쓰는 집계(PII 없음). 조회 실패 시 None."""
    today = today or _today_str()
    fetched = fetch_next_month_expiring(today)
    if fetched is None:
        return None
    next_month, rows = fetched

    by_owner: dict[str, int] = {}
    for r in rows:
        owner = _normalize_owner(r.get(OWNER_KEY)) or "미배정"
        by_owner[owner] = by_owner.get(owner, 0) + 1

    unassigned_lesson = sum(1 for r in rows if not _member_lessons(r))
    uncontacted = sum(1 for r in rows if not _is_contacted(r))

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "next_month": next_month,
        "total": len(rows),
        "uncontacted": uncontacted,
        "unassigned_lesson_count": unassigned_lesson,
        "by_owner": by_owner,
        "dashboard_url": DASHBOARD_URL,
    }


def write_summary_json(summary: dict) -> Path:
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _push_summary()
    return SUMMARY_PATH


def _push_summary() -> None:
    """재등록 화면은 이 파일을 저장소(raw.githubusercontent)에서 읽는다 — 커밋하지 않으면
    내 PC에만 남고 화면은 옛 숫자를 계속 보여준다(약속 L13).

    실사고 2026-08-26: 로컬은 08-24 값(66명)이었는데 저장소는 08-08(65명)에 멈춰 있어
    재등록 화면이 18일째 옛 집계를 띄우고 있었다. 이 스크립트에 커밋 배선이 아예 없었다.
    새 도구를 만들지 않고 기존 커밋 관문(safe_commit)만 부른다(약속 L21).
    커밋 실패가 알림 발송을 막지 않는다 — 조용히 넘어가되 흔적은 남긴다.
    """
    import subprocess
    try:
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "safe_commit.py"),
             "-m", "chore(cpo): 재등록 대상 집계 갱신 (member_expiry_alert)",
             "--", "status/member_expiry_summary.json"],
            cwd=str(REPO_ROOT), capture_output=True, timeout=180,
        )
    except Exception as e:
        print(f"[warn] 집계 커밋 실패 — 화면은 옛 값을 볼 수 있다: {e}")


def build_message(today: str | None = None) -> str:
    """단일 요약 메시지(명단 없음) — 명단은 renewal.html 대시보드 링크로 위임."""
    today = today or _today_str()
    summary = compute_summary(today)
    if summary is None:
        return (
            "🔔 [AI CPO-시포] 재등록 컨택 대상\n\n"
            "⚠️ 데이터 없음 — 유효회원 조회 실패(GAS 응답 없음). 잠시 후 재시도 필요.\n\n"
            f"{_FOOTER}"
        )
    lines = [
        f"🔔 [AI CPO-시포] 재등록 컨택 대상 · {summary['next_month']} 만기",
        f"대상 {summary['total']}명 · 미컨택 {summary['uncontacted']}명",
        "※ 신규·재등록 상담 담당 = 임정은",
        f"⚠️ 담당자 미배정 {summary['unassigned_lesson_count']}명",
        f"👉 명단 보기: {DASHBOARD_URL}",
        _FOOTER,
    ]
    return "\n".join(lines)


def _send_telegram(chat_id: int, text: str) -> tuple[int | None, str | None]:
    """단순 텍스트 발신(요약 메시지는 HTML 마크업 불필요). 성공 시 (message_id, None)."""
    if not TELEGRAM_TOKEN:
        return None, "TELEGRAM_BOT_TOKEN 미설정"
    try:
        ok = _tg_send(TELEGRAM_TOKEN, chat_id, text, source="member_expiry_alert", timeout=15)
        if ok:
            return None, None  # 관문은 message_id를 반환하지 않음 — 호출부는 성공 신호만 사용
        return None, "발송 실패"
    except Exception as exc:  # noqa: BLE001 — 정직 실패 신호로 반환(지어내지 않음)
        return None, str(exc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="회원 만료 임박(익월 종료일자 기준) 요약 알림 — 기본은 렌더+스냅샷 기록만(발신 안 함)."
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="GM 개인방(8254867551)으로 실발신. 다른 chat_id는 받지 않는다(하드코딩 안전장치).",
    )
    args = parser.parse_args()

    today_str = _today_str()
    summary = compute_summary(today_str)
    text = build_message(today_str)
    print(text)
    print(f"\n[길이] {len(text)}자")

    if summary is not None:
        path = write_summary_json(summary)
        print(f"\n[스냅샷 기록] {path}")
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.send:
        _, err = _send_telegram(GM_CHAT_ID, text)
        if err is None:
            print(f"\n[발신 성공] chat_id={GM_CHAT_ID}")
        else:
            print(f"\n[발신 실패] {err}")
