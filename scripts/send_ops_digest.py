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
from datetime import date, datetime
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


def build_done_section(rows: list, prev_ids: dict) -> "tuple[str, dict]":
    """운영부 담당자(OPS_STAFF) 몫 중 상태='완료'인 건에서 지난 회차 이후 새로
    완료된 것만 골라 절로 만든다. 비교 키 = 시트 행 id 고정(업무명은 바뀔 수 있다 —
    relay 구간의 task_id 교훈과 동일). 반환 (섹션 텍스트, 현재 완료건 {id: 표시줄}) —
    두 번째 값은 변화가 없어도 다음 회차 비교용으로 그대로 저장한다."""
    done = _ops_done_rows(rows)
    current = {str(r["id"]): f"{str(r.get('업무명', '')).strip()} — {str(r.get('담당자', '')).strip()} 완료"
               for r in done}

    new_ids = [k for k in current if k not in prev_ids]
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
# 이 함수는 그 message를 몸통으로 쓰고, 업무 시트 완료건은 뒤에 덧붙인다.
#
# 대화 정리가 없으면(원문 미수집 등) 「어제 완료」만 낸다. 낼 게 없으면 빈 문자열 = 발송 안 함
# (GM 지시: 억지로 채우지 않는다 — 잘못된 것을 보내느니 안 보낸다).
#
# ★2026-08-11 웰리 — 세 번째 절 「열린 요청」 추가(배238·544). send_ops_digest 의
# 옛 사람전달(send_relays)이 2026-08-08 GM 지시로 꺼진 뒤, 각 배의 staff_message(예:
# "법정·정기점검 15건 실시일 확인해 주세요")가 3일째 어떤 방에도 안 나가고 있었다.
# 새 스냅샷·새 발신기를 만들지 않는다(약속 L21) — 이미 있던 relay_routes/
# build_relay_message(델타 비교·RELAY_SHOW_N=5 상한 포함)를 그대로 불러 절 하나로 붙인다.
# 상태 저장은 여기서 안 한다(미리보기가 상태를 건드리면 안 됨) — 실제 발송 성공 후
# main()이 relay_current를 저장한다.
# ══════════════════════════════════════════════════════════════════════════
MGR_DAILY_SHOW_N = 3
MGR_DAILY_HEARTBEAT_ID = "mgr-daily-brief-sent"

# ══════════════════════════════════════════════════════════════════════════
# 📮 회신 부탁 절 (2026-08-15 GM 승인 · C안) — 물음은 나가는데 답을 세는 곳이 없어
# 미회신이 쌓이던 것(8/15 실측 14건)을, 이미 매일 나가는 ★중간관리자 아침 정리 끝에
# 절 하나로 흡수한다(약속 L21 — 새 스크립트·새 예약 0).
#
# 재료 = 그 방 원장(_digest_ledger.json · ops_daily_digest 가 매일 쌓는 이슈 목록).
# 어제(target_date)치 열린 건은 정리문의 ⚠️ 절이 이미 다루므로 여기선 **그 전날들** 것만 —
# 어제 대화에 다시 안 나와 ⚠️ 에서 빠졌지만 답도 안 온 건이 이 절의 몫이다.
#
# ★말투(GM 확정 · 8/15 손발신 표준): 감사 먼저(실제 해 주신 것을 이름 붙여) → 남은 것 →
# 답하는 법을 낮춘다("한 마디면 됩니다") → "한꺼번에 안 주셔도 됩니다".
# 'N일째'·'아직도'·'재요청' 금지 — 밀린 건 우리 사정이고 그 표기는 압박만 준다.
# 되돌리기 = build_mgr_daily_brief 안의 build_reply_nudge 호출 한 줄만 지우면 절이 사라진다.
# ══════════════════════════════════════════════════════════════════════════
MGR_LEDGER = MGR_PENDING.parent / "_digest_ledger.json"
NUDGE_LOOKBACK_DAYS = 7   # 이보다 오래된 건 원장에서 안 꺼낸다(오래 묵은 건 웰리가 사람으로 판단)
NUDGE_SHOW_N = 3          # 사람당 이 이상은 다음 회차로 — 길면 아무도 안 읽는다
NUDGE_TITLE_CAP = 46      # _bridge_ask_lines 와 같은 한 줄 상한
# ★중간관리자 방 구성원(수신자). 담당이 운영부 실무진(윤병현AM 등)인 건은 약속 L24
# (운영부는 실장 경유)에 따라 이경연 실장 묶음에 싣되, 줄에 원 담당 이름을 남긴다.
_NUDGE_MEMBERS = ["이경연 실장", "이정헌 소장", "나우열M"]


