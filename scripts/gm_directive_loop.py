#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gm_directive_loop.py — 아침 Close the Loop: 전일 GM 지시 이행 점검 (배 2765 · GM 09-18)

정본 = status/briefs/CEO-2026-09-18-GM지시-자동화-파이프라인.md §5·§6.
정식 지시 원장(status/gm_directives.json)은 다른 레인(gm_directive_pipeline.py)이
소유·채운다 — 이 스크립트는 그 파일을 읽기만 한다(쓰지 않는다). 원장이 아직
비어 있으면(v1 시점) 큐(status/_queue.json)의 'GM 지시 {D}' 표시 배와
GM업무 카드(status/monthly_ops_plan.json, [회장님/대표님/GM 지시] 태그)를
대신 훑어 같은 4분류 표를 만든다.

ponytail: worklog 원문(warn/진행 줄)까지 파싱하지 않고 큐의 status 칸(이미
운영 중인 갱신 경로를 거친 값)만 근거로 쓴다 — 더 정밀한 근거가 필요해지면
worklog_gaps.py 쪽 로직을 가져와 바꾼다. 카드/큐에서 뽑은 항목의 이월
횟수는 이 스크립트 소유 파일(status/gm_directive_carry.json)에만 적는다.

사용:
  gm_directive_loop.py --morning [--date 2026-09-18] [--out status/gm_directive_morning.md]
  gm_directive_loop.py --selfcheck
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from clevel_colors import nickname as _nickname  # noqa: E402

REPO = _SCRIPTS_DIR.parent
LEDGER_PATH = REPO / "status" / "gm_directives.json"
QUEUE_PATH = REPO / "status" / "_queue.json"
PLAN_PATH = REPO / "status" / "monthly_ops_plan.json"
CARRY_PATH = REPO / "status" / "gm_directive_carry.json"
OUT_PATH = REPO / "status" / "gm_directive_morning.md"

TAGS = ("[회장님 지시]", "[대표님 지시]", "[GM 지시]")
_EXTRA_NICK = {"CBO": "시보"}  # clevel_colors.py 정본에 CBO 가 없어 여기서만 보충
MAX_LINES = 40


