# -*- coding: utf-8 -*-
"""자율 틈 감지기 (배237(b)) — 대기/지연 감시 감지기 (US-001).

라이브 write 없음(순수 감지·판정만). gm_aide_scan.run() 이 호출해
reversibility.split_lanes 로 반반 라우팅: 재개가능→auto(게이트 AIDE_RESUMABLE_APPLY 뒤),
정체→surface-only(자율 write 0·보드 정보 표시만), 그 외→propose.

정직 한계(스펙 AC2): note 날짜브래킷 = note 편집일이지 담당 C-Level 실작업일이
아님. 웰리 하이진·GM 상태정합 편집도 브래킷을 남겨 정체를 놓칠 수 있음(거짓음성).
blast=태그 미부착(무해). 종착=정식 updated_at 배선.
"""
from __future__ import annotations

import re
from datetime import date, datetime

# note 내 날짜 브래킷: [YYYY-MM-DD ...] — 앞 10자리만 취해 파싱
_DATE_BRACKET_RE = re.compile(r"\[(\d{4}-\d{2}-\d{2})[^\]]*\]")
# 구조적 task_id 참조: CTO-2026-07-06-VOYAGE-MAP-PAGE 형태
_TASK_ID_RE = re.compile(r"^[A-Z]+-\d{4}-\d{2}-\d{2}-\S+$")

# 무게(priority 아이콘) → 정체 임계(일). 초과(>)면 정체.
_ICON_THRESHOLDS = (("🛳️", 2), ("⛴️", 3), ("⛵", 5))
_DEFAULT_THRESHOLD = 5  # 우선순위 미상(NORMAL·무아이콘)만 최장 5일


def _parse_date(value) -> date | None:
    """'YYYY-MM-DD' 앞 10자리 파싱. 실패/비날짜/None → None(무시)."""
    if not isinstance(value, str):
        return None
    s = value.strip()[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def last_activity(ship: dict) -> date | None:
    """① note 내 최신 날짜브래킷 최대값 → ② 없으면 enqueued_at.
    비날짜 브래킷·파싱실패는 무시. 둘 다 없으면 None."""
    note = str(ship.get("note") or "")
    dates = []
    for raw in _DATE_BRACKET_RE.findall(note):
        d = _parse_date(raw)
        if d:
            dates.append(d)
    if dates:
        return max(dates)
    return _parse_date(ship.get("enqueued_at"))


def stall_threshold(ship: dict) -> int:
    """무게별 임계. 아이콘 있으면 해당 임계, 무아이콘(NORMAL 등)만 최장 5일.
    무브래킷이어도 임계는 아이콘 기준 유지(스펙 AC2 두 축 분리)."""
    priority = str(ship.get("priority") or "")
    for icon, days in _ICON_THRESHOLDS:
        if icon in priority:
            return days
    return _DEFAULT_THRESHOLD


def _is_structural_ref(dep):
    """depends_on 이 구조참조면 ('ship_no', int) 또는 ('task_id', str), 아니면 None.
    자유문장(서술형 depends_on)은 제외."""
    if isinstance(dep, bool):  # bool 은 int subclass — 방어
        return None
    if isinstance(dep, int):
        return ("ship_no", dep)
    if isinstance(dep, str):
        s = dep.strip()
        if not s:
            return None
        if s.isdigit():
            return ("ship_no", int(s))
        if _TASK_ID_RE.match(s):
            return ("task_id", s)
    return None


def _gap_flags():
    """정체·재개 조치는 가역 태그/구조필드 뿐 → revert_ok True·external False·data_loss False."""
    return {"revert_ok": True, "external": False, "data_loss": False}


def detect_stalled(queue: list, today: date | None = None) -> list:
    """status=IN_PROGRESS & (today − last_activity) > 무게별 임계 → 정체 gap."""
    if today is None:
        today = date.today()
    gaps = []
    for ship in queue:
        if ship.get("status") != "IN_PROGRESS":
            continue
        la = last_activity(ship)
        if la is None:
            continue
        idle = (today - la).days
        thr = stall_threshold(ship)
        if idle <= thr:
            continue
        gap = {
            "kind": "stalled",
            "task_id": ship.get("task_id"),
            "ship_no": ship.get("ship_no"),
            "clevel": (ship.get("clevel") or "ceo").lower(),
            "priority": ship.get("priority"),
            "last_activity": la.isoformat(),
            "days_idle": idle,
            "threshold": thr,
            "tag": "stall",
            "reason": (f"IN_PROGRESS {idle}일 무활동(임계 {thr}일 초과 · "
                       f"마지막활동 {la.isoformat()})"),
        }
        gap.update(_gap_flags())
        gaps.append(gap)
    return gaps


def detect_resumable(queue: list) -> list:
    """depends_on 이 ship_no(정수)/task_id 명시참조 & 참조배 live status=DONE 이면
    재개가능 gap. 자유문장 depends_on·자기참조·미완참조는 제외."""
    by_ship_no = {}
    by_task_id = {}
    for s in queue:
        sn = s.get("ship_no")
        if isinstance(sn, int) and not isinstance(sn, bool):
            by_ship_no[sn] = s
        tid = s.get("task_id")
        if isinstance(tid, str):
            by_task_id[tid] = s

    gaps = []
    for ship in queue:
        if ship.get("status") == "DONE" or ship.get("terminal"):
            continue
        ref = _is_structural_ref(ship.get("depends_on"))
        if not ref:
            continue
        kind, val = ref
        dep_ship = by_ship_no.get(val) if kind == "ship_no" else by_task_id.get(val)
        if dep_ship is None or dep_ship is ship:
            continue
        if dep_ship.get("status") != "DONE":
            continue
        gap = {
            "kind": "resumable",
            "task_id": ship.get("task_id"),
            "ship_no": ship.get("ship_no"),
            "clevel": (ship.get("clevel") or "ceo").lower(),
            "depends_on_ref": ship.get("depends_on"),
            "dep_status": "DONE",
            "tag": "resumable",
            "reason": (f"선행 참조배({ship.get('depends_on')}) 완료(DONE) — "
                       f"의존 해소, 재개 가능"),
        }
        gap.update(_gap_flags())
        gaps.append(gap)
    return gaps
