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

[2026-08-05 추가] 같은 실행에서 '사람이 처리할 배 전달'도 한다(send_relays) —
AI가 실행하지 않는 시우·시로·시뽀의 배를 담당자 이름과 함께 해당 방에 넘긴다.
시우→★운영부(최준용M) · 시로·시뽀→★중간관리자(나우열M). 목록이 지난번과 같으면
보내지 않는다. 자세한 이유는 아래 '사람에게 넘기는 배 전달' 주석 블록 참조.

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
from datetime import datetime
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
# 실무진이 받는 글에는 누가 보내는지가 드러나야 한다(unassigned_nudge.AI_SIGNOFF 와 같은 형식).
# 전달 주체는 웰리 — GM 원문 "각기 담당자 이름 적어서 웰리가 전달".
RELAY_SIGNOFF = "웰페리온 AI 총괄 담당 웰리 드림"
# 무게 순서(🛳️크루즈 → ⛴️여객선 → ⛵돛단배). 모르는 값은 맨 뒤.
_RELAY_WEIGHT = {"🛳️크루즈": 0, "⛴️여객선": 1, "⛵돛단배": 2}


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
    """[(방 이름, {clevel: 담당자})] — 방 배정 정본은 safe_commit.DOMAIN_MODIFY_RULES 하나."""
    from safe_commit import DOMAIN_MODIFY_RULES  # 함수 안에서 import — 실패해도 다이제스트는 산다

    routes: dict = {}
    for role_label, contact, _paths, room, _note in DOMAIN_MODIFY_RULES:
        clevel = role_label.split("(")[0].strip().lower()  # "COO(시우)" → "coo"
        routes.setdefault(room, {})[clevel] = contact
    return list(routes.items())


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