def role_label(code: str) -> str:
    code = (code or "").strip().upper()
    return _EXTRA_NICK.get(code) or _nickname(code)


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json_atomic(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


_DATE_RE = re.compile(r"20\d\d-\d\d-\d\d")


def _last_date_in(text: str):
    """텍스트 속 YYYY-MM-DD 중 실제 달력 날짜만 골라 가장 늦은 값을 준다.
    ponytail: 마스킹(11:5x 등)이나 오탈자로 만들어진 가짜 날짜(예: 09-40)는
    date.fromisoformat 검증으로 버린다 — 정규식만으로는 못 거른다."""
    valid = []
    for s in _DATE_RE.findall(text or ""):
        try:
            date.fromisoformat(s)
            valid.append(s)
        except ValueError:
            continue
    return max(valid) if valid else None


def _evidence_tail(note: str, limit: int = 46) -> str:
    """note 의 마지막 대괄호 태그 이후 구간 — 사유/증거 칸 한 줄."""
    note = (note or "").strip()
    if not note:
        return "근거 없음"
    segs = re.split(r"(?=\[)", note)
    tail = (segs[-1] if segs else note).strip().replace("\n", " ")
    return (tail[:limit] + "…") if len(tail) > limit else tail


def classify_queue_status(status: str, note: str, target_date: str):
    """큐 status 칸 → (아이콘, 사유/증거)."""
    last = _last_date_in(note)
    stale = bool(last) and (date.fromisoformat(target_date) - date.fromisoformat(last)).days >= 2
    if status == "DONE":
        return "✅완료", _evidence_tail(note)
    if status == "ON_HOLD":
        return "⚠️중단·정체", _evidence_tail(note)
    if status == "IN_PROGRESS":
        return ("⚠️중단·정체" if stale else "🔄진행중"), _evidence_tail(note)
    if status == "PENDING":
        touched = len(re.findall(r"\[[^\]]*20\d\d-\d\d-\d\d", note or "")) > 1
        icon = ("⚠️중단·정체" if stale else "🔄진행중") if touched else "❌미착수"
        return icon, _evidence_tail(note)
    return "❌미착수", _evidence_tail(note)


def classify_card_status(status: str, note: str):
    if status == "완료":
        return "✅완료", _evidence_tail(note)
    if status == "이월":
        return "⚠️중단·정체", _evidence_tail(note)
    if status == "진행":
        return "🔄진행중", _evidence_tail(note)
    return "❌미착수", _evidence_tail(note)  # 계획·이관 등


def collect_from_queue(target_date: str) -> list[dict]:
    rows = _load_json(QUEUE_PATH, [])
    tag = f"GM 지시 {target_date}"
    items = []
    for r in rows:
        note = r.get("note", "") or ""
        title = r.get("title", "") or ""
        task_id = r.get("task_id", "") or ""
        is_pipeline = f"-{target_date}-" in task_id and "GM-지시-파이프라인" in task_id
        if tag not in note and not is_pipeline:
            continue
        icon, evidence = classify_queue_status(r.get("status", ""), note, target_date)
        items.append({
            "role": role_label(r.get("clevel", "")),
            "key": f"ship:{task_id}",
            "title": title,
            "icon": icon,
            "evidence": evidence,
        })
    return items


def collect_from_cards() -> list[dict]:
    plan = _load_json(PLAN_PATH, {})
    items = []
    for _ym, mv in (plan.get("months") or {}).items():
        for obj in (mv.get("objectives") or []):
            title = obj.get("title", "") or ""
            if not any(title.startswith(t) for t in TAGS):
                continue
            icon, evidence = classify_card_status(obj.get("status", ""), obj.get("progress_note", ""))
            items.append({
                "role": role_label("CEO"),  # GM업무 카드는 웰리가 관측(담당=사람 owner 는 제목에 있음)
                "key": f"card:{obj.get('id')}",
                "title": title,
                "icon": icon,
                "evidence": evidence,
            })
    return items


_LEDGER_STATUS_MAP = {
    "DONE": "✅완료", "완료": "✅완료", "CLOSED": "✅완료",
    "IN_PROGRESS": "🔄진행중", "진행": "🔄진행중",
    "ON_HOLD": "⚠️중단·정체", "STALLED": "⚠️중단·정체", "중단": "⚠️중단·정체", "정체": "⚠️중단·정체",
}


def collect_from_ledger() -> list[dict]:
    """정식 원장 — 읽기만 한다. carry_count 도 원장 값을 그대로 쓰고 여기서 고치지 않는다."""
    rows = _load_json(LEDGER_PATH, [])
    if isinstance(rows, dict):  # gm_directive_pipeline.py 쪽 스키마 = {"items": [...]}
        rows = rows.get("items", [])
    items = []
    for r in rows:
        icon = _LEDGER_STATUS_MAP.get(str(r.get("status", "")).upper(), "❌미착수")
        items.append({
            "role": role_label(r.get("role", "")),
            "key": f"ledger:{r.get('id')}",
            "title": r.get("title", ""),
            "icon": icon,
            "evidence": _evidence_tail(r.get("dod", "") or r.get("note", "")),
            "carry_count": int(r.get("carry_count", 0) or 0),
        })
    return items


def bump_carry(items: list[dict]) -> list[dict]:
    """큐·카드에서 뽑은(원장 없는) 건만 — 하루 1회 이월 카운트 +1, 완료 건은 지운다."""
    carry = _load_json(CARRY_PATH, {})
    today = date.today().isoformat()
    dirty = False
    for it in items:
        key = it["key"]
        rec = carry.get(key, {"count": 0, "last": ""})
        if it["icon"] == "✅완료":
            if key in carry:
                carry.pop(key, None)
                dirty = True
            it["carry_count"] = 0
            continue
        if rec["last"] != today:
            rec["count"] += 1
            rec["last"] = today
            dirty = True
        carry[key] = rec
        it["carry_count"] = rec["count"]
    if dirty:
        _write_json_atomic(CARRY_PATH, carry)
    return items


def build_table(items: list[dict], target_date: str) -> str:
    lines = [
        f"# 🔁 전일 지시 이행 점검 ({target_date})",
        "",
        "| 담당 | 건 | 상태 | 사유/증거 | 이월 |",
        "|---|---|---|---|---|",
    ]
    by_role: dict[str, list] = {}
    for it in items:
        by_role.setdefault(it["role"], []).append(it)
    flagged = []
    for role in sorted(by_role):
        for it in by_role[role]:
            carry_n = it.get("carry_count", 0)
            flag = " 🚩" if carry_n >= 3 else ""
            if flag:
                flagged.append(it)
            title = it["title"][:40]
            lines.append(f"| {role} | {title} | {it['icon']}{flag} | {it['evidence']} | {carry_n} |")
    if not by_role:
        lines.append("| - | 대상 없음 | - | - | - |")
    if flagged:
        lines.append("")
        lines.append("🚩 GM 결정 필요(3회 이상 이월): 계속 / 중단 / 재설계")
        for it in flagged:
            lines.append(f"- {it['role']} {it['title'][:40]} (이월 {it.get('carry_count', 0)}회)")
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES - 1] + ["…(생략 — 나머지는 status/gm_directive_morning.md 참조)"]
    return "\n".join(lines) + "\n"


