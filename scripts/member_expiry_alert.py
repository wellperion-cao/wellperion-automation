# -*- coding: utf-8 -*-
"""
회원 만료 임박(잔여일 0~30일) 텔레그램 알림 — 배9253(시포→시토 인계, GM 수정지시 반영).

기존 인프라 재활용(맨땅 신축 금지):
- 데이터: GAS action `member_active_list&scope=valid` (구현 .deploy-funnel-v2/Survey.js:3855-3949).
- 조회 헬퍼·Exec URL: scripts/cpo_report.py 의 _gas_get()/FUNNEL_EXEC_URL 재사용(신규 작성 금지).
- 발송: telegram_bot 계열과 동일한 requests.post(sendMessage) 패턴 + scripts/tg_outbound_log.py
  의 pace()/log_outbound() 로 전역 페이싱·로깅에 편입.

⚠️ gviz 직독 금지(유효회원 탭 숨김열로 헤더 깨짐) — 반드시 GAS action 경유.
⚠️ 헤더 매칭 = 정확일치만 사용(ssot/incidents.json INC-020 계열 버그 재발 방지).
   GAS 응답 data[] 의 각 행은 시트 원본 헤더 문자열(줄바꿈 포함)을 키로 그대로 반환하므로,
   Survey.js:3904 _aaIdx() 같은 indexOf 부분일치 재구현 없이 리터럴 키로 바로 접근한다.

GM 절대 제약:
- 연락처(휴대폰) 어떤 필드도 메시지에 포함 금지.
- 발송 대상은 GM 개인방(8254867551) 한 곳만 — 실무진 방 발송·예약 등록 금지(본 스크립트는 하지 않음).
"""
from __future__ import annotations

import argparse
import html
import re
from collections import defaultdict
from pathlib import Path

import requests

from cpo_report import GM_CHAT_ID, TELEGRAM_TOKEN, _gas_get, render_header, _today_str

try:  # 발신 공용 로깅·페이싱(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import log_outbound, pace
except Exception:
    def log_outbound(*a, **k):
        pass

    def pace(*a, **k):
        return None

REPO_ROOT = Path(__file__).resolve().parent.parent

# ── 유효회원 시트(GAS member_active_list) 리터럴 헤더 키 — 정확일치 전용 ────────
NAME_KEY = "회원명"
REM_KEY = "잔여일\n(일)"
CONSULT_DATE_KEY = "재등록상담 날짜"
CONSULT_NOTE_KEY = "재등록상담 내용"
OPS_NOTE_KEY = "비고(운영부 참고사항)"
LESSON_NOTE_KEY = "강습팀\n참고사항(이용 시간 기록)"

# 강습 종목(표시명) → 유효회원 시트 담당자 헤더(정확일치). P.L 담당자 = 필라테스.
SUBJECT_TEACHER_KEYS = [
    ("PT", "PT 담당자"),
    ("골프", "골프 담당자"),
    ("필라테스", "P.L 담당자"),
    ("스쿼시", "스쿼시 담당자"),
    ("수영", "수영 담당자"),
]

_TG_LIMIT = 4096
_FOOTER = "시포 · 주 1회(월) 정기 발송 예정 · 이번은 테스트"


def _parse_rem(v) -> int | None:
    """'잔여일\n(일)' 원본 값(숫자·콤마·공백 섞임 가능)을 정수로. 파싱 불가 시 None(정직 제외)."""
    s = re.sub(r"[^0-9\-]", "", str(v or ""))
    if s in ("", "-"):
        return None
    try:
        return int(s)
    except ValueError:
        return None


def fetch_expiring_rows() -> list[tuple[int, dict]] | None:
    """유효회원(scope=valid) 중 0 < 잔여일 <= 30 인 행만, 잔여일 오름차순. 조회 실패 시 None."""
    data = _gas_get("member_active_list", {"scope": "valid"})
    if data is None:
        return None
    rows = data.get("data", [])
    out: list[tuple[int, dict]] = []
    for row in rows:
        rem = _parse_rem(row.get(REM_KEY))
        if rem is None or rem <= 0 or rem > 30:
            continue
        out.append((rem, row))
    out.sort(key=lambda x: x[0])
    return out


def _member_lessons(row: dict) -> list[tuple[str, str]]:
    """회원의 강습 종목·담당강사 목록(담당자 채워진 종목만)."""
    out = []
    for subject, key in SUBJECT_TEACHER_KEYS:
        teacher = str(row.get(key) or "").strip()
        if teacher:
            out.append((subject, teacher))
    return out


def _lessons_str(row: dict) -> str:
    lessons = _member_lessons(row)
    if not lessons:
        return "강습 없음"
    return " · ".join(f"{html.escape(subj)}({html.escape(teacher)})" for subj, teacher in lessons)


def _teacher_groups(d7_rows: list[tuple[int, dict]]) -> dict[str, list[tuple[str, str]]]:
    """D-7 이내 회원을 담당강사별로 묶는다. {강사명: [(회원명, 종목), ...]}"""
    groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for _rem, row in d7_rows:
        name = str(row.get(NAME_KEY) or "(이름없음)").strip()
        for subject, teacher in _member_lessons(row):
            groups[teacher].append((name, subject))
    return groups