def _nudge_norm(s: str) -> str:
    return re.sub(r"[\s·\-—()\[\]+/,.]+", "", str(s or ""))


def _nudge_similar(a: str, b: str) -> bool:
    """같은 건인가 — ops_daily_digest._schedule_is_dup 과 같은 규칙(포함 또는 0.6 유사)."""
    from difflib import SequenceMatcher
    na, nb = _nudge_norm(a), _nudge_norm(b)
    if not na or not nb:
        return False
    return na in nb or nb in na or SequenceMatcher(None, na, nb).ratio() >= 0.6


def build_reply_nudge(target_date: str) -> str:
    """📮 회신 부탁 절 — 원장에서 '전날들의 열린 건(담당 있음)'을 사람별로 묶어 돌려준다.

    거르는 것: ①어제(target_date) 대화에 나온 건(⚠️/✅ 절이 담당) ②나중에 resolved 로
    닫힌 건 ③담당 빈칸(주인 없는 일은 사람한테 묻지 않는다 · 약속 L23) ④서로 닮은 중복
    (최신 문구만 남김). 낼 게 없으면 빈 문자열 = 절 자체가 안 실린다."""
    from datetime import timedelta
    try:
        ledger = json.loads(MGR_LEDGER.read_text(encoding="utf-8"))
        t = date.fromisoformat(target_date)
    except Exception:
        return ""
    lo = (t - timedelta(days=NUDGE_LOOKBACK_DAYS - 1)).isoformat()
    window = [e for e in ledger
              if isinstance(e, dict) and lo <= str(e.get("date", "")) <= target_date]

    resolved_texts, today_texts = [], []
    latest_thanks: dict = {}      # member -> 감사할 실제 건(시간순 순회라 마지막 값=최신)
    for e in sorted(window, key=lambda x: str(x.get("date", ""))):
        for it in e.get("issues") or []:
            title = str(it.get("issue") or "").strip()
            if not title:
                continue
            if str(it.get("status") or "") == "resolved":
                resolved_texts.append(title)
                owner = str(it.get("owner") or "").strip()
                if owner in _NUDGE_MEMBERS:
                    latest_thanks[owner] = title
            if str(e.get("date", "")) == target_date:
                today_texts.append(title)

    kept: dict = {}               # member -> [줄], 최신 날짜부터 채운다
    extra: dict = {}              # member -> 상한 넘어 접은 건수
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
            member = owner if owner in _NUDGE_MEMBERS else _NUDGE_MEMBERS[0]
            rows = kept.setdefault(member, [])
            if any(_nudge_similar(title, r) for r in rows):
                continue
            if len(rows) >= NUDGE_SHOW_N:
                extra[member] = extra.get(member, 0) + 1
                continue
            tag = f"({owner} 건) " if owner != member else ""
            rows.append(tag + _cap_line(title, NUDGE_TITLE_CAP))

    if not kept:
        return ""
    lines = ["📮 답 주시면 좋은 것들 — 각 건 한 마디면 충분합니다(진행 중/완료/날짜 하나)"]
    for member in _NUDGE_MEMBERS:
        rows = kept.get(member)
        if not rows:
            continue
        if member in latest_thanks:
            lines.append(f"🙏 {member}님, {_cap_line(latest_thanks[member], NUDGE_TITLE_CAP)} 처리해 주셔서 감사합니다.")
        else:
            lines.append(f"🙏 {member}님께")
        lines += [f" · {r}" for r in rows]
        if extra.get(member):
            lines.append(f" · 나머지 {extra[member]}건은 다음에 나눠 여쭙겠습니다")
    lines.append("한꺼번에 안 주셔도 됩니다 — 편하실 때 한 줄씩이면 충분합니다.")
    return "\n".join(lines)


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

    done = [r for r in _ops_done_rows(rows) if str(r.get("수정일", "") or "").startswith(target_date)]
    if done:
        names = ", ".join(str(r.get("업무명", "")).strip()
                          for r in done[:MGR_DAILY_SHOW_N] if str(r.get("업무명", "")).strip())
        tail = f" 외 {len(done) - MGR_DAILY_SHOW_N}건" if len(done) > MGR_DAILY_SHOW_N else ""
        done_line = f"✅ 어제 완료 {len(done)}건({names}{tail})"
        if convo:
            parts.append(done_line)  # 대화 정리가 이미 제목을 갖고 있으니 완료줄만 덧붙인다
        else:
            _, m, d = target_date.split("-")
            parts.append(f"🧭 {int(m)}/{int(d)} 어제 정리 — 판단·배정 필요한 것만\n{done_line}")

    relay_state = _relay_state()
    _migrate_relay_state(relay_state)
    room, contacts = relay_routes()[0]
    open_msg, relay_current = build_relay_message(contacts, relay_state.get(room, {}))
    if open_msg:
        parts.append(open_msg)

    # 📮 회신 부탁 절(C안 · GM 승인 2026-08-15) — 이 한 줄만 지우면 절이 사라진다(역롤백).
    nudge = build_reply_nudge(target_date)
    if nudge:
        parts.append(nudge)

    return "\n\n".join(parts), relay_current


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
RELAY_SHOW_N = 5            # 본문에 줄로 싣는 건수 — 나머지는 "외 N건"으로 접는다
RELAY_TITLE_CAP = 34        # 스냅샷(닫힘 표시용) 길이 상한(카톡 한 줄)
RELAY_HEARTBEAT_ID = "clevel-queue-human-relay"  # 지난 회차 목록 보관 = 상설 하트비트 1파일
RELAY_STALE_DAYS = 7  # ★2026-08-13 근본수정(배592) — 내용 안 바뀐 채 이만큼 묵으면 재알림.
#   그 전엔 task_id 키가 한 번 스냅샷에 들어가면 내용이 바뀌어도 다시는 '새 업무'가
#   안 됐다(배364·379 실측). 짧게 잡으면 실무진 신뢰를 깎으니 주간 주기로 둔다.
# 실무진이 받는 글에는 누가 보내는지가 드러나야 한다(unassigned_nudge.AI_SIGNOFF 와 같은 형식).
# 전달 주체는 웰리 — GM 원문 "각기 담당자 이름 적어서 웰리가 전달".
RELAY_SIGNOFF = "웰페리온 AI 총괄 담당 웰리 드림"
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
    #   ▸시모(GM 직접 담당)·웰리(두 방에 직접 쓴다 · L24)는 넣지 않는다 — 중복 발신이 된다.
    contacts.setdefault("cto", "이경연 실장")
    contacts.setdefault("coo", "이경연 실장")
    return [(RELAY_ROOM, contacts)]


