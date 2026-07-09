# -*- coding: utf-8 -*-
"""COO 자율화 두뇌 모듈 레지스트리 로더·검증 (단일 SSOT = status/coo_modules.json)."""
import json
from pathlib import Path

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "status" / "coo_modules.json"

REQUIRED_KEYS = ["id", "name", "hub", "erp_paths", "data_source",
                 "headline_feature", "status_metric", "telegram",
                 "autonomy", "honesty_tags", "enabled"]
TELEGRAM_KEYS = ["bot", "daily_join", "anomaly_immediate", "weekly", "monthly"]


def load_registry(path=REGISTRY_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_registry(reg: dict) -> list:
    errors = []
    mods = reg.get("modules")
    if not isinstance(mods, list):
        return ["modules 키가 리스트가 아님"]
    seen = set()
    for i, m in enumerate(mods):
        for k in REQUIRED_KEYS:
            if k not in m:
                errors.append(f"[{i}] 필수키 누락: {k}")
        mid = m.get("id")
        if mid in seen:
            errors.append(f"[{i}] 중복 id: {mid}")
        seen.add(mid)
        tg = m.get("telegram", {})
        for k in TELEGRAM_KEYS:
            if k not in tg:
                errors.append(f"[{mid}] telegram.{k} 누락")
    return errors


def get_module(reg: dict, mid: str):
    for m in reg.get("modules", []):
        if m.get("id") == mid:
            return m
    return None


def iter_enabled(reg: dict) -> list:
    return [m for m in reg.get("modules", []) if m.get("enabled") is True]


import urllib.request


def _http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Cache-Control": "no-store"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def _pick_today(resp: dict) -> dict:
    """weekly 응답(data 배열) → 마지막(오늘) 행. today_live 응답 → 그대로."""
    if isinstance(resp.get("data"), list) and resp["data"]:
        return resp["data"][-1]
    return resp


def fetch_check_status(module: dict, fetch_fn=_http_get_json) -> dict:
    ds = module["data_source"]
    endpoint = ds["endpoint"]
    depts, reasons = {}, []
    for dept, query in ds.get("queries", {}).items():
        row = _pick_today(fetch_fn(f"{endpoint}?{query}&_pv=0"))
        total = int(row.get("total") or 0)
        done = int(row.get("done") or 0)
        pct = row.get("pct")
        pct = int(pct) if pct is not None else (round(done / total * 100) if total else None)
        depts[dept] = {"pct": pct, "done": done, "total": total}
        if pct is None or pct > 100:
            reasons.append(f"{dept} 완료율 이상({pct}% — 100% 초과/미산출)")
        for iss in (row.get("allIssues") or []):
            reasons.append(f"{dept}: {iss}")
    return {"depts": depts, "anomaly": bool(reasons), "reasons": reasons, "tag": "measured"}
