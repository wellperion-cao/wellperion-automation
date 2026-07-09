# -*- coding: utf-8 -*-
"""COO 부팅 두뇌 — 레지스트리 로드 → 모듈 상태 → 가역성 라우터로 자율/제안 분기.
자율 write는 apply_gate(기본 OFF·env COO_BOOT_APPLY)일 때만. 기본 delta 0."""
import os
import coo_registry as R

sys_path = os.path.join(os.path.dirname(__file__), "aide_detectors")
import sys
sys.path.insert(0, sys_path)
import reversibility  # route(gap)->'auto'|'propose'


def build_module_actions(reg=None, status_map=None) -> list:
    reg = reg or R.load_registry()
    status_map = status_map or {}
    actions = []
    for m in R.iter_enabled(reg):
        st = status_map.get(m["id"], {})
        rev = m["autonomy"]["reversible"]
        gated = m["autonomy"]["gated"]
        for a in rev:
            if a == "flag" and not st.get("anomaly"):
                continue  # 이상 없으면 플래그 액션 없음
            actions.append({"module": m["id"], "action": a, "kind": "reversible",
                            "revert_ok": True, "external": False, "data_loss": False})
        for a in gated:
            actions.append({"module": m["id"], "action": a, "kind": "gated",
                            "revert_ok": False, "external": True, "data_loss": False})
    return actions


def route_actions(actions: list) -> dict:
    lanes = {"auto": [], "propose": []}
    for a in actions:
        lane = reversibility.route(a)  # 3부울 규칙 정본 재사용
        lanes["auto" if lane == "auto" else "propose"].append(a)
    return lanes


def _apply_gate_enabled(apply_gate) -> bool:
    if apply_gate is not None:
        return bool(apply_gate)
    return os.getenv("COO_BOOT_APPLY", "") == "1"


def run_boot_brain(reg=None, status_map=None, apply_gate=None) -> dict:
    actions = build_module_actions(reg=reg, status_map=status_map)
    lanes = route_actions(actions)
    applied = 0
    queue_delta = 0
    if _apply_gate_enabled(apply_gate):
        # 가역 자율 조치(집계·보고·플래그·항로기록)는 여기서 수행.
        # 큐 write는 read-before-write 재로드 후 append(gm_aide_scan 패턴). 기본 게이트 OFF라 미도달.
        applied = len(lanes["auto"])
        # queue_delta 는 실제 항로 append 시 증가(현 파일럿은 표시/보고 위주 → 0 유지 가능).
    return {"auto": lanes["auto"], "propose": lanes["propose"],
            "applied": applied, "queue_delta": queue_delta}
