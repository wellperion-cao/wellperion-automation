#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★운영부 아침 다이제스트 발송 — send_ops_digest.py (2026-07-14 CTO, 배906 · GM go 발효)

ops_daily_digest.py가 만든 _pending_digest.json 메시지를 카톡 ★운영부 방에 발송한다.
아침 파이프라인 마지막 단계(내보내기→다이제스트 생성→[이 단계]발송).

킬스위치(역롤백): status/ops_digest_send.json {"enabled": true/false}.
  enabled != true 이면 아무 것도 안 하고 로그만 남기고 exit 0(무인 발송 중단).
중복방지: _pending_digest.json 의 sent==false 이고 generated_at 이 '오늘'일 때만 발송.
  발송 성공 시 sent=true 로 마킹(같은 회차 재발송 방지). 생성 실패로 옛 다이제스트가
  남아있으면(generated_at 이 오늘 아님) 발송하지 않는다(어제분 재발송 사고 방지).

발송=kakao_report_sender.py --message --only-room '★ 운영부' 재사용(밤 점검공유와 동일 경로).
★개인정보: 다이제스트 원문은 gitignore된 아카이브에만. 이 스크립트·산출물 커밋 안 함.

[2026-08-05 추가 · 2026-08-11 이관] '사람이 처리할 배 전달'(각 배 staff_message)은
이제 build_mgr_daily_brief()의 '열린 요청' 절이 싣는다(★중간관리자 통합본, 배238·544).
델타 비교·RELAY_SHOW_N=5 상한은 그대로 재사용 — 새로 생기거나 바뀐 것만, 목록이
지난번과 같으면 그 절은 빈다. 자세한 이유는 아래 '사람에게 넘기는 배 전달' 주석 블록 참조.

[2026-08-06 추가] 업무 시트(S3)에서 상태가 '완료'로 바뀐 운영부 담당 건을 다이제스트
본문 끝에 "✅ 완료된 일" 절로 붙인다(GM 지시). ★한계: 카톡 발송은 이 PC 예약 시각에만
돈다(데스크톱 카카오톡 직접 조작 구조라 서버 즉시발송 불가) — 완료 체크 즉시가 아니라
다음 다이제스트 발송 회차에 묶여 나간다.

사용:
  python scripts/send_ops_digest.py            # 킬스위치 ON이면 발송
  python scripts/send_ops_digest.py --force    # 킬스위치·오늘조건 무시(수동 검증 발송)
  python scripts/send_ops_digest.py --dry-run  # 미발송(렌더·판정만)
  python scripts/send_ops_digest.py --relay-preview  # 배 전달 본문만 렌더(방에 손 안 댐)
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SENDER = ROOT / "scripts" / "kakao_report_sender.py"
PENDING = ROOT / "1. AI자료_아카이브" / "11_카카오톡" / "★운영부" / "_pending_digest.json"
# 배536(2026-08-11) — ops_daily_digest.py --room "★중간관리자" 가 만드는 그 방 전용 대화 정리.
MGR_PENDING = ROOT / "1. AI자료_아카이브" / "11_카카오톡" / "★중간관리자" / "_pending_digest.json"
KILL_SWITCH = ROOT / "status" / "ops_digest_send.json"
# 배 11070(웰리 ①) — 이 스크립트가 순서대로 여는 방들이 한 스케줄에 몰려 카톡 알림이
# 겹쳐 보였다. ★2026-08-29 GM 확정(배826 재승인)으로 상대 시차(5분씩 밀리기)를
# 절대시각으로 바꿨다 — 예약 실행(07:30)이 늦어져도 각 통은 자기 시각에 나간다.
# 순서·시각: 4부서방 07:40 → ★운영부 07:45 → ★중간관리자 07:50 → ★부서장 07:55.
# 이미 그 시각이 지났으면(앞 단계가 늦어졌으면) 기다리지 않고 바로 보낸다 —
# 다음날까지 기다리는 사고를 막는다(_seconds_until 참고).
# ▸예약 실행(Wellperion-Ops-Morning-Digest-0730)은 07:30 그대로 둔다 — 안 옮겼다. 이 파일
#   앞에서 카톡방 내보내기·다이제스트 생성이 먼저 도는데(ops_morning_digest.bat), 실측
#   (2026-08-25~29 로그)으로 그 준비가 매일 07:37 안쪽에 끝났다 — 첫 목표(07:40)까지 여유가
#   있다. 07:40으로 옮기면 준비가 하루라도 오래 걸리는 날 07:40 자체를 넘겨버려 GM 안의
#   기준시각이 그날그날 달라진다. 07:30 그대로 + 지난 시각은 즉시발송(위 주석)이 더 안전하다.
MORNING_SEND_TIMES = {
    "4부서방": (7, 40),      # ★운영+시설+지원+주차 (foursplit)
    "★운영부": (7, 45),
    "★중간관리자": (7, 50),
    "★부서장": (7, 55),
    # 📅 다가오는 일정 별도 통(GM 지시 2026-08-29 "별도로 만들자 전사일정링크를 태워서") —
    # 아침 4통 리듬(5분 간격)이 끝난 직후, 08:00 텔레그램 항로와 겹치기 전 07:58.
    "일정": (7, 58),
    # ★2026-09-01 GM 지시 — "전달 후 추가로(이어쓰지 말고 별도로) 꼭 진행해 달라는 당부와
    #   응원글도 남겨줘." 아침 통이 다 나간 뒤 별도 한 통. 본문에 붙이지 않는 이유가 있다 —
    #   당부·응원을 목록 꼬리에 이어 쓰면 목록의 일부로 읽혀 그냥 지나간다.
    "마무리인사": (8, 2),
}
# 📅 일정 통은 한 슬롯(07:58)에서 두 방(4부서방·★중간관리자)으로 연달아 나간다.
# 두 알림이 같은 초에 겹치지 않을 만큼만 벌린다. 아침 4통의 5분 간격을 여기 쓰면
# 두 번째 통이 08:00 텔레그램 항로와 겹쳐서 30초로 둔다.
# (2026-08-30 07:58 이 줄이 없어 NameError 로 두 번째 통이 유실되고 예약작업이 실패로 끝났다.)
SEND_STAGGER_SECONDS = 30
TARGET_ROOM = "★운영부"  # 2026-08-04 시토: SSOT(kakao_rooms.json)와 표기 일치(공백 제거) —
# 발송 자체는 _title_key 정규화로 공백 무관하게 동작하지만, 등록부 드리프트 체커가
# SSOT 표기와 다르면 CODE_ROOM_NOT_IN_SSOT로 매번 걸린다(발송 실패 아님 — 표기만 정합화).


ROOMS_CONFIG = ROOT / "scripts" / "kakao_rooms.json"

# ══════════════════════════════════════════════════════════════════════════
# 업무 시트 완료 알림 (2026-08-06 GM 지시 — "체크완료를 하면 카카오톡방에 완료되었다는
# 내용이 있으면 좋을듯" + "완료 알림은 완료 시 즉각 1회, 하루 일과 정리에서도 꼭 체크")
#
# 체크 자리는 새로 안 만든다 — 실무진이 이미 쓰는 업무 시트(S3 · action=todo_list)의
# '상태' 칸이 곧 체크 UI다. 아래 함수들은 그 칸이 '완료'로 바뀐 운영부 담당 건을 골라
# 두 자리에 흡수한다 — 새 스크립트·새 예약작업 없음:
#   ① 즉각 알림 — telegram_bot/daily_scheduler.py 가 10분 주기로 build_done_section
#      (아래)을 그대로 불러 새로 완료된 건만 ★운영부에 바로 보낸다. 아침 다이제스트
#      (이 파일 main())와 하트비트 스냅샷 하나(DONE_HEARTBEAT_ID)를 공유해 같은 건이
#      두 번 나가지 않는다.
#   ② 하루 일과 정리 — daily_scheduler.run_daily_digest 가 build_daily_done_section
#      (아래)으로 '오늘' 완료건 전체를 다시 모아 싣는다. 여기는 중복억제를 안 건다
#      (성격이 다르다 — 즉각=통보, 정리=하루치 요약. GM 지시).
# ══════════════════════════════════════════════════════════════════════════
DONE_HEARTBEAT_ID = "ops-digest-done-tasks"  # 지난 회차에 알린 완료건 스냅샷(상설 하트비트 1파일)
DONE_SHOW_N = 5
OPS_STAFF = ("최준용M", "이경연 실장", "윤병현AM")  # 운영부 담당자(GM 지시 원문 3인)

# 조용한 시간(22:00~08:00) — 즉각 완료 알림은 이 시간대엔 확인 자체를 건너뛴다(GM 상시
# 지시: 밤에는 보내지 않는다). 이 시간에 완료된 건은 스냅샷을 안 건드리므로 다음 날
# 08시 이후 첫 확인이나 아침 다이제스트가 자연히 집어간다 — 별도 이월 로직 불필요.
OPS_QUIET_START_HOUR = 22
OPS_QUIET_END_HOUR = 8


def in_ops_quiet_hours(hour: int) -> bool:
    """hour(0~23)가 조용한 시간대(22:00~08:00, 익일 포함)인가."""
    return hour >= OPS_QUIET_START_HOUR or hour < OPS_QUIET_END_HOUR


def _fetch_todo_rows() -> list:
    """업무 시트 전체 행 — 실패 시 빈 리스트(fail-soft, 다이제스트 발송을 막지 않는다)."""
    from collectors.ops_shared import SSOT_API_URL, gas_get
    resp = gas_get(SSOT_API_URL, {"action": "todo_list"}, label="todo_list")
    if resp is None:
        log("[done] 업무 시트 조회 실패 — 완료 절 생략")
        return []
    try:
        data = resp.json().get("data", [])
        return data if isinstance(data, list) else []
    except Exception as exc:
        log(f"[done] 업무 시트 파싱 실패 — 완료 절 생략: {exc}")
        return []


def _ops_done_rows(rows: list) -> list:
    """업무 시트 행 중 운영부 담당자(OPS_STAFF)의 완료건만 — build_done_section(즉각·
    아침)과 build_daily_done_section(하루 정리) 양쪽이 같은 필터를 공유한다(약속 L01)."""
    from collectors.ops_shared import TODO_DONE_STATUSES

    return [r for r in rows if isinstance(r, dict)
            and str(r.get("상태", "")).strip() in TODO_DONE_STATUSES
            and any(n in str(r.get("담당자", "")) for n in OPS_STAFF)
            and str(r.get("id", ""))]


def build_done_section(rows: list, prev_ids: dict, exclude_text: str = "") -> "tuple[str, dict]":
    """운영부 담당자(OPS_STAFF) 몫 중 상태='완료'인 건에서 지난 회차 이후 새로
    완료된 것만 골라 절로 만든다. 비교 키 = 시트 행 id 고정(업무명은 바뀔 수 있다 —
    relay 구간의 task_id 교훈과 동일). 반환 (섹션 텍스트, 현재 완료건 {id: 표시줄}) —
    두 번째 값은 변화가 없어도 다음 회차 비교용으로 그대로 저장한다.

    exclude_text — [2026-08-29 GM 지시 · 한 통 안 같은 건 두 번 금지] 본문(아침 요약)에
    업무명이 이미 언급된 완료건은 이 절에서 뺀다(실측: 「확인된 것 · 실장님 완료 — 환불
    운영기준」과 「✅ 완료된 일 · 환불 운영기준」이 같은 통에 두 번). 스냅샷(current)은
    전량 그대로 저장한다 — 다음 회차 비교가 틀어지지 않게."""
    done = _ops_done_rows(rows)
    current = {str(r["id"]): f"{str(r.get('업무명', '')).strip()} — {str(r.get('담당자', '')).strip()} 완료"
               for r in done}

    new_ids = [k for k in current if k not in prev_ids]
    if exclude_text:
        titles = {k: current[k].split(" — ")[0].strip() for k in new_ids}
        new_ids = [k for k in new_ids if not (titles[k] and titles[k] in exclude_text)]
    if not new_ids:
        return "", current

    lines = [f"✅ 완료된 일 {len(new_ids)}건"]
    for k in new_ids[:DONE_SHOW_N]:
        lines.append(f" • {current[k]}")
    if len(new_ids) > DONE_SHOW_N:
        lines.append(f" • 외 {len(new_ids) - DONE_SHOW_N}건")
    return "\n".join(lines), current


def build_daily_done_section(rows: list, date_str: str) -> str:
    """'하루 일과 정리'용 — date_str(YYYY-MM-DD)에 완료된 운영부 건 전체를 매번
    다시 모아 보여준다(중복억제 없음 — build_done_section 과 다른 용도: 즉각 알림으로
    이미 나갔어도 하루 정리엔 다시 싣는다, GM 지시). 완료 시각 = 시트 '수정일' 칸
    (hangro_board.build_work_block 의 '어제 완료(수정일=target_date)'와 동일 관례)."""
    done = [r for r in _ops_done_rows(rows) if str(r.get("수정일", "") or "").startswith(date_str)]
    if not done:
        return ""

    lines = [f"✅ 오늘 완료된 운영부 업무 {len(done)}건"]
    for r in done[:DONE_SHOW_N]:
        lines.append(f" • {str(r.get('업무명', '')).strip()} — {str(r.get('담당자', '')).strip()} 완료")
    if len(done) > DONE_SHOW_N:
        lines.append(f" • 외 {len(done) - DONE_SHOW_N}건")
    return "\n".join(lines)


# 실무진 피드백 시트의 작성자 칸은 직함 없이 이름만 들어온다(예 '이경연'). 방에 나갈 땐
# 직함을 붙인다 — 시트 값 자체는 고치지 않는다(GM 지시 2026-08-24).
FB_STAFF_TITLES = {
    "이경연": "이경연 실장", "최준용": "최준용M", "윤병현": "윤병현AM",
    "임정은": "임정은M", "백승화": "백승화 사원",
}


def _fb_staff_title(name: str) -> str:
    name = (name or "").strip()
    return FB_STAFF_TITLES.get(name, name)


def build_daily_feedback_done_section(date_str: str) -> str:
    """'하루 일과 정리'용 — date_str 에 '처리완료'로 닫힌 실무진 피드백을 묶어 보여준다
    (GM 지시 2026-08-24 · 세 갈래 중 '하루 1회 묶음' 선택). 판정 = 처리상태가 '처리완료'로
    시작 + 처리메모 앞머리 날짜 도장이 그날. 브로제이 건은 외부 업체 몫이라 뺀다.
    한계: 처리메모에 날짜 도장이 없는 건(사람이 시트에서 메모만 손으로 쓴 경우)은 안 잡힌다."""
    try:
        from collectors.cpo_staff_feedback_watch import fetch_feedback
        rows, err = fetch_feedback()
    except Exception as exc:
        log(f"[fbdone] 실무진 피드백 조회 예외 — 절 생략: {exc}")
        return ""
    if err or not rows:
        if err:
            log(f"[fbdone] 실무진 피드백 조회 실패 — 절 생략: {err}")
        return ""

    done = [r for r in rows if isinstance(r, dict)
            and str(r.get("처리상태", "")).strip().startswith("처리완료")
            and str(r.get("처리메모", "")).strip().startswith(f"[{date_str}")
            and str(r.get("업무 구분", "")).strip() != "브로제이"]
    if not done:
        return ""

    lines = [f"✅ 오늘 처리된 실무진 피드백 {len(done)}건"]
    for r in done[:DONE_SHOW_N]:
        gubun = str(r.get("업무 구분", "")).strip()
        body = " ".join(str(r.get("내용", "")).split())[:24]
        who = _fb_staff_title(str(r.get("작성자", "")))
        lines.append(f" • {gubun} — {body} ({who})")
    if len(done) > DONE_SHOW_N:
        lines.append(f" • 외 {len(done) - DONE_SHOW_N}건")
    return "\n".join(lines)