def run_morning(target_date: str, out_path: Path) -> str:
    items = collect_from_ledger()
    if not items:  # 원장이 아직 비어 있으면(v1) 큐 + 카드로 대신 훑는다
        items = bump_carry(collect_from_queue(target_date) + collect_from_cards())
    md = build_table(items, target_date)
    try:  # 사람 관리자 지시 추적(배 2766·§7) — 실패해도 AI 지시 점검 보고는 그대로 나간다
        from manager_directive_track import morning_block
        md = md + "\n" + morning_block(target_date)
    except Exception:
        pass
    out_path.write_text(md, encoding="utf-8")
    return md


def selfcheck() -> None:
    fake_ledger = [
        {"id": "d1", "role": "cto", "title": "완료 건", "status": "완료", "dod": "[2026-09-17] 됨", "carry_count": 0},
        {"id": "d2", "role": "cmo", "title": "진행 건", "status": "진행", "dod": "[2026-09-18] 진행중", "carry_count": 1},
        {"id": "d3", "role": "coo", "title": "정체 건", "status": "중단", "dod": "[2026-09-15] 막힘 — 자재 대기", "carry_count": 2},
        {"id": "d4", "role": "cpo", "title": "미착수 건", "status": "미착수", "dod": "", "carry_count": 0},
        {"id": "d5", "role": "cbo", "title": "3회 이월 건", "status": "미착수", "dod": "", "carry_count": 3},
    ]
    tmp_ledger = REPO / "status" / "_gm_directives_selfcheck_tmp.json"
    _write_json_atomic(tmp_ledger, fake_ledger)
    global LEDGER_PATH
    real, LEDGER_PATH = LEDGER_PATH, tmp_ledger
    try:
        items = collect_from_ledger()
        md = build_table(items, date.today().isoformat())
    finally:
        LEDGER_PATH = real
        tmp_ledger.unlink(missing_ok=True)
    for icon in ("✅완료", "🔄진행중", "⚠️중단·정체", "❌미착수"):
        assert icon in md, f"selfcheck 실패: {icon} 없음\n{md}"
    assert "🚩" in md, f"selfcheck 실패: 🚩 없음\n{md}"
    print("selfcheck OK")
    print(md)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--morning", action="store_true")
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--date", default=(date.today() - timedelta(days=1)).isoformat())
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    if args.selfcheck:
        selfcheck()
        return 0
    if args.morning:
        md = run_morning(args.date, Path(args.out))
        print(md)
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
