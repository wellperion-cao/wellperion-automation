# -*- coding: utf-8 -*-
"""
module_decisions_surface.py — 모듈 결정 큐(이상징후·설정변경) 적재·노출·반영.
─────────────────────────────────────────────────────────────────────────────
결정 채널 = CLI/모바일 원격 AskUserQuestion 카드(스펙 §결정 채널). 텔레그램은 알림만.

배237 '무한적체' 함정 방어(gm_aide_scan.py 패턴 복제 — import 아님):
  - dedup_key = "{type}|{module}" (날짜·카운트 미포함) → 동일 open 카드 있으면 append skip.
  - per-run cap = MAX_DECISIONS_PER_RUN(5) → 한 실행에 과다 등록 차단.
  - expires_at(TTL) → 경과분 자동 'expired' 처리(만료 스윕)로 적체 해소.

파일:
  - status/module_decisions.json        : pending 결정 큐(배열)
  - status/module_decision_log.jsonl    : append/expired/applied 원장(감사 추적)
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
_STATUS_DIR = os.path.join(_PROJECT_ROOT, "status")

DECISIONS_PATH = os.path.join(_STATUS_DIR, "module_decisions.json")
DECISION_LOG_PATH = os.path.join(_STATUS_DIR, "module_decision_log.jsonl")
REGISTRY_PATH = os.path.join(_STATUS_DIR, "module_registry.json")

MAX_DECISIONS_PER_RUN = 5      # gm_aide_scan.py:78 미러 — per-run 과다등록 cap
DEFAULT_TTL_DAYS = 14          # 미응답 결정 만료(무한적체 차단)


# ── 저수준 IO ────────────────────────────────────────────────────────────────
def _load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _log(path, event, record):
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"event": event, "at": datetime.now().isoformat(),
                                **record}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def dedup_key(dtype, module) -> str:
    return f"{dtype}|{module}"


# ── 만료 스윕 ────────────────────────────────────────────────────────────────
def sweep_expired(decisions, now=None, log_path=DECISION_LOG_PATH):
    """expires_at 경과한 pending 결정을 status='expired'로 정리. (남은목록, 만료수) 반환."""
    now = now or datetime.now()
    expired = 0
    for d in decisions:
        if d.get("status") != "pending":
            continue
        exp = d.get("expires_at")
        if not exp:
            continue
        try:
            if datetime.fromisoformat(exp) <= now:
                d["status"] = "expired"
                d["expired_at"] = now.isoformat()
                expired += 1
                _log(log_path, "expired", {"decision_id": d.get("decision_id"),
                                           "dedup_key": d.get("dedup_key")})
        except Exception:
            continue
    return decisions, expired


# ── 적재 (dedup + cap + TTL) ─────────────────────────────────────────────────
def append_decisions(candidates, *, path=DECISIONS_PATH, log_path=DECISION_LOG_PATH,
                     now=None, ttl_days=DEFAULT_TTL_DAYS):
    """
    candidates: [{"type","module","summary","options"[list]}] 목록.
    open dedup_key 대조 skip → per-run cap → expires_at 세팅 → 저장.
    반환: {"registered": n, "skipped_dedup": n, "overflow": n, "expired": n}
    """
    now = now or datetime.now()
    decisions = _load(path)
    decisions, expired = sweep_expired(decisions, now=now, log_path=log_path)

    open_keys = {d.get("dedup_key") for d in decisions if d.get("status") == "pending"}

    fresh = []
    skipped = 0
    batch_keys = set()
    for c in candidates:
        key = dedup_key(c.get("type"), c.get("module"))
        if key in open_keys or key in batch_keys:
            skipped += 1
            continue
        batch_keys.add(key)
        fresh.append((key, c))

    to_add = fresh[:MAX_DECISIONS_PER_RUN]
    overflow = fresh[MAX_DECISIONS_PER_RUN:]

    for key, c in to_add:
        rec = {
            "decision_id": f"dec-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}",
            "type": c.get("type"),
            "module": c.get("module"),
            "dedup_key": key,
            "summary": c.get("summary", ""),
            "options": list(c.get("options", [])),
            "raised_at": now.isoformat(),
            "expires_at": (now + timedelta(days=ttl_days)).isoformat(),
            "status": "pending",
        }
        decisions.append(rec)
        _log(log_path, "raised", {"decision_id": rec["decision_id"], "dedup_key": key})

    _save(path, decisions)
    return {
        "registered": len(to_add),
        "skipped_dedup": skipped,
        "overflow": len(overflow),
        "expired": expired,
    }


# ── 노출 (카드 surface) ──────────────────────────────────────────────────────
def list_pending(*, path=DECISIONS_PATH, log_path=DECISION_LOG_PATH, sweep=True, now=None):
    """pending 결정 목록 반환(옵션 만료 스윕 후). 반영 시 저장까지."""
    decisions = _load(path)
    if sweep:
        decisions, expired = sweep_expired(decisions, now=now, log_path=log_path)
        if expired:
            _save(path, decisions)
    return [d for d in decisions if d.get("status") == "pending"]


def pending_count(*, path=DECISIONS_PATH) -> int:
    """텔레그램 보고 말미 '결정 대기 N건'용(스윕 없이 빠른 카운트)."""
    return sum(1 for d in _load(path) if d.get("status") == "pending")


# ── 반영 (버튼 클릭) ─────────────────────────────────────────────────────────
def _patch_registry_enabled(module_id, enabled, registry_path=REGISTRY_PATH):
    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            reg = json.load(f)
        touched = False
        for m in reg.get("modules", []):
            if m.get("id") == module_id:
                m["enabled"] = enabled
                touched = True
        if touched:
            with open(registry_path, "w", encoding="utf-8") as f:
                json.dump(reg, f, ensure_ascii=False, indent=2)
        return touched
    except Exception:
        return False


def apply_decision(decision_id, option, *, path=DECISIONS_PATH,
                   log_path=DECISION_LOG_PATH, registry_path=REGISTRY_PATH):
    """
    카드 클릭 결과 반영: 옵션에 따라 registry patch 등 → 원장 기록 → 큐 제거.
    반환: {"applied": bool, "module": id, "option": str, "effect": str} 또는 {"applied": False, "reason": ...}
    """
    decisions = _load(path)
    target = None
    for d in decisions:
        if d.get("decision_id") == decision_id and d.get("status") == "pending":
            target = d
            break
    if target is None:
        return {"applied": False, "reason": "결정 없음 또는 이미 처리됨", "decision_id": decision_id}

    module_id = target.get("module")
    effect = "기록만"
    # 설정변경 반영: '끄기' 계열 → 모듈 킬스위치(enabled=false)
    if option and ("끄기" in option or option == "disable"):
        if _patch_registry_enabled(module_id, False, registry_path):
            effect = f"registry.{module_id}.enabled=false"

    _log(log_path, "applied", {
        "decision_id": decision_id, "module": module_id,
        "option": option, "effect": effect, "dedup_key": target.get("dedup_key"),
    })

    # 큐 제거(applied 는 원장에만 남김)
    remaining = [d for d in decisions if d.get("decision_id") != decision_id]
    _save(path, remaining)

    return {"applied": True, "module": module_id, "option": option, "effect": effect}


if __name__ == "__main__":
    pend = list_pending()
    print(f"pending 결정 {len(pend)}건")
    for d in pend:
        print(f"  - [{d['type']}] {d['module']}: {d['summary']}  옵션={d['options']}")