def _tips_section() -> list[str]:
    """컨택 팁 — 유효회원 시트에 실제로 존재하는 필드에만 근거(최근 방문일·결제금액·구조화
    선호시간대는 시트에 없어 전제하지 않는다)."""
    return [
        "<b>💡 컨택 팁</b>",
        "· 강습 담당강사가 있는 회원은 강사가 수업 중 자연스럽게 재등록을 안내하는 편이 전화보다 응답률이 높습니다 — 강사별 묶음을 활용해 한 번에 요청하세요.",
        "· 재등록상담 날짜/내용 이력이 있는 회원은 그 내용부터 확인한 뒤 연락하세요(중복질문 방지).",
        "· 비고(운영부 참고사항)·강습팀 참고사항(이용 시간 기록)에 메모가 있으면 컨택 전 먼저 확인하세요.",
        "· 종목을 2개 이상 수강 중인 회원은 재등록 가능성이 높은 편이니 우선순위로 두세요.",
    ]


def build_report(today: str | None = None, abbreviate_teacher_groups: bool = False) -> str:
    today = today or _today_str()
    header = render_header("🔔", "AI CPO-시포", "회원 만료 임박 알림", today)

    expiring = fetch_expiring_rows()
    if expiring is None:
        return (
            f"{header}\n\n⚠️ 데이터 없음 — 유효회원 조회 실패(GAS 응답 없음). 잠시 후 재시도 필요.\n\n{_FOOTER}"
        )

    d7 = [x for x in expiring if x[0] <= 7]
    d8_14 = [x for x in expiring if 8 <= x[0] <= 14]
    d15_30 = [x for x in expiring if 15 <= x[0] <= 30]

    lines = [header, "", "※ 신규·재등록 상담 담당 = 임정은", ""]

    lines.append(f"<b>🔴 이번 주 연락 필요 (D-7 이내) {len(d7)}명</b>")
    if not d7:
        lines.append("없음")
    for rem, row in d7:
        name = html.escape(str(row.get(NAME_KEY) or "(이름없음)").strip())
        lines.append(f"D-{rem} {name} — {_lessons_str(row)}")

    lines.append("")
    lines.append("<b>🏃 강사별 묶음 (D-7 이내)</b>")
    groups = _teacher_groups(d7)
    if not groups:
        lines.append("없음")
    else:
        for teacher, members in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            t_esc = html.escape(teacher)
            if abbreviate_teacher_groups:
                lines.append(f"{t_esc} {len(members)}명")
            else:
                names_str = ", ".join(f"{html.escape(n)}({html.escape(s)})" for n, s in members)
                lines.append(f"{t_esc} {len(members)}명: {names_str}")

    lines.append("")
    lines.append(f"📅 D-8~14 {len(d8_14)}명 · D-15~30 {len(d15_30)}명 (명단 생략)")
    lines.append("")
    lines.extend(_tips_section())
    lines.append("")
    lines.append(_FOOTER)
    return "\n".join(lines)


def build_report_within_limit(today: str | None = None) -> str:
    """4096자 한도 초과 시 D-7 명단은 유지하고 강사별 묶음을 축약(인원수만)."""
    text = build_report(today, abbreviate_teacher_groups=False)
    if len(text) <= _TG_LIMIT:
        return text
    return build_report(today, abbreviate_teacher_groups=True)


def _send_telegram_html(chat_id: int, text: str) -> tuple[int | None, str | None]:
    """HTML parse_mode 발신. 성공 시 (message_id, None), 실패 시 (None, 에러메시지)."""
    if not TELEGRAM_TOKEN:
        return None, "TELEGRAM_BOT_TOKEN 미설정"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        pace()
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        data = resp.json()
        ok = resp.status_code == 200 and bool(data.get("ok"))
        log_outbound(text, chat_id=chat_id, source="member_expiry_alert", ok=ok, kind="sendMessage")
        if ok:
            return data.get("result", {}).get("message_id"), None
        return None, data.get("description") or f"http {resp.status_code}"
    except Exception as exc:  # noqa: BLE001 — 정직 실패 신호로 반환(지어내지 않음)
        log_outbound(text, chat_id=chat_id, source="member_expiry_alert", ok=False, kind="sendMessage")
        return None, str(exc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="회원 만료 임박(잔여일 0~30일) 알림 — 기본은 렌더만(발신 안 함)."
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="GM 개인방(8254867551)으로 실발신. 다른 chat_id는 받지 않는다(하드코딩 안전장치).",
    )
    args = parser.parse_args()

    text = build_report_within_limit()
    print(text)
    print(f"\n[길이] {len(text)}자")

    if args.send:
        msg_id, err = _send_telegram_html(GM_CHAT_ID, text)
        if msg_id is not None:
            print(f"\n[발신 성공] message_id={msg_id} chat_id={GM_CHAT_ID}")
        else:
            print(f"\n[발신 실패] {err}")
