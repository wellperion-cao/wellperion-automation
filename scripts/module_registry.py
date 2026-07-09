"""
module_registry.py — 모듈 단일 등록부(SSOT) 로더·검증 유틸.
정본: status/module_registry.json. 화면·알림·자율(오케스트레이션)이 이 한 곳을 읽는다.
"""

import json
import os

# ── 경로 상수 ──
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
DEFAULT_REGISTRY_PATH = os.path.join(_PROJECT_ROOT, "status", "module_registry.json")

# ── 스키마 상수 ──
MODULE_FIELDS = (
    "id",
    "owner_role",
    "owner_nick",
    "feature",
    "data_source",
    "notify_spec",
    "front_card",
    "autonomy",
    "ai_free_fallback",
    "feedback",
    "reversible",
)

AUTONOMY_LEVELS = ("auto", "semi", "mech", "propose", "manual")


def load_registry(path=None):
    """
    status/module_registry.json(UTF-8)을 읽어 dict 반환.
    path=None이면 프로젝트 기본경로(DEFAULT_REGISTRY_PATH) 사용.
    반환 dict는 최소 'modules' 키(모듈 배열)를 가진다.
    """
    target = path if path is not None else DEFAULT_REGISTRY_PATH
    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "modules" not in data:
        data["modules"] = []
    return data


def validate_module(mod):
    """
    모듈 카드 dict를 검증해 위반 사유 문자열 목록을 반환한다.
    빈 리스트 = 통과. 체크 항목:
      1) 필수 필드(MODULE_FIELDS) 누락
      2) autonomy가 AUTONOMY_LEVELS 밖
      3) reversible이 bool이 아님
    """
    violations = []

    for field in MODULE_FIELDS:
        if field not in mod:
            violations.append(f"필수 필드 누락: {field}")

    if "autonomy" in mod and mod["autonomy"] not in AUTONOMY_LEVELS:
        violations.append(
            f"autonomy 허용값 밖: {mod['autonomy']!r} (허용: {AUTONOMY_LEVELS})"
        )

    if "reversible" in mod and not isinstance(mod["reversible"], bool):
        violations.append(
            f"reversible이 bool 아님: {mod['reversible']!r} ({type(mod['reversible']).__name__})"
        )

    return violations


def get_modules_by_role(role, registry=None):
    """
    owner_role이 role과 일치하는 모듈 목록을 반환한다.
    registry=None이면 load_registry()로 기본 등록부를 읽는다.
    """
    reg = registry if registry is not None else load_registry()
    modules = reg.get("modules", [])
    return [m for m in modules if m.get("owner_role") == role]
