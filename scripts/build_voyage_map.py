#!/usr/bin/env python3
"""항해 지도 빌더 — 배(ship)를 북극성 모듈로 그룹핑해 status/voyage_map.json 생성.

설계 정본:
  - 계획서 : .omc/plans/2026-07-04-voyage-map-module-grouping.md
  - 스펙   : .omc/specs/deep-interview-voyage-map-module-grouping.md
  - 렌더   : 3. 웰페리온 가이드/항해지도.html (발행루트 절대경로로 voyage_map.json 직독)

핵심 원칙:
  - 배→모듈 분류는 **오직** voyage_module_map(vmm) 공유 매퍼로만. 자체 분류 로직 금지.
  - 진척은 '정직 하이브리드': matrix 축에 module 태그가 있고 measured=True 인 축만
    실측(percent/signal)으로 채우고, 나머지는 {"type":"status"}(측정개통필요) 그대로.
  - 태그 없는 축은 실측값이 있어도 손대지 않는다(의도된 동작 — Step1에서 coo·cto만 태그).
"""
from __future__ import annotations

import io
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 경로 상수 ──
BASE_DIR = Path(r"C:\Users\jjky0\welperion-automation")
MATRIX_FILE = BASE_DIR / "3. 웰페리온 가이드" / "coo" / "bootsetup_matrix.json"
QUEUE_FILE = BASE_DIR / "status" / "_queue.json"
KPI_FILE = BASE_DIR / "status" / "kpi_values.json"
OUT_FILE = BASE_DIR / "status" / "voyage_map.json"

# ── 대상 역할 (gm 제외 전체 7 C-Level) ──
TARGET_ROLES = ["ceo", "cmo", "coo", "cto", "cpo", "cfo", "chro"]

# ── 역할 닉네임 ──
ROLE_NICK = {
    "ceo": "웰리", "cfo": "시뽀", "chro": "시로", "cmo": "시모",
    "coo": "시우", "cpo": "시포", "cto": "시토",
}

ACTIVE_STATUSES = ("PENDING", "IN_PROGRESS")

# ── 공유 모듈 매퍼 (배→모듈 단일 소스 — 재구축 금지) ──
try:
    import voyage_module_map as vmm
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import voyage_module_map as vmm


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _role_nsmap(matrix: dict, role_id: str) -> dict:
    role = next((r for r in matrix.get("roles", []) if r.get("id") == role_id), None)
    if not role:
        return {}
    return role.get("nsmap", {}) or {}


def _role_northstar(matrix: dict, role_id: str) -> str:
    role = next((r for r in matrix.get("roles", []) if r.get("id") == role_id), None)
    if not role:
        return ""
    dims = role.get("dims", []) or []
    return dims[0] if dims else ""


def _new_bucket(mod: dict) -> dict:
    return {
        "module": mod.get("id", ""),
        "label": mod.get("label", ""),
        "owner": "",  # 채움: 아래 role 루프에서 닉네임
        "page_url": mod.get("page_url", ""),
        "measured": False,
        "progress": {"type": "status"},
        "ships": [],
        "status_counts": {"진행": 0, "대기": 0, "이번주입항": 0},
    }


def _ship_entry(ship: dict) -> dict:
    return {
        "ship_no": ship.get("ship_no"),
        "title": ship.get("title", ""),
        "note": (ship.get("note", "") or "")[:80],
        "status": ship.get("status", ""),
        "priority": ship.get("priority", ""),
    }


def _within_7days(processed_at, today: date) -> bool:
    if not processed_at:
        return False
    try:
        d = datetime.strptime(str(processed_at)[:10], "%Y-%m-%d").date()
    except Exception:
        return False
    delta = (today - d).days
    return 0 <= delta <= 7


def _apply_progress(role_id: str, nsmap: dict, buckets_by_id: dict, kpi: dict) -> None:
    """정직 하이브리드 진척 계산. module 태그 + measured=True 축만 대상.

    - percent 모드: reach 에 value_key + target → kpi_values.roles.<role>[value_key] 실측.
    - signal 모드 : reach 에 indicators → kpi_values.global 에 실제 존재하는 지표만 신호등.
    태그 없는 role 은 tagged 가 비어 자동 skip(측정개통필요 유지).
    """
    axes = nsmap.get("axes", []) or []
    tagged = [ax for ax in axes if ax.get("module") and ax.get("measured") is True]
    if not tagged:
        return

    target_modules = []
    for ax in tagged:
        m = ax.get("module")
        if m and m not in target_modules:
            target_modules.append(m)

    reach = nsmap.get("reach", {}) or {}

    if "indicators" in reach:
        # ── signal 모드 (cto/T1) ──
        g = kpi.get("global", {}) if isinstance(kpi, dict) else {}
        g = g if isinstance(g, dict) else {}
        lights = []
        for ind in reach.get("indicators", []) or []:
            key = ind.get("key")
            if key not in g:  # 실제 존재하는 지표만 — unauth_gas 자동 제외
                continue
            val = g.get(key)
            okrule = ind.get("ok")
            if okrule == "eq0":
                okval = (val == 0)
            elif okrule == "eq:ok":
                okval = (val == "ok")
            else:
                okval = False
            lights.append({
                "key": key, "label": ind.get("label", ""),
                "value": val, "ok": okval,
            })
        if lights:
            prog = {
                "type": "signal",
                "lights": lights,
                "axis_name": "자동화 신호등",
                "axis_note": "unauth_gas는 kpi_values.global 미배선 — 개통된 지표만 표시",
            }
            for mid in target_modules:
                b = buckets_by_id.get(mid)
                if b:
                    b["progress"] = prog
                    b["measured"] = True

    elif reach.get("value_key") and ("target" in reach):
        # ── percent 모드 (coo/O1) ──
        roles_kpi = kpi.get("roles", {}) if isinstance(kpi, dict) else {}
        roles_kpi = roles_kpi if isinstance(roles_kpi, dict) else {}
        rkpi = roles_kpi.get(role_id, {}) if isinstance(roles_kpi.get(role_id), dict) else {}
        vk = reach["value_key"]
        val = rkpi.get(vk)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            axis = next((ax for ax in tagged if ax.get("module") in target_modules), tagged[0])
            prog = {
                "type": "percent",
                "value": val,
                "target": reach["target"],
                "axis_name": axis.get("name", ""),
                "axis_note": axis.get("note", ""),
            }
            for mid in target_modules:
                b = buckets_by_id.get(mid)
                if b:
                    b["progress"] = prog
                    b["measured"] = True