def _done_state() -> "tuple[dict, bool]":
    """(지난 회차 완료건 스냅샷, 최초실행 여부). 최초실행(하트비트 파일 자체가 없음)이면
    이번 회차는 알리지 않고 스냅샷만 찍는다 — 안 그러면 시트에 쌓여 있던 과거 완료건이
    전부 '신규 완료'로 한꺼번에 쏟아진다(relay 구간 _is_legacy_snapshot과 같은 문제)."""
    from module_heartbeat import last_heartbeat
    rec = last_heartbeat(DONE_HEARTBEAT_ID)
    if rec is None:
        return {}, True
    state = rec.get("state")
    return (dict(state) if isinstance(state, dict) else {}), False


def _save_done_state(state: dict) -> None:
    from module_heartbeat import record_heartbeat
    record_heartbeat(DONE_HEARTBEAT_ID,
                     detail=f"운영부 완료건 스냅샷 — {len(state)}건", extra={"state": state})


# ══════════════════════════════════════════════════════════════════════════
# 주간 보고 초안 (2026-08-06 GM 지시 — "표준 양식은 의미없고, 보고 내용을 중간관리자
# 방에다가 보고할 수 있거나 정리할 수 있게 도와줬으면"). 빈 양식표는 아무도 안 채운다
# — 이경연 실장이 손으로 안 써도 초안이 ★중간관리자 방에 나가고, 고치거나 그대로 쓴다.
# 담당자·완료 판정은 위 OPS_STAFF·_ops_done_rows 그대로 재사용(약속 L01) — 필터를
# 두 번 안 짠다. 발송 쪽(요일·시각·킬스위치)은 telegram_bot/daily_scheduler.py 가
# 이 함수를 불러 kakao_report_sender.py --only-room "★중간관리자"로 보낸다
# (새 스크립트·새 예약작업 없음, 약속 L21).
# ══════════════════════════════════════════════════════════════════════════
WEEKLY_STALE_DAYS = 7   # "오래 갱신이 없는" 기준 — worklog_gaps._STALE_DAYS(배9578)와 동일 관례
WEEKLY_SHOW_N = 8
WEEKLY_ROOM = "★중간관리자"


def _weekly_active_rows(rows: list) -> list:
    """운영부 담당(OPS_STAFF) 미완료·비보류 건 — _ops_done_rows 의 반대.
    '보류'를 뺀 것은 coo_registry.fetch_workapproval_status/rule_task_deadline_passed_active
    와 같은 관례(의도적으로 멈춰둔 것과 방치는 다르다)."""
    from collectors.ops_shared import TODO_DONE_STATUSES

    return [r for r in rows if isinstance(r, dict)
            and str(r.get("상태", "")).strip() not in TODO_DONE_STATUSES
            and str(r.get("상태", "")).strip() != "보류"
            and any(n in str(r.get("담당자", "")) for n in OPS_STAFF)
            and str(r.get("id", ""))]


def _parse_ymd(s):
    """업무 시트 날짜칸(YYYY-MM-DD 또는 ISO datetime) → date. 실패 시 None."""
    from datetime import date as _date
    try:
        return _date.fromisoformat(str(s or "")[:10])
    except Exception:
        return None


def build_weekly_report_draft(rows: list, today_str: str) -> str:
    """운영부 주간 보고 초안. ②진행 중(상태='진행중'·기한 안 지나고 최근 갱신) /
    ③멈춰 있는 것(기한 지남 또는 WEEKLY_STALE_DAYS일+ 무갱신) / ✅이번 주 끝난 것
    (이번 주 월요일 이후 완료). 빈 절은 안 넣는다 — 셋 다 비면 빈 문자열(발송 안 함)."""
    from datetime import date as _date, timedelta as _td

    today = _parse_ymd(today_str) or _date.today()
    week_start = today - _td(days=today.weekday())  # 이번 주 월요일

    progressing, stalled = [], []
    for r in _weekly_active_rows(rows):
        end = _parse_ymd(r.get("종료일"))
        upd = _parse_ymd(r.get("수정일"))
        overdue_days = (today - end).days if end and end < today else 0
        stale_days = None if upd is None else (today - upd).days
        if overdue_days > 0:
            stalled.append((r, f"기한 {overdue_days}일 초과", overdue_days))
        elif stale_days is None or stale_days >= WEEKLY_STALE_DAYS:
            tag = "갱신기록 없음" if stale_days is None else f"{stale_days}일째 무갱신"
            stalled.append((r, tag, stale_days if stale_days is not None else 9999))
        elif str(r.get("상태", "")).strip() == "진행중":
            deadline = end.isoformat() if end else "기한 미정"
            progressing.append((r, deadline))
    stalled.sort(key=lambda x: -x[2])

    done_this_week = [r for r in _ops_done_rows(rows)
                       if (_parse_ymd(r.get("수정일")) or _date.min) >= week_start]

    lines = ["📋 운영부 주간 보고 초안(자동 생성 — 확인 후 고쳐서 올려주세요)"]

    if progressing:
        lines.append(f"\n② 진행 중 {len(progressing)}건")
        for r, deadline in progressing[:WEEKLY_SHOW_N]:
            lines.append(f" • {str(r.get('업무명', '')).strip()} / {str(r.get('담당자', '')).strip()} / {deadline}")
        if len(progressing) > WEEKLY_SHOW_N:
            lines.append(f" • 외 {len(progressing) - WEEKLY_SHOW_N}건")

    if stalled:
        lines.append(f"\n③ 멈춰 있는 것 {len(stalled)}건")
        for r, tag, _age in stalled[:WEEKLY_SHOW_N]:
            lines.append(f" • {str(r.get('업무명', '')).strip()} / {str(r.get('담당자', '')).strip()} / {tag}")
        if len(stalled) > WEEKLY_SHOW_N:
            lines.append(f" • 외 {len(stalled) - WEEKLY_SHOW_N}건")

    if done_this_week:
        lines.append(f"\n✅ 이번 주 끝난 것 {len(done_this_week)}건")
        for r in done_this_week[:WEEKLY_SHOW_N]:
            lines.append(f" • {str(r.get('업무명', '')).strip()} — {str(r.get('담당자', '')).strip()}")
        if len(done_this_week) > WEEKLY_SHOW_N:
            lines.append(f" • 외 {len(done_this_week) - WEEKLY_SHOW_N}건")

    if not progressing and not stalled and not done_this_week:
        return ""

    if stalled:
        lines.append("\n👉 멈춘 건은 완료 처리 / 폐기 / 새 기한 중 하나로 정리해 주세요.")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════
# ★중간관리자 매일 결정거리 요약 (배469 · GM 확정 2026-08-08, 배선 2026-08-10)
#
# ★운영부(공유 전용)와 읽는 사람이 다르다(약속 L24) — 이경연 실장·이정헌 소장·나우열M·GM
# 은 판단·배정을 받는 방이다.
#
# ★2026-08-11 GM 지적으로 미해결 블록을 뺐다. GM 원문: "중간관리자방에도 운영자방처럼
# 어제 정리를 해주긴 했는데 내용이 톡방 내용정리가 아니라 미해결건이던데? 그건 따로
# 보내는걸로 알고 있는데?" — 맞다. 오래 묵은 미해결건은 이미 별도 발신이 담당한다
# (2026-08-10 11:48 웰리 「담당이 안 잡혀 멈춘 건들」 · 18:02 시토 「마감일 지난 업무
# 11건」). 여기서 또 내보내면 같은 방에 같은 목록이 두 번 간다.
#
# 그럼 이 자리에 무엇이 와야 하나 = ★운영부와 같은 「어제 그 방 대화 정리」다. 원문 수집·
# 대화 정리 배선은 시토 배536 — ops_daily_digest.py --room "★중간관리자" 가 그 방 폴더에
# _pending_digest.json 을 만든다(새 생성기 아님, 방 디렉터리만 갈아 끼운 기존 생성기).
# 이 함수는 그 message를 몸통으로 쓴다.
#
# 업무 시트 완료건 절은 2026-08-29 뺐다(카톡 중복 정리) — 같은 완료건이 ★운영부 아침 통에
# 나간다. 낼 게 없으면 빈 문자열 = 발송 안 함(GM 지시: 억지로 채우지 않는다).
#
# ★2026-08-11 웰리 — 세 번째 절 「열린 요청」 추가(배238·544). send_ops_digest 의
# 옛 사람전달(send_relays)이 2026-08-08 GM 지시로 꺼진 뒤, 각 배의 staff_message(예:
# "법정·정기점검 15건 실시일 확인해 주세요")가 3일째 어떤 방에도 안 나가고 있었다.
# 새 스냅샷·새 발신기를 만들지 않는다(약속 L21) — 이미 있던 relay_routes/
# build_relay_message(델타 비교·RELAY_SHOW_N=5 상한 포함)를 그대로 불러 절 하나로 붙인다.
# 상태 저장은 여기서 안 한다(미리보기가 상태를 건드리면 안 됨) — 실제 발송 성공 후
# main()이 relay_current를 저장한다.
# ══════════════════════════════════════════════════════════════════════════
MGR_DAILY_HEARTBEAT_ID = "mgr-daily-brief-sent"
# ★2026-08-26 웰리 실측(배 11039 ⑤ · 배 11070 ③) — 절이 하나씩 늘며 한 통이 35줄까지
# 나갔다. 카톡 한 통 10줄 안쪽이 GM 확정(2026-08-07)이라 25줄로 낮춘다.
# (구 25줄 상한 _cap_message_lines 은 2026-08-29 GM 결정으로 삭제 — "줄을 접는 게 아니라
#  안 끝난 건수를 줄여야 한다". 본문을 자르면 밀린 일이 안 보이게 될 뿐이다. 길이 조절은
#  건수 소진으로만 한다 · ★중간관리자 통이 유일한 사용처였다.)

# ══════════════════════════════════════════════════════════════════════════
# 📮 회신 부탁 절 (2026-08-15 GM 승인 · C안) — 물음은 나가는데 답을 세는 곳이 없어
# 미회신이 쌓이던 것(8/15 실측 14건)을, 이미 매일 나가는 ★중간관리자 아침 정리 끝에
# 절 하나로 흡수한다(약속 L21 — 새 스크립트·새 예약 0).
#
# 재료 = 그 방 원장(_digest_ledger.json · ops_daily_digest 가 매일 쌓는 이슈 목록).
# 어제(target_date)치 열린 건은 정리문의 ⚠️ 절이 이미 다루므로 여기선 **그 전날들** 것만 —
# 어제 대화에 다시 안 나와 ⚠️ 에서 빠졌지만 답도 안 온 건이 이 절의 몫이다.
#
# 'N일째'·'아직도'·'재요청' 금지 — 밀린 건 우리 사정이고 그 표기는 압박만 준다.
# ★2026-08-20 수리 — 이 절은 더 이상 따로 나가지 않는다. build_reply_nudge_items 가
# 항목만 돌려주면 build_asks_section 이 배 전달(relay)과 합쳐 한 절로 낸다(GM 지적 —
# 절 두 개·헤더 두 개가 따로 놀아 복잡했다). 되돌리기 = build_mgr_daily_brief 안의
# build_reply_nudge_items 호출 두 줄만 지우면 이 항목들이 사라진다.
# ══════════════════════════════════════════════════════════════════════════
MGR_LEDGER = MGR_PENDING.parent / "_digest_ledger.json"
NUDGE_LOOKBACK_DAYS = 7   # 이보다 오래된 건 원장에서 안 꺼낸다(오래 묵은 건 웰리가 사람으로 판단)
NUDGE_SHOW_N = 3          # 사람당 이 이상은 다음 회차로 — 길면 아무도 안 읽는다
# ★중간관리자 방 구성원(수신자). 담당이 운영부 실무진(윤병현AM 등)인 건은 약속 L24
# (운영부는 실장 경유)에 따라 이경연 실장 묶음에 싣되, 줄에 원 담당 이름을 남긴다.
_NUDGE_MEMBERS = ["이경연 실장", "이정헌 소장", "나우열M"]
# ★2026-08-28 GM 확정 역할(배 11070 ④) — 비품·소모품 구매·비치는 이정헌 소장 역할 3번이다.
# owner 가 세 사람 중 아무도 아니면(빈칸·방 이름 등) 옛 코드는 무조건 이경연 실장으로
# 떨어졌다 — 구매·비치 건도 실장 앞으로 잘못 쌓였다. 제목에 이 낱말이 있으면 소장으로 보낸다.
_NUDGE_FACILITY_KEYWORDS = ("구매", "비치")


def _nudge_norm(s: str) -> str:
    return re.sub(r"[\s·\-—()\[\]+/,.]+", "", str(s or ""))


def _nudge_similar(a: str, b: str) -> bool:
    """같은 건인가 — ops_daily_digest._schedule_is_dup 과 같은 규칙(포함 또는 0.6 유사)."""
    from difflib import SequenceMatcher
    na, nb = _nudge_norm(a), _nudge_norm(b)
    if not na or not nb:
        return False
    return na in nb or nb in na or SequenceMatcher(None, na, nb).ratio() >= 0.6


def build_reply_nudge_items(target_date: str) -> list:
    """전날들의 열린 건(담당 있음)을 항목 리스트로 돌려준다 — {"date","who","ask","how"}.
    build_asks_section 이 배 전달(relay) 항목과 합쳐 오래된 순으로 잘라 보여준다
    (2026-08-20 GM 지적 — 📌·📮 절이 각자 헤더·건수를 가져 복잡하던 것을 하나로 합쳤다).

    거르는 것: ①어제(target_date) 대화에 나온 건(⚠️/✅ 절이 담당) ②나중에 resolved 로
    닫힌 건 ③담당 빈칸(주인 없는 일은 사람한테 묻지 않는다 · 약속 L23) ④서로 닮은 중복
    (최신 문구만 남김). date = 이 창(window) 안에서 그 건이 처음 나온 날 — 오래 묵을수록
    먼저 보이게 한다."""
    try:
        ledger = json.loads(MGR_LEDGER.read_text(encoding="utf-8"))
        t = date.fromisoformat(target_date)
    except Exception:
        return []
    lo = (t - timedelta(days=NUDGE_LOOKBACK_DAYS - 1)).isoformat()
    window = [e for e in ledger
              if isinstance(e, dict) and lo <= str(e.get("date", "")) <= target_date]

    resolved_texts, today_texts = [], []
    earliest: dict = {}  # 정규화 제목 -> 이 창에서 처음 나온 날짜
    for e in sorted(window, key=lambda x: str(x.get("date", ""))):
        for it in e.get("issues") or []:
            title = str(it.get("issue") or "").strip()
            if not title:
                continue
            earliest.setdefault(_nudge_norm(title), str(e.get("date", "")))
            if str(it.get("status") or "") == "resolved":
                resolved_texts.append(title)
            if str(e.get("date", "")) == target_date:
                today_texts.append(title)

    kept: dict = {}  # member -> [{"title","owner","date"}], 최신 날짜부터 채운다
    for e in sorted(window, key=lambda x: str(x.get("date", "")), reverse=True):
        if str(e.get("date", "")) == target_date:
            continue
        for it in e.get("issues") or []:
            title = str(it.get("issue") or "").strip()
            owner = str(it.get("owner") or "").strip()
            if not title or not owner or str(it.get("status") or "") != "open":
                continue
            if any(_nudge_similar(title, x) for x in resolved_texts + today_texts):
                continue
            if owner in _NUDGE_MEMBERS:
                member = owner
            elif any(kw in title for kw in _NUDGE_FACILITY_KEYWORDS):
                member = "이정헌 소장"
            else:
                member = _NUDGE_MEMBERS[0]
            rows = kept.setdefault(member, [])
            if any(_nudge_similar(title, r["title"]) for r in rows):
                continue
            if len(rows) >= NUDGE_SHOW_N:
                continue
            rows.append({"title": title, "owner": owner,
                        "date": earliest.get(_nudge_norm(title), str(e.get("date", "")))})

    items = []
    for member, rows in kept.items():
        for r in rows:
            tag = f"({r['owner']} 건) " if r["owner"] != member else ""
            items.append({
                "date": r["date"],
                "who": member,
                "ask": _cap_line(tag + r["title"], ASKS_TITLE_CAP),
                "how": f"{member}님께 진행 중·완료·날짜 한 마디만 답해 주시면 됩니다.",
            })
    return items


