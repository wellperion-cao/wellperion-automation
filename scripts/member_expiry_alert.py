# -*- coding: utf-8 -*-
"""
회원 만료 임박(익월 종료일자 기준 만기자) 텔레그램 알림 — 배9253(시포→시토 인계).
2026-07-20 GM 확정: 시포 스펙 채택 — 매월 1회(4주차 첫 월요일), 익월(발송월+1)
종료일자 기준 만기자 전원 대상(잔여일 0~30 주간필터 방식은 폐기).

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
   있다(GM 확인, 2026-07-20). 이를 실제 강사 이름으로 오인하면 강사별 묶음 통계가
   오염된다 — _normalize_owner() 로 빈값과 동일하게 처리한다.

GM 절대 제약:
- 연락처(휴대폰) 어떤 필드도 메시지에 포함 금지.
- 발송 대상은 GM 개인방(8254867551) 한 곳만 — 실무진 방 발송·다른 chat_id 인자 없음.
"""
from __future__ import annotations

import argparse
import html
import re
from collections import defaultdict
from datetime import datetime

import requests

from cpo_report import GM_CHAT_ID, TELEGRAM_TOKEN, _gas_get, render_header, _today_str

try:  # 발신 공용 로깅·페이싱(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import log_outbound, pace
except Exception:
    def log_outbound(*a, **k):
        pass

    def pace(*a, **k):
        return None

# ── 유효회원 시트(GAS member_active_list) 리터럴 헤더 키 — 정확일치 전용 ────────
NAME_KEY = "회원명"
END_KEY = "종료\n일자"  # 익월 만기자 필터 기준(잔여일 역산 금지 — GM 지시)

# 강습 종목(표시명) → 유효회원 시트 담당자 헤더(정확일치). P.L 담당자 = 필라테스.
SUBJECT_TEACHER_KEYS = [
    ("PT", "PT 담당자"),
    ("골프", "골프 담당자"),
    ("필라테스", "P.L 담당자"),
    ("스쿼시", "스쿼시 담당자"),
    ("수영", "수영 담당자"),
]

# 담당자 칸에 실제로 들어있는 '미배정' 표기 변형(빈값과 동일 취급).
_UNASSIGNED_MARKERS = {"", "담당자x", "-", "미정", "미배정", "tbd", "n/a"}

_TG_LIMIT = 4096
_FOOTER = "시포 · 월 1회(4주차 월요일) 정기 발송 예정 · 이번은 테스트"


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
    """익월(발송월+1) 종료일자('종료\\n일자' 정확일치) 시작 문자열과 일치하는 유효회원 전원.
    조회 실패 시 None(정직 실패 신호)."""
    data = _gas_get("member_active_list", {"scope": "valid"})
    if data is None:
        return None
    next_month = _next_month_str(datetime.strptime(today, "%Y-%m-%d"))
    rows = [r for r in data.get("data", []) if str(r.get(END_KEY) or "").strip().startswith(next_month)]
    rows.sort(key=lambda r: str(r.get(END_KEY) or ""))
    return next_month, rows


def _end_day(row: dict) -> int:
    """'종료\\n일자'(yyyy-mm-dd) 의 일(day) 부분. 파싱 불가 시 31(하순 버킷으로 안전 폴백)."""
    v = str(row.get(END_KEY) or "").strip()
    parts = v.split("-")
    if len(parts) == 3:
        try:
            return int(parts[2])
        except ValueError:
            pass
    return 31


def _member_lessons(row: dict) -> list[tuple[str, str]]:
    """회원의 강습 종목·담당강사 목록(정규화 후 실제 배정된 종목만)."""
    out = []
    for subject, key in SUBJECT_TEACHER_KEYS:
        teacher = _normalize_owner(row.get(key))
        if teacher:
            out.append((subject, teacher))
    return out


def _lessons_str(row: dict) -> str:
    lessons = _member_lessons(row)
    if not lessons:
        return "담당자 미배정"
    return " · ".join(f"{html.escape(subj)}({html.escape(teacher)})" for subj, teacher in lessons)


def _teacher_groups(rows: list[dict]) -> dict[str, list[tuple[str, str]]]:
    """대상 회원을 담당강사별로 묶는다. {강사명: [(회원명, 종목), ...]}"""
    groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in rows:
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
        "· 담당자 미배정 회원은 재등록 컨택이 아예 누락될 위험이 가장 크니 최우선으로 처리하세요.",
    ]


def build_report(today: str | None = None, abbreviate_teacher_groups: bool = False) -> str:
    today = today or _today_str()
    header = render_header("🔔", "AI CPO-시포", "회원 만료 임박 알림(익월 만기)", today)

    fetched = fetch_next_month_expiring(today)
    if fetched is None:
        return (
            f"{header}\n\n⚠️ 데이터 없음 — 유효회원 조회 실패(GAS 응답 없음). 잠시 후 재시도 필요.\n\n{_FOOTER}"
        )
    next_month, rows = fetched
    total = len(rows)

    unassigned = [r for r in rows if not _member_lessons(r)]
    early = [r for r in rows if _end_day(r) <= 10]      # 초순(1~10일 종료) — 가장 먼저 만기, 최우선 컨택
    mid = [r for r in rows if 11 <= _end_day(r) <= 20]  # 중순(11~20일 종료)
    late = [r for r in rows if _end_day(r) >= 21]       # 하순(21일~월말 종료)

    lines = [
        header,
        "",
        f"대상: {next_month} 종료 예정 회원 {total}명",
        "",
        "※ 신규·재등록 상담 담당 = 임정은",
        "",
    ]

    lines.append(f"<b>⚠️ 담당자 미배정 {len(unassigned)}명</b>")
    if not unassigned:
        lines.append("없음(전원 강습 담당강사 배정 확인)")
    else:
        for r in unassigned:
            name = html.escape(str(r.get(NAME_KEY) or "(이름없음)").strip())
            end_v = html.escape(str(r.get(END_KEY) or "").strip())
            lines.append(f"· {name} ({end_v} 종료)")

    lines.append("")
    lines.append(f"<b>🔴 초순 만기 (다음달 1~10일 종료) 상세 명단 {len(early)}명</b>")
    if not early:
        lines.append("없음")
    for r in early:
        end_v = str(r.get(END_KEY) or "").strip()
        day_label = end_v[5:] if len(end_v) == 10 else "?"  # "MM-DD"
        name = html.escape(str(r.get(NAME_KEY) or "(이름없음)").strip())
        lines.append(f"{day_label} {name} — {_lessons_str(r)}")

    lines.append("")
    lines.append("<b>🏃 강사별 묶음 (초순 만기)</b>")
    groups = _teacher_groups(early)
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
    lines.append(f"📅 중순(11~20일 종료) {len(mid)}명 · 하순(21일~월말 종료) {len(late)}명 (명단 생략)")
    lines.append("")
    lines.extend(_tips_section())
    lines.append("")
    lines.append(_FOOTER)
    return "\n".join(lines)


def build_report_within_limit(today: str | None = None) -> str:
    """4096자 한도 초과 시 초순 상세명단은 유지하고 강사별 묶음을 축약(인원수만)."""
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
        description="회원 만료 임박(익월 종료일자 기준) 알림 — 기본은 렌더만(발신 안 함)."
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