ARCHIVE_PATH = ROOT / "status" / "_queue_archive.json"


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


def _is_done(task_id: str, queue: list, archive_cache: list) -> bool:
    """이 task_id 가 실제로 완료됐는가 — 큐 안에서 status 가 DONE/완료이거나, 큐에서
    아예 사라졌는데 보관함(queue_archive_sweep.py 가 terminal 배만 옮긴다)에 있으면
    완료로 본다. 큐에 그대로 남아 PENDING/IN_PROGRESS 인 채 staff_message 가 지워지거나
    audience 가 바뀌기만 한 배는 완료가 아니다(2026-08-06 GM 근본수정 — 그런 배를
    '✅ 처리 완료'로 오보하던 문제)."""
    for s in queue:
        if isinstance(s, dict) and str(s.get("task_id", "")) == task_id:
            return str(s.get("status", "")) in ("DONE", "완료")
    return any(isinstance(s, dict) and str(s.get("task_id", "")) == task_id for s in archive_cache)


def _load_archive() -> list:
    try:
        data = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _cap_line(text: str, cap: int = RELAY_TITLE_CAP) -> str:
    """카톡 한 줄용 길이 상한 — 낱말 한가운데서 자르지 않는다(GM 상시 지시).

    상한 안에서 마지막 띄어쓰기까지만 남긴다. 띄어쓰기가 아예 없으면(붙여 쓴 긴 문장)
    어쩔 수 없이 길이로 자른다 — 그때는 잘린 티가 나는 게 뜻이 끊기는 것보다 낫다."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(t) <= cap:
        return t
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
    text = str(ship.get("staff_message") or "").strip()
    return bool(text) and text.strip(".…").lower() not in _EMPTY_STAFF_MESSAGE


def build_relay_message(contacts: dict, prev_items: dict) -> "tuple[str, dict]":
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
    dropped_why = {"닫힌 배": 0, "AI 내부 살림": 0, "전달문 비어 있음": 0, "audience 칸 비어 있음": 0}
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
        ships.append(x)
    log(f"[relay] 실을 배 {len(ships)}척 · 제외 "
        + (" · ".join(f"{k} {v}" for k, v in dropped_why.items() if v) or "없음"))
    ships.sort(key=lambda x: (_RELAY_WEIGHT.get(x.get("priority"), 9),
                              str(x.get("enqueued_at", ""))))

    if _is_legacy_snapshot(prev_items):
        today = date.today().isoformat()
        current = {_relay_key(s): {"line": _cap_line(str(s["staff_message"]).strip().splitlines()[0]),
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
        line = _cap_line(str(s["staff_message"]).strip().splitlines()[0])
        if k not in prev_lines or prev_lines[k] != line:
            new_ships.append(s)
            current[k] = {"line": line, "last_sent": today}
        elif _is_stale(prev_sent[k], today):
            stale_ships.append(s)
            current[k] = {"line": line, "last_sent": today}  # 재알림 보냈으니 시계 리셋
        else:
            current[k] = {"line": line, "last_sent": prev_sent[k]}  # 변화 없음 — 시계 유지

    # ★'완료'는 목록에서 사라진 것 전부가 아니라, 실제로 DONE/보관함행인 것만(위 _is_done).
    #   staff_message 가 지워지거나 audience 가 바뀌어 사라진 배는 아직 진행 중일 수 있다 —
    #   그런 배까지 '✅ 처리 완료'로 실무진에게 보내면 오보다.
    dropped = [k for k in prev_lines if k not in current]
    if dropped:
        archive_cache = _load_archive()
        closed = [prev_lines[k] for k in dropped if _is_done(k, queue, archive_cache)]
    else:
        closed = []
    if not new_ships and not stale_ships and not closed:
        return "", current  # 지난번과 같은 목록 — 다시 보내지 않는다

    who = {contacts[s["clevel"]] for s in ships}
    solo = who.pop() if len(who) == 1 else None
    # ★2026-08-18 GM 지적 — "사람이 처리할 업무"는 문구 자체가 별로다. 읽는 쪽에서 보면
    # 'AI가 못 하니 너희가 해라' 로 들린다. 우리가 부탁드리는 자리임을 문장이 먼저 밝힌다.
    lines = [f"📌 오늘 확인 부탁드릴 것 {len(ships)}건" + (f" — {solo}" if solo else "")]
    if new_ships:
        lines.append(f"🆕 새로 생긴/바뀐 업무 {len(new_ships)}건")
        for s in new_ships[:RELAY_SHOW_N]:
            tail = "" if solo else f" · {contacts[s['clevel']]}"
            gm_tag = f"[GM업무 {s['gm_task_id']}] " if s.get("gm_task_id") else ""
            lines.append(f" • {gm_tag}{str(s['staff_message']).strip()}{tail}")
        overflow_new = new_ships[RELAY_SHOW_N:]
        if overflow_new:
            lines.append(f" • 외 {len(overflow_new)}건")
            log(f"[relay] 상한({RELAY_SHOW_N}건) 초과 — {len(overflow_new)}건 다음 회차로 이월")
            # ★한 번도 안 보여준 건을 '봤다'고 스냅샷에 찍으면 다음 회차에 영영 안 나온다
            #   (new_ships 판정이 prev_items 키 존재로만 갈리므로). 안 보여준 건은 이번
            #   스냅샷에서 뺀다 — 다음 회차에 다시 '신규'로 잡혀 우선순위 순서대로 드러난다.
            for s in overflow_new:
                current.pop(_relay_key(s), None)
    if stale_ships:
        lines.append(f"🔁 오래 열려 있어 재확인 {len(stale_ships)}건")
        for s in stale_ships[:RELAY_SHOW_N]:
            tail = "" if solo else f" · {contacts[s['clevel']]}"
            gm_tag = f"[GM업무 {s['gm_task_id']}] " if s.get("gm_task_id") else ""
            lines.append(f" • {gm_tag}{str(s['staff_message']).strip()}{tail}")
        overflow_stale = stale_ships[RELAY_SHOW_N:]
        if overflow_stale:
            lines.append(f" • 외 {len(overflow_stale)}건")
    if closed:
        lines.append(f"✅ 처리 완료 {len(closed)}건")
        for snap in closed[:RELAY_SHOW_N]:
            lines.append(f" • {snap}")
        if len(closed) > RELAY_SHOW_N:
            lines.append(f" • 외 {len(closed) - RELAY_SHOW_N}건")
    lines.append(RELAY_SIGNOFF)
    return "\n".join(lines), current


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
    """방에 손대지 않고 본문만 렌더해 보여준다(실방 검증용 — 발신·상태기록 없음)."""
    state = _relay_state()
    _migrate_relay_state(state)   # 실제 발신과 같은 조건으로 봐야 미리보기가 미리보기다
    for room, contacts in relay_routes():
        message, _current = build_relay_message(contacts, state.get(room, {}))
        print(f"\n===== {room} ({'내용 없음' if not message else '발신 대상'}) =====")
        print(message or "(변화 없음 — 발신 안 함)")
        if message:
            body = message.splitlines()
            assert body[-1] == RELAY_SIGNOFF, "AI 주체 서명 누락"
            assert "PENDING" not in message and "task_id" not in message, "내부 상태값 노출"
    return 0


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
    mcmd = [sys.executable, str(SENDER), "--message", mgr_msg, "--only-room", WEEKLY_ROOM]
    log(f"[mgr] 결정거리 요약 발송(대상 {target_date}) → {WEEKLY_ROOM}")
    mproc = subprocess.run(mcmd, capture_output=True, text=True, encoding="utf-8")
    mout = (mproc.stdout or "").strip()
    if mproc.returncode == 0 and "DONE" in mout:
        _mark_mgr_sent(target_date)
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
_OVD_LEADER: dict = {
    "시설부": "이정헌 소장",
    "지원부": "반장", "지원부(남)": "반장", "지원부(여)": "반장",
    "운영부": "이경연 실장",
}
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
_OVD_LIST_CAP = 8            # 본문에 펼치는 최대 건수(나머지는 아래 한 줄로 접는다)
_OVD_CONTENT_CAP = 24        # 내용 요약 길이 — 카톡 한 줄을 넘기지 않는 선
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
    """이 건을 실제로 부를 사람 한 명. 담당자 이름이 없거나 방 이름(@운영부)이면 부서 책임자."""
    names = [str(x).strip() for x in (row.get("assigneeCanon") or []) if str(x).strip()]
    if not names:
        one = str(row.get("assignee") or "").strip()
        names = [one] if one else []
    names = [n for n in names if not n.startswith("@")]
    return "/".join(names) if names else (_OVD_LEADER.get(dept, "") or "담당 미정")


def _build_ovd_block(rows_for_room: list) -> str:
    """3일+ 미처리 접수 → 알림 블록. 완료·분실물은 이미 제외된 상태로 들어온다."""
    from collectors.ops_shared import reception_elapsed_days
    now = datetime.now()
    items: list = []
    for r in rows_for_room:
        days = reception_elapsed_days(r, now)
        if days < 3:
            continue
        dept = str(r.get("dept") or "").strip() or "부서 미정"
        content = " ".join(str(r.get("content") or "").split())[:_OVD_CONTENT_CAP]
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
    shown, rest = items[:_OVD_LIST_CAP], items[_OVD_LIST_CAP:]

    lines = [f"⏰ 아직 안 끝난 접수 {len(items)}건 — 마무리 부탁드립니다",
             "회원분이 남겨 주신 뒤로 아직 안 닫힌 건들입니다."]
    for it in shown:
        icon = "🔴" if it["days"] >= 14 else ("🟠" if it["days"] >= 7 else "🟡")
        # 장소가 내용 첫머리에 이미 적혀 있으면 두 번 쓰지 않는다("헬스장 헬스장 기구를…").
        where = f"{it['loc']} " if it["loc"] and not it["content"].startswith(it["loc"]) else ""
        lines.append(f"{icon} {it['when']} [{it['cat']}] {where}{it['content']}"
                     f" — {it['dept']} {it['who']}")
    if rest:
        lines.append(f"…그 밖에 {len(rest)}건이 더 있습니다(화면에서 보실 수 있습니다).")
    lines.append(f"📎 종합접수처 {_OVD_BOARD_URL}")
    lines.append("   → 맨 위 부서 단추에서 본인 부서를 누르시면 그 부서 것만 남습니다.")
    lines.append("처리하신 건은 「처리자」에 성함, 「처리 메모」에 한 줄 남기고 "
                 "[저장] → [✅ 전달 완료]까지 눌러 주시면 목록에서 내려갑니다.")
    return "\n".join(lines)


def _selfcheck_ovd_block() -> None:
    """빈 값·방 이름 담당자·긴 내용에서도 한 줄이 서는지. 네트워크 없이 돈다."""
    rows = [
        {"createdAt": "2026-07-16 09:00:00", "category": "컴플레인 접수", "dept": "운영부",
         "loc": "여자사우나", "content": "청결 관련 이용 가이드 필요" * 5,
         "assigneeCanon": ["@운영부"], "status": "접수"},
        {"createdAt": "2026-08-14 09:00:00", "category": "시설물 고장 접수", "dept": "시설부",
         "loc": "", "content": "", "assignee": "", "status": "접수"},
    ]
    out = _build_ovd_block(rows)
    assert "아직 안 끝난 접수 2건" in out, out
    assert "이경연 실장" in out and "이정헌 소장" in out, "담당 공란·방이름이면 책임자로 떨어져야 한다"
    assert "@운영부" not in out, "방 이름을 사람 이름 자리에 쓰지 않는다"
    assert "일째" not in out and "일 운영부" not in out, "N일 표기는 쓰지 않는다"
    assert _OVD_BOARD_URL in out and "전달 완료" in out, "어디서·무엇을 하면 되는지가 빠졌다"
    assert max(len(x) for x in out.splitlines()) < 120, "카톡 한 줄이 너무 길다"
    print("[selfcheck] _build_ovd_block OK")


def send_overdue_reception_alerts() -> None:
    """기한 초과 접수를 ★부서장·★운영+시설+지원+주차 방에 아침 1회 발송."""
    if not _ovd_enabled():
        log("[ovd] 킬스위치 OFF — 생략")
        return
    if _ovd_already_sent_today():
        log("[ovd] 이미 발송된 회차 — 생략")
        return
    from collectors.ops_shared import RECEPTION_EXEC_URL, gas_get
    resp = gas_get(RECEPTION_EXEC_URL, {"action": "reg_list"}, timeout=20, label="ovd-alert")
    if resp is None:
        log("[ovd] 종합접수 조회 실패 — 생략")
        return
    try:
        data = resp.json()
        rows = data.get("data", []) if data.get("ok") else []
    except Exception:
        log("[ovd] 응답 파싱 실패 — 생략")
        return
    eligible = [r for r in rows
                if str(r.get("status", "")) not in {"완료"}
                and str(r.get("category") or "").strip() not in _OVD_CAT_EXCLUDE]
    sent_any = False
    for room in (_OVD_ROOM_LESSON, _OVD_ROOM_OPS):
        room_rows = [r for r in eligible if _ovd_room_for(str(r.get("dept") or "")) == room]
        block = _build_ovd_block(room_rows)
        if not block:
            log(f"[ovd] {room} — 3일+ 없음, 생략")
            continue
        cmd = [sys.executable, str(SENDER), "--message", block, "--only-room", room]
        log(f"[ovd] 발송 → {room}")
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        out = (proc.stdout or "").strip()
        tail = out.splitlines()[-1] if out else "출력 없음"
        log(f"[ovd] rc={proc.returncode} · {tail}")
        if proc.returncode == 0 and "DONE" in out:
            sent_any = True
    if sent_any:
        _ovd_mark_sent()


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

    rc = _send_ops_room(args)

    # ★중간관리자 — ★운영부 결과와 무관하게 시도한다(방마다 독립 · 2026-08-15 수리,
    # send_mgr_brief docstring 참조). dry-run 은 방에 손대지 않으므로 원래대로 생략.
    if not args.dry_run:
        try:
            send_mgr_brief()
        except Exception as exc:
            log(f"[mgr] 예외 — 다음 회차 재시도: {type(exc).__name__}: {exc}")
        try:
            send_overdue_reception_alerts()
        except Exception as exc:
            log(f"[ovd] 예외 — 다음 회차 재시도: {type(exc).__name__}: {exc}")
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
    done_section, done_current = build_done_section(_fetch_todo_rows(), done_prev)
    if done_bootstrap:
        done_section = ""  # 최초실행 — 과거 완료건 일괄 스팸 방지, 스냅샷만 찍고 이번엔 침묵
    if done_section:
        message = f"{message}\n\n{done_section}"

    cmd = [sys.executable, str(SENDER), "--message", message, "--only-room", TARGET_ROOM]
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
            # ★중간관리자 발송은 여기(성공 분기 안)에 있다가 main() 끝의 send_mgr_brief()
            # 호출로 나갔다(2026-08-15 — ★운영부 실패·기발송이 mgr 재시도를 삼키던 것 수리).
        print(f"DONE: 다이제스트 발송 완료 — {TARGET_ROOM}")
        return 0
    print(f"FAILED: 발송 실패(rc={proc.returncode}) — {tail}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