def _mgr_conversation_message(target_date: str) -> str:
    """ops_daily_digest.py --room "★중간관리자" 가 만든 그 방 대화 정리 원문.
    MGR_PENDING의 date가 target_date와 다르면(생성 실패로 옛 회차가 남아있는 등) 빈 문자열 —
    옛 정리 재발송 사고 방지(배536 요건)."""
    if not MGR_PENDING.exists():
        return ""
    try:
        data = json.loads(MGR_PENDING.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if str(data.get("date", "")) != target_date:
        return ""
    return (data.get("message") or "").strip()


def build_mgr_daily_brief(rows: list, target_date: str) -> "tuple[str, dict]":
    """★중간관리자용 '어제 정리'. rows=업무 시트 전체 행(_fetch_todo_rows()).

    미해결건은 담지 않는다 — 별도 발신이 담당한다(2026-08-11 GM 지적, 위 주석 참조).
    반환 (message, relay_current) — relay_current 는 '열린 요청' 절의 이번 회차 스냅샷.
    빈 값이라도 항상 돌려준다(호출부가 상태 저장 여부를 스스로 결정)."""
    convo = _mgr_conversation_message(target_date)
    parts = [convo] if convo else []

    # [2026-08-29 GM 지시 · 카톡 중복 정리] 「✅ 어제 완료 N건」 절 삭제 — 같은 완료건이
    # ★운영부 아침 통(「✅ 완료된 일」 절 · _send_ops_room)에 이미 나간다. 두 방이 같은
    # 말을 반복하지 않는다. 대화 정리(convo)가 없는 날은 제목만이라도 세운다(빈 통 방지).
    done = [r for r in _ops_done_rows(rows) if str(r.get("수정일", "") or "").startswith(target_date)]
    if done and not convo:
        _, m, d = target_date.split("-")
        parts.append(f"🧭 {int(m)}/{int(d)} 어제 정리 — 판단·배정 필요한 것만")

    relay_state = _relay_state()
    _migrate_relay_state(relay_state)
    room, contacts = relay_routes()[0]
    relay_items, relay_current = build_relay_message(contacts, relay_state.get(room, {}))

    # 📌+📮 통합절(2026-08-20 GM 지적 수리) — 배 전달·회신 부탁을 하나로 합쳐 한 통
    # ASKS_TOTAL_CAP건만 보여준다(build_asks_section). 아래 두 줄만 지우면 절이 사라진다.
    nudge_items = build_reply_nudge_items(target_date)
    asks = build_asks_section(relay_items, nudge_items)
    if asks:
        parts.append(asks)

    # [2026-08-29 GM 결정] 25줄 상한으로 본문을 자르던 것 삭제 — "줄을 접는 게 아니라
    # 안 끝난 건수를 줄여야 한다". 넘쳐도 자르지 않는다(밀린 일이 안 보이게 되는 게 더 나쁘다).
    message = "\n\n".join(parts)
    # 📅 다가오는 일정은 이 통에 붙이지 않는다 — 별도 통(send_schedule_pings · 07:58)으로
    # 분리했다(GM 지시 2026-08-29 "별도로 만들자 전사일정링크를 태워서").
    return message, relay_current


def _mgr_already_sent(target_date: str) -> bool:
    from module_heartbeat import last_heartbeat
    rec = last_heartbeat(MGR_DAILY_HEARTBEAT_ID)
    return bool(rec) and (rec.get("state") or {}).get("date") == target_date


def _mark_mgr_sent(target_date: str) -> None:
    from module_heartbeat import record_heartbeat
    record_heartbeat(MGR_DAILY_HEARTBEAT_ID, detail=f"★중간관리자 결정거리 요약 발송 — {target_date}",
                     extra={"state": {"date": target_date}})


def preview_mgr_brief() -> int:
    """★중간관리자 결정거리 요약 미리보기 — 방에 손 안 댐(발신·상태기록 없음)."""
    target_date = ""
    if PENDING.exists():
        try:
            target_date = json.loads(PENDING.read_text(encoding="utf-8")).get("date", "")
        except Exception:
            pass
    if not target_date:
        from datetime import timedelta as _td
        target_date = (datetime.now() - _td(days=1)).strftime("%Y-%m-%d")
    message, _relay_current = build_mgr_daily_brief(_fetch_todo_rows(), target_date)
    print(f"\n===== {WEEKLY_ROOM} 결정거리 요약 ({target_date}) =====")
    print(message or "(보낼 내용 0건 — 발송 안 함)")
    return 0


# ══════════════════════════════════════════════════════════════════════════
# 사람에게 넘기는 배 전달 (2026-08-05 GM 편제 확정)
#
# 왜 필요한가. AI 로 도는 C-Level 은 웰리·시토·시모·시포 넷뿐이고, 시우·시로·시뽀의
# 배는 추적용으로 큐에 살아 있되 AI 가 실행하지 않는다. 그런데 그 배들이 사람에게
# 닿는 경로가 없었다 — safe_commit.py 의 방 안내는 "AI 가 그 도메인 파일을 고치려다
# 막혔을 때"만 뜨는 일회성 문구이고, ★운영부 아침 다이제스트의 업무 블록은 업무현황
# SSOT 시트(action=todo_list)를 읽지 status/_queue.json 을 읽지 않는다. 그래서 시우
# 12건·시로 3건이 아무에게도 전달되지 않은 채 큐에만 쌓였다.
#
# 왜 여기(send_ops_digest.py)인가. ops_daily_digest.py 는 ★운영부 한 방의 '본문을
# 만드는' 곳이라 ★중간관리자에는 애초에 닿지 못한다. 실제 배달은 이 스크립트가 하고,
# 이미 유일한 카톡 관문(kakao_report_sender.py --only-room)을 부르고 있어 방 하나를
# 더 도는 데 새 발신기·새 스크립트가 필요 없다. 발송이 확정된 뒤에만 중복방지 지문을
# 적을 수 있는 것도 여기뿐이다(본문 생성 시점에 적으면 GM 이 보류한 회차가 '보냄'으로
# 남아 다음 회차가 막힌다).
#
# 누구에게 어느 방인가 = safe_commit.DOMAIN_MODIFY_RULES 가 이미 정본이라 그대로
# 읽어 쓴다(같은 값을 두 곳에 두지 않는다 — 약속 L01).
# ══════════════════════════════════════════════════════════════════════════
QUEUE_PATH = ROOT / "status" / "_queue.json"
RELAY_OPEN_STATUSES = {"PENDING", "IN_PROGRESS"}
RELAY_TITLE_CAP = 0         # 0 = 자르지 않음(GM 지시 2026-08-30). 종전 34자
RELAY_HEARTBEAT_ID = "clevel-queue-human-relay"  # 지난 회차 목록 보관 = 상설 하트비트 1파일
RELAY_STALE_DAYS = 1  # 내용 안 바뀐 채 이만큼 묵으면 재알림 = 회신이 올 때까지 매일 다시 싣는다.
#   ★2026-08-25 GM 방침으로 7일 → 1일. GM 원문: "그냥 계속 푸시하면 안되는거야? 그리고
#   답변 오면 질문 삭제하고, 업무체크or완료 처리하면 될 것 같은데." 주간 주기에서는 회신이
#   안 오면 다음 알림까지 일주일이 비어 사실상 답을 못 받고 배만 열린 채 남았다.
#   ▸압박 표기는 여전히 금지다(§4-2-2) — 문구는 그대로 다시 실릴 뿐 'N일째'·'재요청' 같은
#     말은 붙지 않는다. 답이 와서 항목이 빠지면 그 줄만 사라지고, 배가 닫히면 목록에서 빠진다.
#   ▸ASKS_SHOW_N(한 통 5건)이 여전히 상한이라 매일 나가도 한 통 길이는 그대로다.
#   ▸그 전엔 task_id 키가 한 번 스냅샷에 들어가면 내용이 바뀌어도 다시는 '새 업무'가
#   안 됐다(배364·379 실측 · 2026-08-13 배592 에서 stale 재알림 도입).
# 실무진이 받는 글에는 누가 보내는지가 드러나야 한다(unassigned_nudge.AI_SIGNOFF 와 같은 형식).
# 전달 주체는 웰리 — GM 원문 "각기 담당자 이름 적어서 웰리가 전달".
# 2026-08-21 GM 확정 — "AI 총괄 웰리"가 아니라 그냥 "AI 웰리". 직함을 길게 붙이지 않는다.
# ※ 문구를 바꾸면 ops_daily_digest.AUTO_BROADCAST_SIGNOFF(자동글 걸러내는 자리)에도 같이
#   넣어야 한다. 안 넣으면 웰리가 보낸 자동 글이 '사람이 쓴 말'로 잡혀 요약에 다시 실린다.
RELAY_SIGNOFF = "AI 웰리 드림"
# 무게 순서(🛳️크루즈 → ⛴️여객선 → ⛵돛단배). 모르는 값은 맨 뒤.
_RELAY_WEIGHT = {"🛳️크루즈": 0, "⛴️여객선": 1, "⛵돛단배": 2}

# ★2026-08-07 GM 확정(약속 L24 · 배443) — 채널 역할을 갈랐다.
#   ★중간관리자 방 = 소통 창구(질문·요청·확인·답변 받기). 이경연 실장·이정헌 소장·나우열M 이
#     다 있어 부서를 가로지르는 확인이 한 번에 끝난다.
#   ★운영부 방 = 공유 전용. 업무 내용·진행 상황만 알리고 답변을 요구하지 않는다.
# 이 전달문은 "이 일을 해주세요"라 본질이 요청이다 — 답을 받아야 하므로 담당 역할과 무관하게
# ★중간관리자 방 한 곳으로 보낸다. 개인 이름으로 라우팅하지 않는다(방으로 라우팅).
# ★운영부 방에는 기존 아침 다이제스트(공유 성격)가 그대로 나간다 — 그건 손대지 않았다.
RELAY_ROOM = "★중간관리자"


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def _title_key(s: str) -> str:
    """방 이름 대조 — kakao_report_sender._title_key 와 같은 규칙(공백만 지운다)."""
    return "".join(str(s or "").split())


def _known_rooms() -> set:
    """kakao_rooms.json all_rooms 에 실재하는 방 이름 집합. 여기 없는 방으로는 안 보낸다
    (오타 한 글자로 엉뚱한 방을 열거나 매번 실패하는 일을 막는다 — 새 방 생성 금지)."""
    try:
        cfg = json.loads(ROOMS_CONFIG.read_text(encoding="utf-8"))
        return {_title_key(r.get("name", "")) for r in (cfg.get("all_rooms") or [])}
    except Exception as exc:
        log(f"[relay] 방 목록 읽기 실패 — 전달 생략: {exc}")
        return set()


def relay_routes() -> "list[tuple[str, dict]]":
    """[(방 이름, {clevel: 담당자})] — 담당자 정본은 safe_commit.DOMAIN_MODIFY_RULES 하나.

    ★2026-08-07 GM 확정(배443) — 방은 역할로 가르지 않는다. 이 전달문은 "이 일을 해주세요"라
    본질이 요청이고, 요청은 답을 받아야 한다 → 전부 ★중간관리자 방 한 곳으로 간다.
    담당자 이름은 본문 줄 끝에 그대로 붙으므로 누구 일인지는 안 흐려진다.
    (DOMAIN_MODIFY_RULES 의 room 칸은 커밋 가드 안내문에서 계속 쓰이므로 그대로 둔다.)
    """
    from safe_commit import DOMAIN_MODIFY_RULES  # 함수 안에서 import — 실패해도 다이제스트는 산다

    contacts: dict = {}
    for role_label, contact, _paths, _room, _note in DOMAIN_MODIFY_RULES:
        clevel = role_label.split("(")[0].strip().lower()  # "COO(시우)" → "coo"
        contacts[clevel] = contact
    # ★2026-08-10 GM 확정 — 시포(CPO) 몫도 이 통합본에 싣는다. GM 원문: "그냥 담당자없이
    #   전달해줘 운영부 장에게". 그래서 개인 담당자(임정은M 등) 이름은 줄에 안 붙이고
    #   운영부 장(이경연 실장) 한 사람 앞으로 보낸다 — 실장이 실무진에게 나눈다(약속 L24).
    #   ▸종전엔 이 표에 시포가 없어 조건(clevel not in contacts)에서 통째로 걸러졌다.
    #     전달문을 채워도 사람 방에 영영 안 나가는 상태였고, 발송 실패가 아니라
    #     '보낼 게 없음'으로 보여 아무 경보도 안 울렸다(실측 2026-08-10 · 배 7척).
    #   ▸safe_commit 의 커밋 가드 표(DOMAIN_MODIFY_RULES)에는 넣지 않는다 — 그 표는
    #     '누가 어느 파일을 고칠 수 있나'를 정하는 다른 목적이라 여기 필요로 건드리지 않는다.
    contacts.setdefault("cpo", "이경연 실장")
    # ★2026-08-18 시토 — 시포와 똑같은 구멍이 시토·시우에도 그대로 있었다. 이 표에 없는
    #   역할은 전달문을 채워도 build_relay_message 의 `clevel not in contacts` 에서 통째로
    #   걸러진다(2026-08-10 시포 사고와 같은 통로). 그래서 그 역할 배는 사람에게 물을 것이
    #   생겨도 영영 안 나가고, 배가 대신 답을 기다리며 열린 채로 남는다 — GM 2026-08-18
    #   지적("기다리는 라인을 안 만들 수는 없나")의 실제 원인이 여기다.
    #   ▸담당자는 약속 L24 대로 운영부 장(이경연 실장) 한 사람 — 시설부 소장님께 여쭐 건은
    #     전달문 본문에 성함을 적는다(★중간관리자 방에 실장·소장·나우열M 이 함께 있다).
    #   ▸시모(GM 직접 담당)는 넣지 않는다 — 담당이 GM 이라 사람 방으로 나갈 것이 없다.
    contacts.setdefault("cto", "이경연 실장")
    contacts.setdefault("coo", "이경연 실장")
    # ★2026-08-25 GM 방침 — 웰리(ceo) 배도 이 표에 넣는다. GM 원문: "질문에 꼭 답을 해야해?
    #   그냥 계속 푸시하면 안되는거야? 그리고 답변 오면 질문 삭제하고, 업무체크or완료 처리하면
    #   될 것 같은데." 종전엔 웰리가 여기 없어 배 626·725·763 처럼 전달문을 채워 둔 배가
    #   `clevel not in contacts` 에서 통째로 걸러졌고, 매번 웰리가 손으로 보내야 했다.
    #   ▸중복 발신 걱정(옛 주석의 근거)은 반대로 뒤집혔다 — 자동으로 나가면 웰리가 손으로
    #     보낼 이유가 없어진다. 손 발신을 멈추는 것이 짝 조치다(웰리 배로 전달).
    contacts.setdefault("ceo", "이경연 실장")
    return [(RELAY_ROOM, contacts)]


def _relay_key(ship: dict) -> str:
    """배 식별 키 — task_id 고정(배마다 불변). ★2026-08-06 GM 근본수정: 예전엔 short_no
    우선이었는데 short_no 는 나중에 붙는 경우가 있어, 같은 배가 키가 바뀌며 '완료'+
    '신규' 두 번 잡혔다. task_id 는 생성 시 한 번 박히고 안 바뀐다.

    ★첫 회차 처리: 옛 스냅샷은 short_no(숫자 문자열) 키라 이 함수 도입 이후 첫 비교에서
    전부 매칭 실패한다 — build_relay_message 의 _is_legacy_snapshot 이 그 회차만 비교를
    건너뛰고 새 키로 스냅샷만 다시 찍는다(살아있는 배 전부가 '신규'로 쏟아지는 것 방지)."""
    return str(ship.get("task_id") or "")


def _is_legacy_snapshot(prev_items: dict) -> bool:
    """지난 스냅샷이 옛 키(short_no 숫자 문자열)로 저장된 것인가.
    task_id 는 항상 "CTO-2026-07-22-..." 꼴 문자열이라 숫자만인 키가 하나라도 있으면
    옛 형식 — 이번 회차는 비교 없이 스냅샷만 새 키로 다시 찍는다(첫 회차 처리)."""
    return any(str(k).isdigit() for k in prev_items)


def _unpack_snapshot(v, today: str) -> "tuple[str, str]":
    """스냅샷 값 하나를 (문구, 마지막 발송일)로 푼다. ★2026-08-13 이전 값은 문구(str)만
    있었다 — 그 옛 값을 만나면 '오늘 막 보낸 것'으로 시계를 시작한다(last_sent=today).
    빈 값으로 두면 다음 회차부터 곧장 '7일 지남'으로 잡혀 형식전환 첫 회차에 밀린 배가
    한꺼번에 재알림으로 쏟아진다(_is_legacy_snapshot 이 막던 것과 같은 함정)."""
    if isinstance(v, dict):
        return str(v.get("line", "")), str(v.get("last_sent", "")) or today
    return str(v), today


def _is_stale(last_sent: str, today: str) -> bool:
    """내용은 안 바뀌었어도 이만큼 묵으면 다시 알린다(RELAY_STALE_DAYS)."""
    if not last_sent:
        return False
    try:
        return (date.fromisoformat(today) - date.fromisoformat(last_sent)).days >= RELAY_STALE_DAYS
    except Exception:
        return False


def _uncapped_line(text: str) -> str:
    """카톡 표시 캡(RELAY_TITLE_CAP) 없이 줄바꿈만 정리한 원문 — 스냅샷 비교 전용.

    ★2026-08-26 웰리 실측(배 11039) — 캡 뒤가 같으면 배626처럼 빈칸이 10건→3건으로
    줄어도 '변화 없음'으로 잡혔다. 비교는 항상 원문으로, 캡은 표시할 때만 씌운다."""
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _cap_line(text: str, cap: int = RELAY_TITLE_CAP) -> str:
    """카톡 한 줄용 길이 상한 — 낱말 한가운데서 자르지 않는다(GM 상시 지시).

    상한 안에서 마지막 띄어쓰기까지만 남긴다. 띄어쓰기가 아예 없으면(붙여 쓴 긴 문장)
    어쩔 수 없이 길이로 자른다 — 그때는 잘린 티가 나는 게 뜻이 끊기는 것보다 낫다.

    ★cap <= 0 이면 자르지 않는다(GM 지시 2026-08-30 — "핵심 내용을 끝까지 보내 달라,
      계속 …로 끝나는 것보다 다 보고 싶다"). 자르는 자리가 이 함수 하나뿐이라 여기서
      끄면 카톡 통 전체가 원문 그대로 나간다(약속 L21 — 관문 하나에만 둔다)."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if cap <= 0 or len(t) <= cap:
        return t
    # 링크는 절대 자르지 않는다 — 잘린 주소는 눌러도 404 다(2026-08-26 실측: 중간관리자
    # 방 아침 정리의 멤버십·지원부 링크가 '…' 로 끝나 실무진이 못 들어갔다).
    _m = re.search(r"https?://\S+", t)
    if _m:
        before = _cap_line(t[:_m.start()].strip(), cap) if _m.start() > cap else t[:_m.start()].strip()
        return f"{before} {_m.group(0)}".strip()
    head = t[:cap]
    cut = max(head.rfind(" "), head.rfind("·"))
    if cut >= cap // 2:
        head = head[:cut]
    return head.rstrip(" ·—-(→,") + "…"


_EMPTY_STAFF_MESSAGE = {"none", "null", "nan", "-", "—", "없음", "미정"}


def _has_staff_message(ship: dict) -> bool:
    """실무진에게 실을 만한 전달문이 실제로 있는가.

    ★2026-08-08 실측(배442) — 파이썬 None 이 문자열 "None" 으로 칸에 박혀 있던 배 3척이
    있었고, 그중 2척이 GM 이 2026-08-07 에 지적한 바로 그 2건이다(배 9·150). 칸을 비우려던
    응급 조치가 빈 값 대신 "None" 이라는 글자를 남겨, 다음 회차에 실무진 방으로
    「• None · 이경연 실장」 이 그대로 나갈 상태였다. 사람 눈에 뜻이 없는 값은 없는 값으로 친다.
    """
    text = _resolve_staff_message(ship).strip()
    return bool(text) and text.strip(".…").lower() not in _EMPTY_STAFF_MESSAGE


SCHEDULE_SSOT_PATH = ROOT / "status" / "schedule_ssot.json"


def _schedule_blank_names(dept: str) -> "list[str]":
    """전사일정 SSOT 에서 실시일(last_done)이 아직 빈 정기점검 이름들.

    이벤트(type='이벤트')는 제외한다 — 한 번 하고 끝나는 건은 '아직 못 받은 실시일'이
    아니다. '해당없음'으로 이미 판정된 줄도 뺀다(물을 것이 없다)."""
    try:
        data = json.loads(SCHEDULE_SSOT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        log(f"[relay] 전사일정 읽기 실패 — 동적 전달문 생략: {exc}")
        return []
    return [str(x.get("name") or "").strip()
            for x in data.get("items", [])
            if str(x.get("type")) == "정기점검"
            and (not dept or str(x.get("dept")) == dept)
            and str(x.get("applies") or "") != "해당없음"
            and not str(x.get("last_done") or "").strip()]


def _resolve_staff_message(ship: dict) -> str:
    """실제로 실을 전달문. staff_message_query 가 있으면 발송 시점에 원천에서 다시 만든다.

    ★2026-08-25 실사고 — 배626(법정·정기점검 실시일)의 목록을 사람이 손으로 유지하다가,
    이미 답을 받아 전사일정에 채워진 5건을 소장님께 다시 물었다. 사람이 목록을 지우는 일
    자체를 없앤다: 채워진 줄은 다음 발송에서 자동으로 빠지고, 다 채워지면 전달문이 비어
    그 배는 목록에서 사라진다(약속 L01 — 목록의 진실은 전사일정 한 곳).
    """
    q = ship.get("staff_message_query")
    if not isinstance(q, dict) or q.get("kind") != "schedule_blank":
        return str(ship.get("staff_message") or "")
    names = _schedule_blank_names(str(q.get("dept") or ""))
    if not names:
        return ""   # 빈칸이 다 채워졌다 — 더 물을 것이 없다
    who = str(q.get("to") or "").strip()
    head = f"{who} — " if who else ""
    lines = [f"{head}점검 실시일 중 아직 못 받은 것은 {len(names)}가지입니다."
             " 아시는 것부터 한 줄씩 주시면 저희가 전사일정에 채웁니다."]
    lines += [f"{i}) {n} — 최근 실시일" for i, n in enumerate(names, 1)]
    tail = str(q.get("tail") or "").strip()
    if tail:
        lines.append(tail)
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════
# 📅 다가오는 일정 (2026-08-28 GM 지시 · 배 11070) — "카카오톡에 전사일정 관련해가지고도
# 리마인드 같이 시켜주면 좋을 것 같긴해". 원장 = status/schedule_ssot.json 하나뿐(읽기 전용
# — 이 파일이 쓰지 않는다, 다른 레인이 쓴다). 새 원장·새 통을 만들지 않는다(약속 L21) —
# 이미 나가는 아침 통 끝에 블록 하나로 붙인다.
#
# 부서 소관(법정·정기점검·공사·점검 회차)과 관리자 건(미팅·방문·보고 등)은 방이 다르다
# (GM 지시 — 같은 일정이 두 방에 겹쳐 나가면 안 된다). 가르는 기준 = type·담당 부서:
#   부서 소관 → type이 정기점검이거나 dept가 시설·지원·주차·운영 4부서 중 하나
#   관리자 건 → 그 밖(경영지원부 등 — 미팅·방문·보고류)
# 호출부(send_schedule_pings — 별도 통 · 2026-08-29)가
# _is_dept_schedule_item 으로 걸러서 넘긴다.
# ponytail: 「전사일정에 넣은 것」(ops_daily_digest.py, 다른 파일의 절)과 겹칠 때 빼는
#   로직은 안 넣었다 — 그 절의 원장을 이 파일이 몰라 넣으려면 파일을 하나 더 읽어야
#   한다. 겹침이 실제로 눈에 띄면 그때 흡수한다.
# ══════════════════════════════════════════════════════════════════════════
SCHEDULE_LOOKAHEAD_DAYS = 7
SCHEDULE_SHOW_N = 5


def _schedule_horizon(today=None):
    """일정 리마인드의 끝 날짜 = **이번 주 금요일**(GM 지시 2026-09-01).

    GM 원문: "항상 이번주 금요일까지 계속 리마인드해줘. 9.1(화)면 9.1~9.4(금),
    9.2(수)면 9.2~9.4(금)." 창이 매일 7일씩 앞으로 밀리면 같은 일정이 일주일 내내
    같은 자리에 떠 배경이 된다. 금요일로 못 박으면 주가 갈수록 목록이 줄어 —
    남은 것이 눈에 띈다.
    ▸토·일에는 이번 주 금요일이 이미 지났으므로 다음 주 금요일까지 본다(빈 통 방지).
    """
    today = today or date.today()
    wd = today.weekday()                 # 월=0 … 금=4 · 토=5 · 일=6
    ahead = (4 - wd) if wd <= 4 else (4 + 7 - wd)
    return today + timedelta(days=ahead)
_SCHEDULE_DEPT_ORGS = {"시설부", "지원부", "주차관리부", "운영부"}


def _is_dept_schedule_item(item: dict) -> bool:
    """부서 소관(법정·정기점검·공사·점검 회차)인가 — 아니면 관리자 건(미팅·방문·보고 등)."""
    return str(item.get("type")) == "정기점검" or str(item.get("dept") or "").strip() in _SCHEDULE_DEPT_ORGS


def _upcoming_schedule_items(today=None) -> list:
    """오늘부터 SCHEDULE_LOOKAHEAD_DAYS일 안, 담당(assignee)이 잡힌 일정만 next_due 순으로.
    applies='해당없음'은 뺀다(schedule_ssot.json honesty_note — 부서가 해당없음으로 끈 것)."""
    today = today or date.today()
    try:
        data = json.loads(SCHEDULE_SSOT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        log(f"[schedule] 전사일정 읽기 실패 — 리마인드 절 생략: {exc}")
        return []
    horizon = _schedule_horizon(today)
    out = []
    for x in data.get("items", []):
        if not isinstance(x, dict) or str(x.get("applies") or "") == "해당없음":
            continue
        assignee = str(x.get("assignee") or "").strip()
        if not assignee:
            continue
        try:
            d = date.fromisoformat(str(x.get("next_due") or "")[:10])
        except Exception:
            continue
        if not (today <= d <= horizon):
            continue
        out.append({"date": d, "name": str(x.get("name") or "").strip(), "assignee": assignee,
                    "dept_item": _is_dept_schedule_item(x)})
    out.sort(key=lambda x: x["date"])
    return out


def _schedule_day_label(d, today) -> str:
    delta = (d - today).days
    if delta == 0:
        return "오늘"
    if delta == 1:
        return "내일"
    return f"{d.month}/{d.day}"  # GM 지시 — "D-3" 같은 표기는 못 읽는다, 실제 날짜로 적는다


def _todays_assignees(items: list, today=None) -> list:
    """오늘 날짜 건의 담당자 — 순서 유지·중복 제거. 없으면 빈 목록."""
    today = today or date.today()
    names: list = []
    for it in items:
        if it.get("date") != today:
            continue
        nm = str(it.get("assignee") or "").strip()
        if nm and nm not in names:
            names.append(nm)
    return names


def _build_schedule_block(items: list, today=None, show_all: bool = False) -> str:
    """📅 다가오는 일정 블록. items 는 이미 부서/관리자 갈래로 걸러진 목록.

    5건 선택은 날짜 다양성 우선(2026-08-29 실측 수리) — 앞 날짜 하나가 5건을 독식하면
    9/2 미팅·9/4 공사 같은 뒤 날짜 핵심 일정이 「그 밖」으로 접혀 안 보였다(8/31 8건 실측).
    날짜별 첫 건을 먼저 채우고 남는 자리를 날짜순으로 채운다. 표시는 날짜순 그대로."""
    if not items:
        return ""
    today = today or date.today()
    seen, first, later = set(), [], []
    for it in items:
        (later if it["date"] in seen else first).append(it)
        seen.add(it["date"])
    # show_all — 관리자 방으로 한 통만 갈 때는 접지 않는다(GM 2026-09-01 "각 관리자들이 챙길 수
    # 있도록"). 가려진 줄이 있으면 챙길 수가 없다.
    if show_all:
        # 날짜로 묶어 적는다. 스물 몇 줄이 날짜 없이 이어지면 같은 날 것이 몇 건인지 안 보이고,
        # 관리자가 '오늘 우리 부서 것' 을 찾으려면 처음부터 다시 읽어야 한다.
        # 한 줄에 한 가지 · 상세는 들여쓰기(실무진 전달문 표준).
        shown = sorted(items, key=lambda x: x["date"])
        _end = _schedule_horizon(today)
        _dow = "월화수목금토일"
        _rng = (f"{today.month}/{today.day}({_dow[today.weekday()]})"
                if _end == today else
                f"{today.month}/{today.day}({_dow[today.weekday()]}) ~ {_end.month}/{_end.day}({_dow[_end.weekday()]})")
        lines = [f"📅 다가오는 일정 — {_rng} · {len(shown)}건"]
        cur = None
        for it in shown:
            if it["date"] != cur:
                cur = it["date"]
                lab = _schedule_day_label(cur, today)
                # '오늘'·'내일' 은 날짜를 같이 적어 준다. 그 밖은 라벨이 이미 날짜라 두 번 안 적는다.
                lines.append(f"▪ {lab} ({cur.month}/{cur.day})" if lab in ("오늘", "내일") else f"▪ {lab}")
            lines.append(f"   {it['name']} — {it['assignee']}")
        return "\n".join(lines)
    shown = sorted((first + later)[:SCHEDULE_SHOW_N], key=lambda x: x["date"])
    rest = [it for it in items if it not in shown]
    lines = ["📅 다가오는 일정"]
    for it in shown:
        lines.append(f" • {_schedule_day_label(it['date'], today)} — {it['name']} ({it['assignee']})")
    if rest:
        lines.append(f" • 그 밖 {len(rest)}건")
    return "\n".join(lines)


def _selfcheck_schedule_block() -> None:
    """부서/관리자 갈래·7일 창·5건 상한·오늘·내일 표기. 네트워크 없이 돈다."""
    today = date(2026, 8, 28)
    raw = [
        {"name": "손소독제 구매", "assignee": "이경연 실장", "dept": "운영부", "type": "정기점검",
         "next_due": "2026-08-28", "applies": "있음"},
        {"name": "매트릭스 방문", "assignee": "김남욱GM", "dept": "경영지원부", "type": "이벤트",
         "next_due": "2026-08-29", "applies": "있음"},
        {"name": "8일 뒤 — 창 밖", "assignee": "김남욱GM", "dept": "경영지원부", "type": "이벤트",
         "next_due": "2026-09-05", "applies": "있음"},
        {"name": "담당 미정 — 빠져야 함", "assignee": "", "dept": "시설부", "type": "정기점검",
         "next_due": "2026-08-29", "applies": "있음"},
        {"name": "해당없음 — 빠져야 함", "assignee": "이정헌 소장", "dept": "시설부", "type": "정기점검",
         "next_due": "2026-08-29", "applies": "해당없음"},
    ]
    items = []
    for x in raw:
        d = date.fromisoformat(x["next_due"])
        if x["applies"] == "해당없음" or not x["assignee"] or not (today <= d <= today + timedelta(days=6)):
            continue
        items.append({"date": d, "name": x["name"], "assignee": x["assignee"],
                      "dept_item": _is_dept_schedule_item(x)})
    dept_items = [x for x in items if x["dept_item"]]
    mgr_items = [x for x in items if not x["dept_item"]]
    assert len(dept_items) == 1 and dept_items[0]["name"] == "손소독제 구매", dept_items
    assert len(mgr_items) == 1 and mgr_items[0]["name"] == "매트릭스 방문", mgr_items
    dept_out = _build_schedule_block(dept_items, today)
    assert "오늘 — 손소독제 구매 (이경연 실장)" in dept_out, dept_out
    mgr_out = _build_schedule_block(mgr_items, today)
    assert "내일 — 매트릭스 방문 (김남욱GM)" in mgr_out, mgr_out
    assert "8일 뒤" not in dept_out and "8일 뒤" not in mgr_out, "7일 창 밖은 빠져야 한다"
    assert "담당 미정" not in dept_out, "담당 없는 일정은 빠져야 한다"
    assert "해당없음" not in dept_out, "applies=해당없음은 빠져야 한다"
    many = [{"date": today, "name": f"건{i}", "assignee": "x", "dept_item": True} for i in range(7)]
    out = _build_schedule_block(many, today)
    assert out.count(" • ") == 6, "5건 + 「그 밖」 한 줄 = 6줄이어야 한다"
    assert "그 밖 2건" in out, out
    assert _build_schedule_block([], today) == "", "일정이 없으면 블록 자체가 없어야 한다"
    print("[selfcheck] _build_schedule_block OK")


# ══════════════════════════════════════════════════════════════════════════
# 📌+📮 통합 「확인 부탁드릴 것」 절 (2026-08-20 GM 지적 수리)
#
# GM 원문: "정말 복잡해, 직관적이고 명확해야해, 내용도 다 체크되거나 완료된건 등등
# 정리안된 내용들이 너무 많아서 신뢰가 안되네." 실측(2026-08-20 07:41 발송본) —
# 헤더는 "18건"인데 실제로 줄로 보이는 건 4건뿐이었다(나머지 14건은 지난 회차와
# 안 바뀌어 조용히 숨어 있었는데 헤더 숫자엔 그대로 들어갔다). 거기에 배 전달(📌)과
# 회신 부탁(📮)이 각자 헤더·건수를 따로 갖고, 완료된 배 스냅샷("✅ 처리 완료")까지
# 같은 메시지에 섞여 있어 "확인해 달라"는 메시지 안에 "이미 끝났다"는 내용이 같이
# 왔다 — 대화 정리 절의 "✅ 확인된 것"과도 겹치는 중복이었다.
#
# 고친 것: 두 절을 하나로 합친다(build_asks_section). 헤더 건수 = 화면에 실제로 보이는
# 줄 수(더 이상 숨은 잔여분을 포함하지 않는다). 완료 스냅샷은 아예 안 싣는다(약속
# "★중복 최소화" — 완료는 대화 정리 절의 "✅ 확인된 것"이 이미 담당). 한 건 = 두 줄
# (①무엇을 확인해 달라는지 ②어디서·어떻게 답하면 되는지), 오래된 순 사람별 상한만.
#
# ★2026-08-26 웰리 실측(배 11039 ⑤) — 상한이 통 전체 5건 고정이라, 실장님 앞으로 5건이
# 차면 다음 회차에 소장님 건이 새로 생겨도 밀려 접혔다. 그래서 사람별 상한(5건씩)으로
# 바꿨었는데, 형평은 지켰지만 사람이 여럿이면 한 통 총량이 다시 커졌다(오늘 실측 —
# 총 5건 그대로 나감). ★2026-08-29 GM 확정(배826 재승인) — 형평보다 "한 통 3건" 총량이
# 우선이다. 사람별 배려는 없앤다 — 오래된 순으로 3건만 자르고 나머지는 한 줄로 접는다.
# ══════════════════════════════════════════════════════════════════════════
# ★2026-08-30 GM 지시 — "가능하면 조금 더 넉넉한 줄수를 주고, 핵심 내용을 끝까지 보내 달라.
#   계속 …로 끝나거나 '외 3건'으로 접히는 것보다 다 보고 싶다, 궁금하다."
#   → 세 상한을 모두 0(= 자르지 않음)으로 둔다. 8/29 의 '한 통 3건'은 이 지시가 대체한다.
#   접는 대신 줄여야 하는 건 화면에 뜨는 줄이 아니라 안 끝난 '건수' 자체다.
ASKS_TOTAL_CAP = 0  # 0 = 전부 보여줌(GM 지시 2026-08-30). 종전 3건
ASKS_TITLE_CAP = 0  # 0 = 안 자름. 종전 50자
ASKS_HOW_CAP = 0    # 0 = 안 자름. 종전 60자
_ROLE_TAG_RE = re.compile(r"^\[[^\]]*\]\s*")  # "[웰페리온 AI 웰리] " 같은 발신 태그
_GREETING_RE = re.compile(r"^(답변\s*)?(감사|고맙|안녕|수고)")  # 인사·감사만 있는 줄
_ADDRESS_ONLY_RE = re.compile(r"(님|께)\s*[,，]?$")            # 「이경연 실장님,」 같은 호칭 줄


def _is_lead_in(line: str) -> bool:
    """확인할 내용이 없는 머리줄(인사·감사·호칭만)인가. 짧은 줄에만 적용한다 —
    「이경연 실장님 — 세탁물 화면에 …」 처럼 뒤에 내용이 붙은 줄은 그대로 쓴다."""
    return bool(_GREETING_RE.match(line)) or (len(line) <= 15 and bool(_ADDRESS_ONLY_RE.search(line)))


def _split_ask_how(staff_message: str, who: str) -> "tuple[str, str]":
    """전달문 원문(여러 줄일 수 있음)에서 ①확인해 달라는 한 줄 ②어디서·어떻게 답하면
    되는지 한 줄을 뽑는다. 링크(📎)가 있으면 그 줄을 '어떻게'로 쓰고, 없으면 담당자에게
    한 마디로 답해 달라는 기본 문구를 쓴다. 배 note 를 통째로 붙이지 않는다(GM 지적)."""
    text = _ROLE_TAG_RE.sub("", str(staff_message or "").strip())
    body_lines = [l.strip() for l in text.splitlines() if l.strip()]
    # ★인사·호칭만 있는 첫 줄은 건너뛴다(2026-08-26 실측 — 배784 는 「답변 감사합니다.」,
    #   배778 은 「이경연 실장님,」 한 줄로 목록에 실려 무슨 건인지 알 수 없었다). 전달문을
    #   쓰는 쪽이 매번 형식을 챙기게 하지 않고, 싣는 쪽에서 내용 있는 줄을 고른다.
    idx = next((i for i, l in enumerate(body_lines) if not _is_lead_in(l)), 0)
    ask = body_lines[idx] if body_lines else text
    how = next((l for l in body_lines[idx + 1:] if l.startswith("📎")), "")
    if not how:
        how = f"{who}님께 말씀해 주시거나 톡으로 한 마디만 답해 주시면 됩니다."
    return _cap_line(ask, ASKS_TITLE_CAP), _cap_line(how, ASKS_HOW_CAP)


def build_asks_section(relay_items: list, nudge_items: list) -> str:
    """배 전달(relay)·회신 부탁(nudge) 항목을 오래된 순으로 합쳐 한 통 ASKS_TOTAL_CAP건만
    보여주고 나머지는 한 줄로 접는다(GM 확정 2026-08-29 — 종전 사람당 상한을 한 통 총량
    상한으로 바꿨다). 표시는 여전히 사람별로 묶는다. 헤더 건수 = 화면에 실제로 보이는
    줄 수뿐이다."""
    items = sorted(relay_items + nudge_items, key=lambda x: x.get("date") or "9999-99-99")
    if not items:
        return ""
    shown = items if ASKS_TOTAL_CAP <= 0 else items[:ASKS_TOTAL_CAP]
    rest = len(items) - len(shown)

    # ★2026-08-20 GM 지적("정말 복잡해, 직관적이고 명확해야해") — 사람 단위로 묶는다.
    #   전에는 항목마다 「…님께 한 마디만 답해 주시면 됩니다」가 그대로 반복돼 같은 문장이
    #   다섯 번 찍혔다. 답하는 방법은 맨 위에 한 번만 적고, 아래는 사람별로 자기 것만 모아
    #   한 줄씩 둔다 — 받는 사람이 자기 이름만 찾으면 자기 몫이 다 보인다.
    #   ▸어디서 하는지가 따로 있는 건(📎 링크가 붙은 건)만 그 줄을 살려 둔다.
    by_who: dict = {}
    for it in shown:
        by_who.setdefault(it["who"], []).append(it)

    lines = [f"🧾 확인 부탁드릴 것 {len(shown)}건 — 한 마디만 주시면 됩니다(진행 중 / 완료 / 날짜)"]
    for who, group in by_who.items():
        lines.append(f"👤 {who}")
        for it in group:
            lines.append(f" • {it['ask']}")
            how = str(it.get("how") or "")
            if "📎" in how or "http" in how:
                lines.append(f"   {how}")
    if rest:
        lines.append(f"…외 {rest}건이 더 있습니다 — 오래된 순 {ASKS_TOTAL_CAP}건만 추렸습니다.")
    lines.append(RELAY_SIGNOFF)
    return "\n".join(lines)


def _selfcheck_asks_section() -> None:
    """헤더 건수 = 실제로 보이는 줄 수인지, 그리고 접히는 건·잘리는 글자가 없는지
    (GM 지시 2026-08-30 — 전부 끝까지 보낸다). 네트워크 없이 돈다."""
    relay = [{"date": "2026-08-18", "who": "이경연 실장", "ask": "실장 건", "how": "h"}]
    nudge = [{"date": f"2026-08-{d:02d}", "who": "이정헌 소장", "ask": f"n{d}건", "how": "h"}
             for d in range(10, 17)]  # 7건 — 이경연 실장 1건과 합쳐 총 8건
    out = build_asks_section(relay, nudge)
    assert "확인 부탁드릴 것 8건" in out, out  # 헤더 건수 = 실제로 보이는 줄 수
    assert "더 있습니다" not in out, out       # 접는 꼬리줄이 남아 있으면 안 된다
    # 답하는 방법 안내는 맨 위 한 번뿐이어야 한다(2026-08-20 GM: 같은 문장이 다섯 번 찍혔다)
    assert out.count("한 마디만 주시면 됩니다") == 1, out
    # 여덟 건 전부 본문에 있어야 한다 — 사람이 여럿이어도 밀려 접히지 않는다.
    for d in range(10, 17):
        assert f"n{d}건" in out, f"모든 건이 보여야 한다: n{d}"
    assert "실장 건" in out, "다른 사람 건도 접히지 않아야 한다"
    # 긴 문장이 '…' 로 끊기지 않는지 — GM 지시 2026-08-30 의 핵심.
    long_ask = "가나다라마바사아자차카타파하 " * 8
    out2 = build_asks_section([{"date": "2026-08-01", "who": "테스트", "ask": _cap_line(long_ask, ASKS_TITLE_CAP), "how": "h"}], [])
    assert "…" not in out2, out2
    assert out.splitlines()[-1] == RELAY_SIGNOFF
    assert build_asks_section([], []) == "", "항목 0건이면 절 자체가 없어야 한다"
    print("[selfcheck] build_asks_section OK")


def build_relay_message(contacts: dict, prev_items: dict) -> "tuple[list, dict]":
    """열려 있는(PENDING·IN_PROGRESS) 배 중 '실무진 전달문'(staff_message)이 있는 것만 담는다.

    ★2026-08-06 GM 근본수정 — 예전엔 배 '제목'을 40자 근처에서 잘라 보냈다. 배 제목은
    AI 끼리 쓰는 식별 문장이라 사람에게 그대로 주면 맥락이 없다("무슨 내용이냐고
    묻는데?"). 이제는 배의 staff_message 칸(무엇을·왜·어떻게 해달라 세 줄)을 그대로
    싣는다 — 잘라서 붙이는 게 아니라 애초에 사람이 읽을 문장을 배에 적어 두게 한다.
    staff_message 가 없는 배는 싣지 않는다 — 잘린 제목보다 안 보내는 게 낫다.

    매일 같은 목록을 다시 보내면 실무진이 읽기를 멈춘다 — prev_items(지난 회차에 실은
    {key: 스냅샷}) 와 비교해 '새로 생긴 것'·'처리 완료된 것'만 알린다. 변화가 없으면
    빈 문자열을 돌려 아무것도 보내지 않는다. 반환값 (message, current_items) — 두
    번째 값은 다음 회차 비교용으로 그대로 저장된다(변화가 없어도 저장 — prev_items 를
    계속 최신 스냅샷으로 유지해야 다음 변화를 놓치지 않는다).

    ★audience 가 'office' 인 배만 싣는다(GM 2026-08-05 "원래 하던 일인데, 배편에 있는
    내용인거야?"). 큐에는 AI 내부 살림(audience='ai')도 섞여 있는데, 그걸 사람 방에
    보내면 AI 를 돌보는 일이 실무진 업무로 둔갑한다."""
    try:
        queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        log(f"[relay] 큐 읽기 실패 — 전달 생략: {exc}")
        return "", dict(prev_items)

    # ★제외 사유를 센다(2026-08-07 GM 지적 배442 — 조용한 탈락 금지). 안 나가는 것도 사고다:
    #   'AI 살림이라 뺐다'와 '전달문이 비어 안 나간다'는 전혀 다른 문제인데 둘 다 침묵이면 구별이 안 된다.
    #   담당이 아예 다른 역할인 배는 정상 범위 밖이라 세지 않는다(그건 탈락이 아니다).
    dropped_why = {"닫힌 배": 0, "AI 내부 살림": 0, "전달문 비어 있음": 0, "audience 칸 비어 있음": 0,
                   "공유 전용(답 불필요)": 0}
    ships = []
    for x in queue:
        if not isinstance(x, dict) or x.get("clevel") not in contacts:
            continue
        if str(x.get("status", "")) not in RELAY_OPEN_STATUSES:
            dropped_why["닫힌 배"] += 1
            continue
        aud = str(x.get("audience", "")).strip()
        if aud != "office":
            # 빈 칸은 안전측으로 막는다 — 채우기 전까지 안 나가는 게 맞다(GM 2026-08-07).
            dropped_why["AI 내부 살림" if aud else "audience 칸 비어 있음"] += 1
            continue
        if not _has_staff_message(x):
            dropped_why["전달문 비어 있음"] += 1
            continue
        # ★2026-08-26 웰리 실측(배 11039 ④) — "확인 부탁드릴 것" 절은 전부 답을 구하는
        # 문구인데, 실제로는 사과·감사·완료 안내처럼 답이 필요 없는 배도 섞여 실무진에게
        # 없던 부담을 만들었다. reply_needed=False 면 이 절(★중간관리자)에는 안 싣는다 —
        # 새 방·새 절은 만들지 않는다(약속 L21). 안 적으면(기본값) 지금까지처럼 답 필요로 본다.
        if not bool(x.get("reply_needed", True)):
            dropped_why["공유 전용(답 불필요)"] += 1
            continue
        ships.append(x)
    ships.sort(key=lambda x: (_RELAY_WEIGHT.get(x.get("priority"), 9),
                              str(x.get("enqueued_at", ""))))

    if _is_legacy_snapshot(prev_items):
        log(f"[relay] 후보 {len(ships)}척 · 제외 "
            + (" · ".join(f"{k} {v}" for k, v in dropped_why.items() if v) or "없음")
            + " · 옛 스냅샷 형식 — 이번 회차는 발신 없이 새 키로만 다시 찍음")
        today = date.today().isoformat()
        current = {_relay_key(s): {"line": _uncapped_line(_resolve_staff_message(s).strip().splitlines()[0]),
                                    "last_sent": today} for s in ships}
        return "", current  # 옛 키 형식 — 비교 건너뛰고 새 키로 스냅샷만 다시 찍는다(첫 회차)

    today = date.today().isoformat()
    prev_lines = {k: _unpack_snapshot(v, today)[0] for k, v in prev_items.items()}
    prev_sent = {k: _unpack_snapshot(v, today)[1] for k, v in prev_items.items()}

    new_ships = []    # 처음 보거나(키 없음) 내용이 바뀐 것(★2026-08-13 — 예전엔 키만 보고 놓쳤다)
    stale_ships = []  # 내용은 그대로인데 RELAY_STALE_DAYS 이상 묵어 다시 알리는 것
    current = {}
    for s in ships:
        k = _relay_key(s)
        line = _uncapped_line(_resolve_staff_message(s).strip().splitlines()[0])
        if k not in prev_lines or prev_lines[k] != line:
            new_ships.append(s)
            current[k] = {"line": line, "last_sent": today}
        elif _is_stale(prev_sent[k], today):
            stale_ships.append(s)
            current[k] = {"line": line, "last_sent": today}  # 재알림 보냈으니 시계 리셋
        else:
            current[k] = {"line": line, "last_sent": prev_sent[k]}  # 변화 없음 — 시계 유지

    # ★2026-08-26 웰리 실측(배 11039 ①) — 옛 로그는 후보 수를 "실을 배 N척"이라 적어
    #   실제 발신 건수처럼 읽혔다. 이번 회차에 정말 나가는 수(신규+재알림)와 오늘 이미
    #   보낸 수(변화 없음)를 갈라 적는다.
    already_today = len(ships) - len(new_ships) - len(stale_ships)
    log(f"[relay] 후보 {len(ships)}척 -> 이번 회차 실림 {len(new_ships) + len(stale_ships)}"
        f"(신규 {len(new_ships)}·재알림 {len(stale_ships)}) · 오늘 이미 보냄 {already_today} · 제외 "
        + (" · ".join(f"{k} {v}" for k, v in dropped_why.items() if v) or "없음"))

    # ★완료는 이 절에 안 싣는다(2026-08-20 GM 지적 — "확인해 달라"는 메시지에 "이미
    #   끝났다"가 섞여 신뢰를 깎는다). 대화 정리 절의 "✅ 확인된 것"이 이미 담당한다.
    #   목록에서 사라진 키는 스냅샷(current)에서도 그냥 빠진다 — 별도 처리 불필요.
    if not new_ships and not stale_ships:
        return [], current  # 지난번과 같은 목록 — 다시 보내지 않는다

    # ★한 항목 = {"date","who","ask","how"} 로 돌려준다. 헤더·건수·상한은 이제
    #   build_asks_section 이 nudge 항목과 합쳐서 한 번에 결정한다(중복 헤더 제거).
    items = []
    for s in new_ships + stale_ships:
        # 받는 사람은 원래 clevel 당 한 사람으로 정해져 있었다. 그런데 같은 역할이 서로 다른
        # 분께 여쭐 일이 생기면 그 가정이 깨진다 — 2026-08-26 실측에서 이정헌 소장님 앞
        # 전달문(주차 일일점검 담당 시설부 확정)이 「이경연 실장」 묶음 아래로 들어갔다.
        # 받는 사람이 배에 적혀 있으면(staff_to) 그것을 쓴다. 안 적힌 배는 종전 그대로다.
        who = str(s.get("staff_to") or "").strip() or contacts[s["clevel"]]
        ask, how = _split_ask_how(_resolve_staff_message(s), who)
        items.append({"date": str(s.get("enqueued_at", ""))[:10], "who": who, "ask": ask, "how": how})
    return items, current


def _relay_state() -> dict:
    """방별 지난 회차 스냅샷 {room: {key: snapshot}} — 상설 하트비트 1파일에 보관."""
    from module_heartbeat import last_heartbeat
    rec = last_heartbeat(RELAY_HEARTBEAT_ID) or {}
    state = rec.get("state")
    return {k: dict(v) for k, v in state.items()} if isinstance(state, dict) else {}


def _save_relay_state(state: dict) -> None:
    from module_heartbeat import record_heartbeat
    record_heartbeat(RELAY_HEARTBEAT_ID,
                     detail=f"사람 처리 배 전달 — 방 {len(state)}곳 스냅샷 갱신",
                     extra={"state": state})


def _migrate_relay_state(state: dict) -> None:
    """방 배정이 바뀐 첫 회차에 옛 방 스냅샷을 새 방으로 합친다(배443).

    안 하면 이미 한 번 전달한 배가 전부 '새로 생긴 업무'로 한꺼번에 쏟아진다 — 방을 바꾼 게
    실무진 눈에는 대량 신규로 보인다. 합치기만 하고 발신은 안 한다.
    """
    legacy = [r for r in list(state) if r != RELAY_ROOM]
    if not legacy:
        return
    merged = dict(state.get(RELAY_ROOM) or {})
    for r in legacy:
        merged.update(state.pop(r) or {})
    state[RELAY_ROOM] = merged
    log(f"[relay] 방 통합 — 옛 방 {len(legacy)}곳 스냅샷을 '{RELAY_ROOM}'로 승계(첫 회차 대량발신 방지)")


def preview_relays() -> int:
    """방에 손대지 않고 배 전달(relay) 부분만 렌더해 보여준다(실방 검증용 — 발신·상태기록
    없음). 회신 부탁(nudge) 은 --mgr-preview 쪽이 합쳐서 보여준다."""
    state = _relay_state()
    _migrate_relay_state(state)   # 실제 발신과 같은 조건으로 봐야 미리보기가 미리보기다
    for room, contacts in relay_routes():
        items, _current = build_relay_message(contacts, state.get(room, {}))
        message = build_asks_section(items, [])
        print(f"\n===== {room} ({'내용 없음' if not message else '발신 대상'}) =====")
        print(message or "(변화 없음 — 발신 안 함)")
        if message:
            body = message.splitlines()
            assert body[-1] == RELAY_SIGNOFF, "AI 주체 서명 누락"
            assert "PENDING" not in message and "task_id" not in message, "내부 상태값 노출"
    return 0


# 배698(2026-08-19 GM 결정) — "마지막 발송일" 하트비트. ops_daily_digest.pick_target_dates
# 가 이 값을 읽어 그 이후 밀린 완결일을 한 통으로 흡수한다(id는 그쪽 _LAST_SENT_HEARTBEAT
# 와 반드시 같은 문자열 — 약속 L01, 두 파일이 각자 상수로 들고 있으니 고칠 땐 같이 고친다).
_LAST_SENT_HEARTBEAT_OPS = "ops-digest-last-sent-ops"
_LAST_SENT_HEARTBEAT_MGR = "ops-digest-last-sent-mgr"


def _record_last_sent(heartbeat_id: str, date_str) -> None:
    if not date_str:
        return
    try:
        from module_heartbeat import record_heartbeat
        record_heartbeat(heartbeat_id, detail=f"발송 완료 — {date_str}", extra={"state": {"date": str(date_str)}})
    except Exception as e:
        log(f"[last-sent] 하트비트 기록 실패({heartbeat_id}): {e}")


def kill_switch_enabled() -> bool:
    try:
        return bool(json.loads(KILL_SWITCH.read_text(encoding="utf-8")).get("enabled", False))
    except Exception:
        return False


def send_mgr_brief() -> None:
    """★중간관리자 결정거리 요약 발송 — ★운영부 결과와 무관하게 자기 조건으로 돈다.

    ★2026-08-15 수리(방마다 독립 · 배536 원칙): 예전엔 이 블록이 main()의 ★운영부 발송
    '성공' 분기 안에 있었다. 그래서 ①★운영부 발송이 실패하면 ★중간관리자도 통째로 안 나갔고
    ②같은 날 재실행하면 ★운영부가 '이미 발송됨'으로 먼저 return 해 — mgr 발송 실패 시
    "다음 회차 재시도" 로그가 거짓이었다(재시도 기회가 그날 다시 오지 않는다).
    중복방지는 원래대로 _mgr_already_sent(하트비트) 하나가 담당한다.

    대상일 = 그 방 자신의 _pending_digest.json(date) — 오늘 생성분일 때만. 없으면 어제.
    (예전엔 ★운영부 pending 의 date 를 빌려 썼다 — 두 방의 대화 폴백일이 갈리면 어긋난다.)"""
    from datetime import timedelta

    today = datetime.now().strftime("%Y-%m-%d")
    target_date = ""
    if MGR_PENDING.exists():
        try:
            d = json.loads(MGR_PENDING.read_text(encoding="utf-8"))
            if str(d.get("generated_at", "")).startswith(today):
                target_date = str(d.get("date", ""))
        except Exception:
            pass
    if not target_date:
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    if _mgr_already_sent(target_date):
        log(f"[mgr] 이미 발송된 회차({target_date}) — 생략")
        return
    mgr_msg, relay_current = build_mgr_daily_brief(_fetch_todo_rows(), target_date)
    if not mgr_msg:
        log("[mgr] 보낼 내용 0건 — 발송 생략")
        return
    # --sender 아침정리다이제스트 — kakao_report_sender 의 사람 방 발신 가드(배 11070 ⑤) 통과용.
    mcmd = [sys.executable, str(SENDER), "--message", mgr_msg, "--only-room", WEEKLY_ROOM,
            "--sender", "아침정리다이제스트"]
    log(f"[mgr] 결정거리 요약 발송(대상 {target_date}) → {WEEKLY_ROOM}")
    mproc = subprocess.run(mcmd, capture_output=True, text=True, encoding="utf-8")
    mout = (mproc.stdout or "").strip()
    if mproc.returncode == 0 and "DONE" in mout:
        _mark_mgr_sent(target_date)
        _record_last_sent(_LAST_SENT_HEARTBEAT_MGR, target_date)  # 배698 — 흡수 판단용(위 참조)
        # 열린 요청 절 스냅샷 저장 — 발송 성공 후에만(미리보기·실패 시엔 안 찍음,
        # 기존 relay 하트비트 RELAY_HEARTBEAT_ID 재사용, 새 파일 없음 · 약속 L21).
        relay_state = _relay_state()
        _migrate_relay_state(relay_state)
        relay_state[WEEKLY_ROOM] = relay_current
        _save_relay_state(relay_state)
        log("[mgr] 발송 완료")
    else:
        log(f"[mgr] 발송 실패(rc={mproc.returncode}) — 다음 회차 재시도")


# ══════════════════════════════════════════════════════════════════════════
# 기한 초과 접수 알림 (배CTO-2026-08-18 · GM 지시 2026-08-18)
# 매일 아침 3일+ 미처리 접수를 부서별 방에 한 번씩 내보낸다. 분실물 제외(별도 주기).
# 3일=건수 한 줄 / 7일+=부서·담당 이름 / 14일+=맨 앞. 담당 공란='담당 미정'.
# 방: 팀/강습 → ★부서장 / 나머지 → ★운영+시설+지원+주차
# 책임자(건마다 지목): 시설부=이정헌 소장 / 지원부=반장 / 운영부=이경연 실장
# 킬스위치: ops_digest_send.json overdue_alert_enabled (기본 true)
# ══════════════════════════════════════════════════════════════════════════
_OVD_ROOM_LESSON = "★부서장"
_OVD_ROOM_OPS = "★운영+시설+지원+주차"
#   ★2026-08-26 GM — 지원부 반장 성함을 받았다(여=이연희 반장 / 남=박남일 반장). 이름을
#   여기 적지 않고 정본(ssot/kpi.json `_부서반장_*`)에서 읽는다 — 팀 리더와 같은 방식(약속 L01).
#   이 dict 는 정본을 못 읽을 때만 쓰는 최소 폴백이라 이름이 아니라 직함만 둔다.
#   ★2026-08-28 GM 지시로 성별 구분 없는 "지원부"를 뺐다. GM 원문: "지원부 / 지원부(남) /
#   지원부(여) 이렇게 있던데 지원부 <삭제". 옛 데이터에 남은 "지원부" 값은 이제 「담당 미정」으로
#   나가고, 그래야 화면에서 사람이 남/여를 정한다 — 여자 반장님께 자동으로 넘기면 남자 구역 건이
#   조용히 잘못 배달된다(종전 폴백이 그랬다).
_OVD_LEADER_DEPT: dict = {
    "시설부": "소장", "지원부(남)": "반장", "지원부(여)": "반장",
    "운영부": "실장",
}


def _ovd_leaders() -> dict:
    """부서·종목별로 '부를 사람' 한 명. 부서 4종은 여기, 종목 팀은 정본에서 읽는다.

    ★2026-08-25 GM 지적 — 그날 아침 알림이 P.T팀 건 2개를 「담당 미정」으로 내보냈다.
      팀 리더 명단은 GM 이 여러 번 말씀하셨는데 저장소 어디에도 표로 없어서, 코드가
      부서 3종만 알고 있었다. 이름을 여기 또 적지 않고 정본(ssot/kpi.json 팀리더 표)에서
      읽는다 — 사람이 바뀌면 그 표만 고치면 된다(약속 L01).
    """
    out = dict(_OVD_LEADER_DEPT)
    try:
        import json as _json
        from pathlib import Path as _Path
        canon = _json.loads((_Path(__file__).resolve().parent.parent /
                             "ssot" / "kpi.json").read_text(encoding="utf-8"))
        for key, block in canon.items():
            if str(key).startswith("_팀리더") and isinstance(block, dict):
                for team, who in (block.get("teams") or {}).items():
                    if team and who:
                        out.setdefault(str(team), str(who))
            # 부서 책임자 정본은 폴백(직함만)을 덮어쓴다 — 이름이 있는 쪽이 이긴다.
            if str(key).startswith("_부서반장") and isinstance(block, dict):
                for dept, who in (block.get("depts") or {}).items():
                    if dept and who:
                        out[str(dept)] = str(who)
                # ★2026-08-28 — "지원부"로만 온 건을 여자 반장님께 자동으로 넘기던 줄을 지웠다.
                #   GM 이 그 부서를 없앴고, 남/여를 모르는 건은 사람이 정해야 한다(위 dict 주석).
                out.pop("지원부", None)
    except Exception:
        pass          # 정본을 못 읽어도 부서 4종은 그대로 동작한다(fail-soft)
    return out
_OVD_HEARTBEAT_ID = "overdue-reception-alert"
# 이 알림에서 빼는 분류.
#  · 분실물 접수 = 보관 성격(30일 주기)이라 매일 재촉할 일이 아니다.
#  · 직원·강사 칭찬합니다 = 기한(SLA)이 없는 분류다(정본 = GAS REG_CATEGORIES slaHours=null).
#    2026-08-20 실측에서 칭찬 1건(RECEPTION-114)이 「마무리 부탁드립니다」 목록에 섞여 나갔다 —
#    고맙다는 말을 밀린 일처럼 재촉한 셈이다. 22:30 적체 리마인드(_aging_block)는 이미 빼고
#    있었는데 이 아침 알림만 안 빼고 있었다.
_OVD_CAT_EXCLUDE = {"분실물 접수", "직원·강사 칭찬합니다"}


def _ovd_room_for(dept: str) -> str:
    d = str(dept or "").strip()
    return _OVD_ROOM_LESSON if ("강습" in d or d.endswith("팀")) else _OVD_ROOM_OPS


def _ovd_enabled() -> bool:
    try:
        return bool(json.loads(KILL_SWITCH.read_text(encoding="utf-8")).get("overdue_alert_enabled", True))
    except Exception:
        return True


def _ovd_already_sent_today() -> bool:
    from module_heartbeat import last_heartbeat
    rec = last_heartbeat(_OVD_HEARTBEAT_ID)
    return bool(rec) and str((rec.get("state") or {}).get("date", "")) == date.today().isoformat()


def _ovd_mark_sent() -> None:
    from module_heartbeat import record_heartbeat
    record_heartbeat(_OVD_HEARTBEAT_ID,
                     detail="기한 초과 접수 알림 발송",
                     extra={"state": {"date": date.today().isoformat()}})


# ★2026-08-20 GM 지적 — "부서랑 실무진 이름만 떠있는건 뭐야, 조금 더 친절하게".
#   종전 한 줄은 「🔴 35일 운영부 · 최준용M」 이 전부였다. 받는 사람은 그게 어떤 접수인지
#   모른 채 이름만 불린 셈이라, 화면에 들어가 스무 건을 뒤져야 자기 건을 찾을 수 있었다.
#   그래서 ①무슨 건인지(분류·장소·내용) ②어디서(링크 + 화면 안 위치) ③무엇을 하면 되나
#   (닫는 동작)를 넣는다 — 실무진 전달문 3줄 규칙(wellperion-gm-report §4-2-2).
#   ▸「N일째」 표기는 뺀다. 밀린 건 우리 사정이고 그 숫자는 압박만 될 뿐 무엇을 하라는
#     정보가 없다(같은 규칙). 대신 접수 날짜를 적는다 — 오래된 순 정렬은 그대로다.
_OVD_LIST_CAP = 0            # 0 = 전부 펼침(GM 지시 2026-08-30). 종전 8건
_OVD_CONTENT_CAP = 0         # 0 = 안 자름(GM 지시 2026-08-30). 종전 24자
_OVD_BOARD_URL = ("https://wellperion-cao.github.io/wellperion-automation/"
                  "coo/reception/종합접수처_현황.html")


def _ovd_short_cat(category: str) -> str:
    """「컴플레인 접수」→「컴플레인」 · 「직원·강사 쓴소리합니다」→「쓴소리」.
    분류 이름을 새로 정의하지 않는다 — 꼬리말만 떼서 줄인다(원본 = GAS REG_CATEGORIES)."""
    c = str(category or "").strip()
    for tail in (" 접수", "합니다"):
        if c.endswith(tail):
            c = c[: -len(tail)].strip()
    return c.replace("직원·강사 ", "")


def _ovd_who(row: dict, dept: str) -> str:
    """이 건을 실제로 부를 사람 한 명 = 그 부서 책임자.

    ★2026-08-21 GM 확정 — 접수처에 '담당' 칸이 없어졌다(사람 분류는 접수자·처리자 둘뿐).
      그전엔 담당자 이름을 먼저 봤는데, 그 값의 대부분이 자동으로 찍힌 방 이름(@운영부)이라
      실제로는 늘 부서 책임자로 떨어지고 있었다. 이제 그 한 갈래만 남긴다.
      처리자(handler)를 쓰지 않는 이유 = 이 블록은 '아직 안 끝난 건'만 다뤄 처리자가 비어 있다."""
    return _ovd_leaders().get(dept, "") or "담당 미정"


def _build_ovd_block(rows_for_room: list, detail: bool = True) -> str:
    """3일+ 미처리 접수 → 알림 블록. 완료·분실물은 이미 제외된 상태로 들어온다.

    detail=False — [2026-08-29 GM 지시 · 카톡 중복 정리] 건수 리마인드만 낸다.
    ★부서장 방은 같은 목록이 아침(여기)·저녁(build_lesson_digest) 하루 두 번 전문으로
    나갔다. 원문 펼침은 저녁 문의 통 한 곳으로 몰고 아침은 건수만 — 정보는 저녁에 그대로."""
    from collectors.ops_shared import reception_elapsed_days
    now = datetime.now()
    items: list = []
    for r in rows_for_room:
        days = reception_elapsed_days(r, now)
        if days < 3:
            continue
        dept = str(r.get("dept") or "").strip() or "부서 미정"
        content = " ".join(str(r.get("content") or "").split())
        if _OVD_CONTENT_CAP > 0:
            content = content[:_OVD_CONTENT_CAP]
        items.append({
            "days": days,
            "dept": dept,
            "who": _ovd_who(r, dept),
            "cat": _ovd_short_cat(r.get("category")),
            "loc": str(r.get("loc") or "").strip(),
            "content": content or "(내용 없음)",
            "when": "/".join(str(int(x)) for x in str(r.get("createdAt") or "")[5:10].split("-")
                             if x.isdigit()),
        })
    if not items:
        return ""
    items.sort(key=lambda x: -x["days"])
    if not detail:
        return "\n".join([
            f"🌅 하루의 시작 — 접수 {len(items)}건 · 목록은 저녁 정리 한 통에 담아 드립니다",
            f"📎 종합접수처 {_OVD_BOARD_URL}",
        ])
    shown, rest = (items, []) if _OVD_LIST_CAP <= 0 else (items[:_OVD_LIST_CAP], items[_OVD_LIST_CAP:])

    lines = [f"🌅 하루의 시작 — 아직 안 끝난 접수 {len(items)}건, 마무리 부탁드립니다",
             "회원분이 남겨 주신 뒤로 아직 안 닫힌 건들입니다."]
    for it in shown:
        icon = "🔴" if it["days"] >= 14 else ("🟠" if it["days"] >= 7 else "🟡")
        # 장소가 내용 첫머리에 이미 적혀 있으면 두 번 쓰지 않는다("헬스장 헬스장 기구를…").
        where = f"{it['loc']} " if it["loc"] and not it["content"].startswith(it["loc"]) else ""
        # 「N일째」 병기 — GM 지시 2026-08-29 "처리 안된 소요 일정 체크". 2026-08-20의
        # 'N일째 금지'는 재촉 문구 맥락이었고, 이번 지시가 소요일 표기를 명시적으로 요구해 대체한다.
        #
        # ★2026-08-31 두 줄로 갈랐다(GM "가독성 다 챙겼는지 확인해줘"). 종전엔 날짜·경과일·분류·
        #   장소·회원 원문·부서·담당을 한 줄에 ' · ' 로 이어 붙였다 — 컴플레인 원문이 길어 한 줄이
        #   휴대폰에서 대여섯 줄로 접혔고, 아홉 건이 붙으니 글자벽이 됐다. 실무진이 훑어서 자기
        #   부서 것을 찾는 통인데 훑을 수가 없었다.
        #   첫 줄 = 언제·얼마나 됐나·무슨 분류·누구 일 (훑는 줄)
        #   둘째 줄 = 회원이 남기신 내용 (읽는 줄, 들여쓰기 3칸)
        lines.append(f"{icon} {it['when']} · {it['days']}일째 [{it['cat']}] — {it['dept']} {it['who']}")
        lines.append(f"   {where}{it['content']}")
    if rest:
        lines.append(f"…그 밖에 {len(rest)}건이 더 있습니다(화면에서 보실 수 있습니다).")
    # 처리 세 걸음 — GM 지시 2026-08-29 "어떻게 처리하면 되는지에 대한 안내가 있어야함".
    lines.append(f"📎 종합접수처 {_OVD_BOARD_URL}")
    lines.append("① 확인 — 맨 위 부서 단추에서 본인 부서를 누르면 그 부서 것만 남습니다.")
    lines.append("② 처리 — 현장 조치 후 「처리자」에 성함, 「처리 메모」에 조치 내용 한 줄.")
    lines.append("③ 기록 — [저장] → [✅ 전달 완료]까지 눌러야 목록에서 내려갑니다.")
    return "\n".join(lines)


def _selfcheck_ovd_block() -> None:
    """빈 값·긴 내용에서도 한 줄이 서는지. 네트워크 없이 돈다.
    ▸2026-08-21: 접수처에 담당 칸이 없어져 픽스처에서도 뺐다 — 부를 사람은 부서 책임자다."""
    rows = [
        {"createdAt": "2026-07-16 09:00:00", "category": "컴플레인 접수", "dept": "운영부",
         "loc": "여자사우나", "content": "청결 관련 이용 가이드 필요" * 5, "status": "접수"},
        {"createdAt": "2026-08-14 09:00:00", "category": "시설물 고장 접수", "dept": "시설부",
         "loc": "", "content": "", "status": "접수"},
    ]
    out = _build_ovd_block(rows)
    assert "아직 안 끝난 접수 2건" in out, out
    assert "이경연 실장" in out and "이정헌 소장" in out, "부서 책임자로 떨어져야 한다"
    assert "@운영부" not in out, "방 이름을 사람 이름 자리에 쓰지 않는다"
    assert "일째" in out, "소요일(N일째) 표기가 있어야 한다(GM 지시 2026-08-29)"
    assert "① 확인" in out and "② 처리" in out and "③ 기록" in out, "처리 세 걸음 안내가 빠졌다"
    assert _OVD_BOARD_URL in out and "전달 완료" in out, "어디서·무엇을 하면 되는지가 빠졌다"
    assert max(len(x) for x in out.splitlines()) < 120, "카톡 한 줄이 너무 길다"
    print("[selfcheck] _build_ovd_block OK")


def _ovd_ready() -> bool:
    """기한 초과 접수 알림을 낼 준비가 됐는가 — 킬스위치+중복방지, 4부서방·★부서장
    공통 게이트. 한 실행 안에서 한 번만 확인한다(두 방이 절대시각 07:40·07:55로
    떨어져 있어도 이 실행 동안 상태가 바뀌지 않는다)."""
    if not _ovd_enabled():
        log("[ovd] 킬스위치 OFF — 생략")
        return False
    if _ovd_already_sent_today():
        log("[ovd] 이미 발송된 회차 — 생략")
        return False
    return True


def _send_ovd_room(room: str) -> bool:
    """기한 초과 접수를 방 하나에 발송(원장은 그때그때 새로 조회 — 07:40·07:55로 시각이
    떨어져 있어 값이 살짝 다를 수 있는 것이 자연스럽다). 반환=실제 발송 여부."""
    from collectors.ops_shared import RECEPTION_EXEC_URL, gas_get
    resp = gas_get(RECEPTION_EXEC_URL, {"action": "reg_list"}, timeout=20, label="ovd-alert")
    if resp is None:
        log("[ovd] 종합접수 조회 실패 — 생략")
        return False
    try:
        data = resp.json()
        rows = data.get("data", []) if data.get("ok") else []
    except Exception:
        log("[ovd] 응답 파싱 실패 — 생략")
        return False
    eligible = [r for r in rows
                if str(r.get("status", "")) not in {"완료"}
                and str(r.get("category") or "").strip() not in _OVD_CAT_EXCLUDE]
    room_rows = [r for r in eligible if _ovd_room_for(str(r.get("dept") or "")) == room]
    # ★부서장 아침 = 건수만(원문 펼침은 저녁 문의 통 한 곳 — 2026-08-29 GM 지시).
    # 📅 다가오는 일정은 이 통에 붙이지 않는다 — 별도 통(send_schedule_pings · 07:58).
    block = _build_ovd_block(room_rows, detail=(room != _OVD_ROOM_LESSON))
    if not block:
        log(f"[ovd] {room} — 3일+ 없음, 생략")
        return False
    cmd = [sys.executable, str(SENDER), "--message", block, "--only-room", room,
           "--sender", "아침정리다이제스트"]
    log(f"[ovd] 발송 → {room}")
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    out = (proc.stdout or "").strip()
    tail = out.splitlines()[-1] if out else "출력 없음"
    log(f"[ovd] rc={proc.returncode} · {tail}")
    return proc.returncode == 0 and "DONE" in out


# ─── 📅 다가오는 일정 별도 통 (GM 지시 2026-08-29 "별도로 만들자 전사일정링크를 태워서") ───
# 아침 통(접수·정리)에 끼워 붙이던 일정 칸을 독립된 짧은 통으로 뺐다. 부서 소관→4부서방 /
# 관리자 건→★중간관리자(같은 일정이 두 방에 안 겹치는 배타 분류는 _is_dept_schedule_item 그대로).
# 7일 안에 일정이 없으면 그 방 통 자체를 안 보낸다. 쿼리 없는 전사일정 링크를 맨 끝에 한 줄.
_SCHEDULE_PAGE_URL = ("https://wellperion-cao.github.io/wellperion-automation/"
                      "coo/check/전사_일정.html")
_SCHED_PING_HEARTBEAT_ID = "morning-schedule-ping"


def _sched_ping_already_sent_today() -> bool:
    from module_heartbeat import last_heartbeat
    rec = last_heartbeat(_SCHED_PING_HEARTBEAT_ID)
    return bool(rec) and str((rec.get("state") or {}).get("date", "")) == date.today().isoformat()


def send_schedule_pings() -> None:
    """📅 다가오는 일정 통 — ★중간관리자 방 1통. 하루 1회.

    ★2026-09-01 GM 지시 — "다가오는 일정은 전체 방 말고 중간관리자 방에만. 각 관리자들이
      챙길 수 있도록." 종전엔 4부서방(부서 소관)·★중간관리자(관리자 건)로 갈라 두 통을 보냈다.
      4부서방은 현장 실무진이 보는 자리라 일정 목록이 '내가 할 일'로 안 읽히고 흘러갔다.
      일정은 관리자가 받아 자기 사람에게 내려보내는 것이 맞다 — 그래서 한 방으로 모은다.
    ▸부서 소관 건도 함께 싣는다. 받는 사람이 관리자 한 자리로 바뀌었으니 갈라 둘 이유가 없다.
    ▸접지 않고 전부 싣는다(GM 2026-08-29 "줄을 접지 말고 건수를 줄여라") — 관리자가 챙기려면
      가려진 것이 없어야 한다.
    """
    # ★2026-09-01 GM 지시 — "주말에는 보내지마." 창이 이번 주 금요일까지라 토·일에는 남은
    #   일정이 없고, 쉬는 날 알림은 소음이다. 월요일 아침에 그 주 것을 다시 낸다.
    #   (_schedule_horizon 의 토·일 → 다음 주 금요일 처리는 손으로 돌려 볼 때를 위해 남겨 둔다.)
    if date.today().weekday() >= 5:
        log("[sched] 주말 — 일정 통 보내지 않음(GM 지시 2026-09-01)")
        return
    if _sched_ping_already_sent_today():
        log("[sched] 이미 발송된 회차 — 생략")
        return
    items = _upcoming_schedule_items()
    sent_any = False
    block = _build_schedule_block(items, show_all=True)
    if not block:
        log("[sched] 7일 내 일정 없음 — 통 생략")
    else:
        # 오늘 건이 있으면 담당자를 불러 준다 — 이름이 없으면 아무도 자기 일로 안 읽는다.
        _names = _todays_assignees(items)
        _who = (" · ".join(_names) if len(_names) <= 2 else "담당자분들") if _names else ""
        ask = (f"👉 오늘 건 {_who} — 본인 부서 건은 담당자에게 전달해 주시고, 끝나면 「완료」 한 마디만 남겨 주세요"
               if _who else
               "👉 본인 부서 건은 담당자에게 전달해 주시고, 끝나면 「완료」 한 마디만 남겨 주세요")
        msg = "\n".join([
            block,
            ask,
            f"📎 전사일정 {_SCHEDULE_PAGE_URL}",
            "   날짜·담당이 비어 있으면 이 화면에서 직접 채워 주시면 됩니다",
        ])
        # ★2026-09-01 GM 지시 — "중간관리자방 + 운영부방까지 공유하자."
        #   ★운영부는 답을 요구하지 않는 공유 전용 방이다(약속 L24) — 같은 통을 그대로 보내되
        #   묻는 자리는 ★중간관리자 한 곳으로 둔다. 같은 사람이 두 방에서 같은 걸 두 번 받는
        #   중복이지만, 일정은 놓치면 되돌릴 수 없어 GM 이 중복을 감수하기로 정했다.
        for _i, _room in enumerate((RELAY_ROOM, TARGET_ROOM)):
            if _i:
                time.sleep(SEND_STAGGER_SECONDS)   # 알림 두 개가 같은 초에 겹치지 않게
            cmd = [sys.executable, str(SENDER), "--message", msg, "--only-room", _room,
                   "--sender", "아침정리다이제스트"]
            log(f"[sched] 발송 → {_room}")
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            out = (proc.stdout or "").strip()
            log(f"[sched] rc={proc.returncode} · {out.splitlines()[-1] if out else '출력 없음'}")
            if proc.returncode == 0 and "DONE" in out:
                sent_any = True
    if sent_any:
        from module_heartbeat import record_heartbeat
        record_heartbeat(_SCHED_PING_HEARTBEAT_ID, detail="📅 다가오는 일정 통 발송",
                         extra={"state": {"date": date.today().isoformat()}})


# ══════════════════════════════════════════════════════════════════════════
# 아침 통 뒤 「당부 + 응원」 별도 한 통 (GM 지시 2026-09-01)
#
# GM 원문: "실무진 전달건은 신경 많이 써줘야해. 그리고 꼭 전달 후 추가로(이어쓰지말고
#   별도로) 꼭 진행 해달라는 당부와 응원글도 남겨줘."
# ▸왜 별도인가 — 목록 꼬리에 이어 쓰면 목록의 일부로 읽혀 그냥 지나간다. 한 통으로 따로
#   오면 그것만 읽힌다. 대신 짧아야 한다(3줄). 길면 이것도 목록이 된다.
# ▸어느 방에 — 오늘 아침 실제로 통이 나간 방에만. 아무것도 안 간 방에 응원만 가면 뜬금없다.
#   판정은 발신 로그(logs/kakao_sent-<날짜>.log)로 한다 — 상태값이 아니라 실제로 나간 기록이다.
# ▸매일 같은 문장이면 벽지가 된다. 요일로 갈라 쓴다(주 5종).
_CLOSING_HEARTBEAT_ID = "morning-closing-note"
_CLOSING_ROOMS = ("★운영+시설+지원+주차", "★운영부", "★중간관리자", "★부서장")
_CLOSING_BY_DOW = {
    0: "월요일입니다. 이번 주에 챙길 것이 위에 다 적혀 있으니 하나씩만 밟아 가시면 됩니다.",
    1: "어제 못 끝낸 것부터 보시면 오늘이 가벼워집니다.",
    2: "주 중간입니다. 밀린 것이 있으면 지금 손대는 편이 금요일이 편합니다.",
    3: "금요일 전에 마칠 수 있는 것부터 보시면 좋겠습니다.",
    4: "금요일입니다. 이번 주 안에 끝내기로 한 것만 마지막으로 확인 부탁드립니다.",
    5: "주말 근무 고생 많으십니다. 급한 것만 보시고 나머지는 월요일에 이어가시죠.",
    6: "주말 근무 고생 많으십니다. 급한 것만 보시고 나머지는 월요일에 이어가시죠.",
}


def _rooms_sent_this_morning(today=None) -> list:
    """오늘 07:00 이후 실무진 방으로 실제로 나간 통이 있는 방 목록(발신 로그 실측)."""
    today = today or date.today()
    path = ROOT / "logs" / f"kakao_sent-{today.isoformat()}.log"
    hit: list = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if not rec.get("ok"):
                continue
            if str(rec.get("ts", ""))[11:16] < "07:00":
                continue
            room = str(rec.get("chat_id") or "")
            if room in _CLOSING_ROOMS and room not in hit:
                hit.append(room)
    except FileNotFoundError:
        pass
    except Exception as exc:
        log(f"[closing] 발신 로그 읽기 실패 — 인사 생략: {exc}")
    return hit


def send_closing_note() -> None:
    """아침 통이 나간 방에 「당부 + 응원」 한 통. 하루 1회."""
    from module_heartbeat import last_heartbeat, record_heartbeat
    rec = last_heartbeat(_CLOSING_HEARTBEAT_ID)
    if rec and str((rec.get("state") or {}).get("date", "")) == date.today().isoformat():
        log("[closing] 이미 발송된 회차 — 생략")
        return
    rooms = _rooms_sent_this_morning()
    if not rooms:
        log("[closing] 오늘 아침 나간 통이 없음 — 인사 생략")
        return
    body = "\n".join([
        "🙌 오늘도 부탁드립니다",
        f"   {_CLOSING_BY_DOW[date.today().weekday()]}",
        "   처리하신 건은 「완료」 한 마디만 남겨 주시면 저희가 목록에서 내리겠습니다.",
        "   늘 챙겨 주셔서 고맙습니다.",
    ])
    sent_any = False
    for i, room in enumerate(rooms):
        if i:
            time.sleep(SEND_STAGGER_SECONDS)
        cmd = [sys.executable, str(SENDER), "--message", body, "--only-room", room,
               "--sender", "아침정리다이제스트"]
        log(f"[closing] 발송 → {room}")
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        out = (proc.stdout or "").strip()
        log(f"[closing] rc={proc.returncode} · {out.splitlines()[-1] if out else '출력 없음'}")
        if proc.returncode == 0 and "DONE" in out:
            sent_any = True
    if sent_any:
        record_heartbeat(_CLOSING_HEARTBEAT_ID, detail="🙌 아침 당부·응원 발송",
                         extra={"state": {"date": date.today().isoformat()}})


def _selfcheck_closing_note() -> None:
    """문구가 요일마다 다르고, 빈 줄 없이 4줄인지. 네트워크 없이 돈다."""
    seen = {v for k, v in _CLOSING_BY_DOW.items() if k <= 4}
    assert len(seen) == 5, "평일 다섯 날 문구가 서로 달라야 한다(같으면 벽지가 된다)"
    for d in range(7):
        b = "\n".join(["🙌 오늘도 부탁드립니다", f"   {_CLOSING_BY_DOW[d]}",
                       "   처리하신 건은 「완료」 한 마디만 남겨 주시면 저희가 목록에서 내리겠습니다.",
                       "   늘 챙겨 주셔서 고맙습니다."])
        assert len(b.splitlines()) == 4, b
        assert all(ln.strip() for ln in b.splitlines()), "빈 줄을 넣지 않는다"
    print("[selfcheck] closing_note OK")


def _seconds_until(hour: int, minute: int, now: "datetime | None" = None) -> float:
    """지금부터 오늘 그 시각까지 남은 초. 이미 지났으면 0 — 앞 단계(내보내기·다이제스트
    생성)가 늦어져도 다음날까지 기다리지 않고 바로 진행한다(순서만 지킨다)."""
    now = now or datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return max((target - now).total_seconds(), 0.0)


def _sleep_until(hour: int, minute: int) -> None:
    wait = _seconds_until(hour, minute)
    if wait:
        log(f"[schedule] {hour:02d}:{minute:02d} 까지 {int(wait)}초 대기")
        time.sleep(wait)


def _selfcheck_seconds_until() -> None:
    """절대시각 대기 계산 — 미래면 그만큼, 과거면 0(다음날까지 기다리지 않는다). 네트워크 없이 돈다."""
    now = datetime(2026, 8, 29, 7, 30, 0)
    assert _seconds_until(7, 40, now) == 600, _seconds_until(7, 40, now)
    assert _seconds_until(7, 45, now) == 900
    assert _seconds_until(7, 55, now) == 1500
    late = datetime(2026, 8, 29, 7, 50, 0)
    assert _seconds_until(7, 40, late) == 0, "이미 지난 시각은 0초여야 한다(다음날까지 대기 금지)"
    assert _seconds_until(7, 50, late) == 0, "정확히 그 시각도 0초"
    print("[selfcheck] _seconds_until OK")


def main() -> int:
    if sys.platform != "win32":
        print("FAILED: Windows 전용")
        return 1
    ap = argparse.ArgumentParser(description="★운영부 아침 다이제스트 발송")
    ap.add_argument("--force", action="store_true", help="킬스위치·오늘조건 무시(수동 검증)")
    ap.add_argument("--dry-run", action="store_true", help="미발송")
    ap.add_argument("--relay-preview", action="store_true",
                    help="사람 처리 배 전달 본문만 렌더(방에 손 안 댐 · 발신·지문기록 없음)")
    ap.add_argument("--mgr-preview", action="store_true",
                    help="★중간관리자 결정거리 요약 본문만 렌더(방에 손 안 댐 · 발신·지문기록 없음)")
    args = ap.parse_args()

    if args.relay_preview:
        return preview_relays()

    if args.mgr_preview:
        return preview_mgr_brief()

    if not args.force and not kill_switch_enabled():
        log(f"킬스위치 OFF({KILL_SWITCH}) — 발송 생략")
        print("SKIPPED: 킬스위치 비활성")
        return 0

    # ★2026-08-08 GM 지시로 여기 있던 독립 relay 발송(send_relays)은 중단했다 — '사람이
    # 처리할 업무' 전달은 ★중간관리자 통합본(build_mgr_daily_brief → send_mgr_brief)이
    # 대신 싣는다(배238·544, 2026-08-11 웰리 배선). 이 자리엔 이제 아무것도 없다.

    # 기한 초과 접수(4부서방·★부서장) 킬스위치+중복방지는 여기서 한 번만 본다 — 이 실행이
    # 07:40부터 07:55까지 15분을 걸치는 동안 상태가 바뀌지 않는다.
    ovd_ready = _ovd_ready()
    sent_ovd_ops = sent_ovd_lesson = False

    # 절대시각 4통 — 4부서방 07:40 → ★운영부 07:45 → ★중간관리자 07:50 → ★부서장 07:55
    # (GM 확정 배826 재승인 2026-08-29). dry-run 은 방에 손대지 않으므로 대기·mgr·ovd 는
    # 그대로 건너뛴다(종전과 같음 · 미리보기는 --mgr-preview/--relay-preview 로 따로 본다).
    if not args.dry_run:
        _sleep_until(*MORNING_SEND_TIMES["4부서방"])
        if ovd_ready:
            try:
                sent_ovd_ops = _send_ovd_room(_OVD_ROOM_OPS)
            except Exception as exc:
                log(f"[ovd] 4부서방 예외 — 다음 회차 재시도: {type(exc).__name__}: {exc}")

        _sleep_until(*MORNING_SEND_TIMES["★운영부"])
    rc = _send_ops_room(args)

    # ★중간관리자 — ★운영부 결과와 무관하게 시도한다(방마다 독립 · 2026-08-15 수리,
    # send_mgr_brief docstring 참조).
    if not args.dry_run:
        _sleep_until(*MORNING_SEND_TIMES["★중간관리자"])
        try:
            send_mgr_brief()
        except Exception as exc:
            log(f"[mgr] 예외 — 다음 회차 재시도: {type(exc).__name__}: {exc}")

        _sleep_until(*MORNING_SEND_TIMES["★부서장"])
        if ovd_ready:
            try:
                sent_ovd_lesson = _send_ovd_room(_OVD_ROOM_LESSON)
            except Exception as exc:
                log(f"[ovd] ★부서장 예외 — 다음 회차 재시도: {type(exc).__name__}: {exc}")
        if sent_ovd_ops or sent_ovd_lesson:
            _ovd_mark_sent()

        # 📅 다가오는 일정 별도 통 — 아침 4통이 다 나간 뒤 07:58 (GM 지시 2026-08-29).
        _sleep_until(*MORNING_SEND_TIMES["일정"])
        try:
            send_schedule_pings()
        except Exception as exc:
            log(f"[sched] 예외 — 다음 회차 재시도: {type(exc).__name__}: {exc}")

        # 🙌 당부·응원 별도 통 — 아침 통이 다 나간 뒤 08:02 (GM 지시 2026-09-01).
        _sleep_until(*MORNING_SEND_TIMES["마무리인사"])
        try:
            send_closing_note()
        except Exception as exc:
            log(f"[closing] 예외 — 다음 회차 재시도: {type(exc).__name__}: {exc}")
    return rc


def _send_ops_room(args) -> int:
    """★운영부 아침 다이제스트 발송 본체 — 기존 main() 몸통을 그대로 옮긴 것(2026-08-15).
    옮긴 이유 하나뿐: 이 함수의 조기 return 들이 ★중간관리자 발송까지 삼키지 않게."""
    if not PENDING.exists():
        print(f"FAILED: 대기 다이제스트 없음 — {PENDING}")
        return 1
    data = json.loads(PENDING.read_text(encoding="utf-8"))
    message = (data.get("message") or "").strip()
    if not message:
        print("FAILED: 다이제스트 메시지가 비어 있음")
        return 1

    today = datetime.now().strftime("%Y-%m-%d")
    gen_today = str(data.get("generated_at", "")).startswith(today)
    already = bool(data.get("sent"))
    if not args.force:
        if already:
            log("이미 발송된 회차(sent=true) — 중복 발송 생략")
            print("SKIPPED: 이미 발송됨")
            return 0
        if not gen_today:
            log(f"대기 다이제스트가 오늘 생성분이 아님(generated_at={data.get('generated_at')}) — 옛 회차 재발송 방지, 생략")
            print("SKIPPED: 오늘 생성분 아님")
            return 0

    done_prev, done_bootstrap = _done_state()
    done_section, done_current = build_done_section(_fetch_todo_rows(), done_prev,
                                                    exclude_text=message)
    if done_bootstrap:
        done_section = ""  # 최초실행 — 과거 완료건 일괄 스팸 방지, 스냅샷만 찍고 이번엔 침묵
    if done_section:
        message = f"{message}\n\n{done_section}"

    # --sender 아침정리다이제스트 — kakao_report_sender 의 사람 방 발신 가드(배 11070 ⑤) 통과용.
    cmd = [sys.executable, str(SENDER), "--message", message, "--only-room", TARGET_ROOM,
           "--sender", "아침정리다이제스트"]
    if args.dry_run:
        cmd.append("--dry-run")
    log(f"[send] 다이제스트 발송(대상 {data.get('date')}) → {TARGET_ROOM}")
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    out = (proc.stdout or "").strip()
    tail = out.splitlines()[-1] if out else "출력 없음"
    log(f"[send] 결과 rc={proc.returncode} · {tail}")
    if proc.returncode == 0 and "DONE" in out:
        if not args.dry_run:
            data["sent"] = True
            data["sent_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            PENDING.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            if done_bootstrap or done_current != done_prev:
                _save_done_state(done_current)
            # 배698(2026-08-19) — 다음날 흡수 판단(ops_daily_digest.pick_target_dates)이 쓰는
            # "마지막 발송일" 하트비트. data["date"]는 흡수본이면 최근 날짜(끝일)라 이 값이
            # 그 이전 날짜를 다시 흡수 대상으로 잡지 않는다.
            _record_last_sent(_LAST_SENT_HEARTBEAT_OPS, data.get("date"))
            # ★중간관리자 발송은 여기(성공 분기 안)에 있다가 main() 끝의 send_mgr_brief()
            # 호출로 나갔다(2026-08-15 — ★운영부 실패·기발송이 mgr 재시도를 삼키던 것 수리).
        print(f"DONE: 다이제스트 발송 완료 — {TARGET_ROOM}")
        return 0
    print(f"FAILED: 발송 실패(rc={proc.returncode}) — {tail}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