def main() -> int:
    today = date.today()

    matrix = _load_json(MATRIX_FILE, {"roles": []})
    queue = _load_json(QUEUE_FILE, [])
    kpi = _load_json(KPI_FILE, {})
    if not isinstance(queue, list):
        queue = []
    if not isinstance(kpi, dict):
        kpi = {}

    # 활성 배(PENDING·IN_PROGRESS) 를 role 별로 분류
    active_by_role: dict[str, list] = {r: [] for r in TARGET_ROLES}
    done_by_role: dict[str, list] = {r: [] for r in TARGET_ROLES}
    for ship in queue:
        if not isinstance(ship, dict):
            continue
        role = str(ship.get("clevel", "") or "").lower()
        if role not in active_by_role:
            continue
        st = str(ship.get("status", "") or "").upper()
        if st in ACTIVE_STATUSES:
            active_by_role[role].append(ship)
        elif st == "DONE" and _within_7days(ship.get("processed_at"), today):
            done_by_role[role].append(ship)

    roles_out = []
    etc_bucket = []

    for role in TARGET_ROLES:
        nick = ROLE_NICK.get(role, role)
        mods = vmm.load_modules(role)

        # 모든 모듈에 먼저 빈 버킷 생성 (배 없어도 그룹핑 노출 — AC10)
        buckets_by_id: dict[str, dict] = {}
        ordered_ids: list[str] = []
        for mod in mods:
            b = _new_bucket(mod)
            b["owner"] = nick
            mid = mod.get("id", "")
            if mid not in buckets_by_id:
                buckets_by_id[mid] = b
                ordered_ids.append(mid)

        # 활성 배 배정
        for ship in active_by_role[role]:
            m = vmm.module_for_ship(ship, role_id=role)
            mid = m.get("id", "기타")
            if mid == "기타":
                etc_bucket.append({
                    "role": role,
                    "owner": nick,
                    "ship_no": ship.get("ship_no"),
                    "title": ship.get("title", ""),
                    "note": (ship.get("note", "") or "")[:80],
                    "status": ship.get("status", ""),
                    "priority": ship.get("priority", ""),
                })
                continue
            b = buckets_by_id.get(mid)
            if b is None:  # 방어적: owns 밖 module id
                b = _new_bucket(m)
                b["owner"] = nick
                buckets_by_id[mid] = b
                ordered_ids.append(mid)
            b["ships"].append(_ship_entry(ship))
            st = str(ship.get("status", "") or "").upper()
            if st == "IN_PROGRESS":
                b["status_counts"]["진행"] += 1
            elif st == "PENDING":
                b["status_counts"]["대기"] += 1

        # 이번주입항(최근 7일 DONE) — 카운트만
        for ship in done_by_role[role]:
            m = vmm.module_for_ship(ship, role_id=role)
            mid = m.get("id", "기타")
            if mid == "기타":
                continue  # 기타 완료건은 버림(etc_bucket=활성만)
            b = buckets_by_id.get(mid)
            if b is None:
                b = _new_bucket(m)
                b["owner"] = nick
                buckets_by_id[mid] = b
                ordered_ids.append(mid)
            b["status_counts"]["이번주입항"] += 1

        # 진척 계산 (정직 하이브리드)
        nsmap = _role_nsmap(matrix, role)
        _apply_progress(role, nsmap, buckets_by_id, kpi)

        roles_out.append({
            "id": role,
            "nick": nick,
            "northstar": _role_northstar(matrix, role),
            "modules": [buckets_by_id[mid] for mid in ordered_ids],
        })

    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "roles": roles_out,
        "etc_bucket": etc_bucket,
    }

    OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 콘솔 요약 ──
    total_module = sum(len(r["modules"]) for r in roles_out)
    total_ships = sum(len(b["ships"]) for r in roles_out for b in r["modules"])
    print("[build_voyage_map] 항해 지도 생성 완료")
    print(f"  역할 수     : {len(roles_out)}")
    print(f"  모듈 수     : {total_module}")
    print(f"  모듈배정 배 : {total_ships}")
    print(f"  기타 배     : {len(etc_bucket)}")
    print(f"  생성 파일   : {OUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