def _cap_line(text: str) -> str:
    """카톡 한 줄용 길이 상한 — 낱말 한가운데서 자르지 않는다(GM 상시 지시).

    상한 안에서 마지막 띄어쓰기까지만 남긴다. 띄어쓰기가 아예 없으면(붙여 쓴 긴 문장)
    어쩔 수 없이 길이로 자른다 — 그때는 잘린 티가 나는 게 뜻이 끊기는 것보다 낫다."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(t) <= RELAY_TITLE_CAP:
        return t
    head = t[:RELAY_TITLE_CAP]
    cut = head.rfind(" ")
    if cut >= RELAY_TITLE_CAP // 2:
        head = head[:cut]
    return head.rstrip(" ·—-(→,") + "…"


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

    ships = [x for x in queue if isinstance(x, dict)
             and x.get("clevel") in contacts
             and str(x.get("status", "")) in RELAY_OPEN_STATUSES
             and str(x.get("audience", "")) == "office"   # ★AI 내부 살림(audience="ai")은 사람 방에 보내지 않는다
             and str(x.get("staff_message", "")).strip()]  # ★전달문 없는 배는 사람 방에 싣지 않는다
    ships.sort(key=lambda x: (_RELAY_WEIGHT.get(x.get("priority"), 9),
                              str(x.get("enqueued_at", ""))))
    current = {_relay_key(s): _cap_line(str(s["staff_message"]).strip().splitlines()[0]) for s in ships}

    if _is_legacy_snapshot(prev_items):
        return "", current  # 옛 키 형식 — 비교 건너뛰고 새 키로 스냅샷만 다시 찍는다(첫 회차)

    new_ships = [s for s in ships if _relay_key(s) not in prev_items]
    # ★'완료'는 목록에서 사라진 것 전부가 아니라, 실제로 DONE/보관함행인 것만(위 _is_done).
    #   staff_message 가 지워지거나 audience 가 바뀌어 사라진 배는 아직 진행 중일 수 있다 —
    #   그런 배까지 '✅ 처리 완료'로 실무진에게 보내면 오보다.
    dropped = [k for k in prev_items if k not in current]
    if dropped:
        archive_cache = _load_archive()
        closed = [prev_items[k] for k in dropped if _is_done(k, queue, archive_cache)]
    else:
        closed = []
    if not new_ships and not closed:
        return "", current  # 지난번과 같은 목록 — 다시 보내지 않는다

    who = {contacts[s["clevel"]] for s in ships}
    solo = who.pop() if len(who) == 1 else None
    lines = [f"🧾 사람이 처리할 업무 {len(ships)}건" + (f" — {solo}" if solo else "")]
    if new_ships:
        lines.append(f"🆕 새로 생긴 업무 {len(new_ships)}건")
        for s in new_ships[:RELAY_SHOW_N]:
            tail = "" if solo else f" · {contacts[s['clevel']]}"
            lines.append(f" • {str(s['staff_message']).strip()}{tail}")
        if len(new_ships) > RELAY_SHOW_N:
            lines.append(f" • 외 {len(new_ships) - RELAY_SHOW_N}건")
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


def send_relays(dry_run: bool = False) -> None:
    """방마다 '사람이 처리할 배' 변화분 1통. 새로 생긴 것·처리 완료된 것이 없으면 안 보낸다.

    같은 목록을 매일 다시 보내면 실무진이 읽기를 멈춘다 — 배가 늘거나 줄었을 때만
    다시 뜬다. 발신 실패 시 스냅샷을 안 적으므로 다음 회차에 자동 재시도된다.
    전달 실패가 다이제스트 발송을 막지 않는다(fail-soft)."""
    try:
        routes = relay_routes()
    except Exception as exc:
        log(f"[relay] 전달 대상 규칙 로드 실패 — 전달 생략(다이제스트는 계속): {exc}")
        return

    known = _known_rooms()
    state = _relay_state()
    changed = False
    for room, contacts in routes:
        if _title_key(room) not in known:
            log(f"[relay] '{room}' 는 kakao_rooms.json 에 없는 방 — 건너뜀")
            continue
        message, current = build_relay_message(contacts, state.get(room, {}))
        if not message:
            log(f"[relay] {room} — 변화 없음, 발신 생략")
            if current != state.get(room, {}):
                state[room], changed = current, True
            continue

        cmd = [sys.executable, str(SENDER), "--message", message, "--only-room", room]
        if dry_run:
            cmd.append("--dry-run")
        log(f"[relay] {room} 전달 발송({message.count(chr(10)) + 1}줄)")
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        out = (proc.stdout or "").strip()
        if proc.returncode == 0 and "DONE" in out:
            if not dry_run:
                state[room], changed = current, True
            log(f"[relay] {room} 전달 완료")
        else:
            tail = out.splitlines()[-1] if out else "출력 없음"
            log(f"[relay] {room} 전달 실패(rc={proc.returncode}) — {tail} · 다음 회차 재시도")
    if changed:
        _save_relay_state(state)


def preview_relays() -> int:
    """방에 손대지 않고 본문만 렌더해 보여준다(실방 검증용 — 발신·상태기록 없음)."""
    state = _relay_state()
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


def main() -> int:
    if sys.platform != "win32":
        print("FAILED: Windows 전용")
        return 1
    ap = argparse.ArgumentParser(description="★운영부 아침 다이제스트 발송")
    ap.add_argument("--force", action="store_true", help="킬스위치·오늘조건 무시(수동 검증)")
    ap.add_argument("--dry-run", action="store_true", help="미발송")
    ap.add_argument("--relay-preview", action="store_true",
                    help="사람 처리 배 전달 본문만 렌더(방에 손 안 댐 · 발신·지문기록 없음)")
    args = ap.parse_args()

    if args.relay_preview:
        return preview_relays()

    if not args.force and not kill_switch_enabled():
        log(f"킬스위치 OFF({KILL_SWITCH}) — 발송 생략")
        print("SKIPPED: 킬스위치 비활성")
        return 0

    # 사람이 처리할 배 전달은 다이제스트보다 먼저·독립으로 돈다 — 어제 카톡 대화가
    # 없어(휴관 등) 다이제스트가 안 만들어진 날에도 이 전달은 나가야 한다.
    send_relays(dry_run=args.dry_run)

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
        print(f"DONE: 다이제스트 발송 완료 — {TARGET_ROOM}")
        return 0
    print(f"FAILED: 발송 실패(rc={proc.returncode}) — {tail}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
