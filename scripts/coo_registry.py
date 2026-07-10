# -*- coding: utf-8 -*-
"""COO 자율화 두뇌 모듈 레지스트리 로더·검증 — 소비자.
단일 SSOT는 status/module_registry.json(웰리 확정 13필드 계약, 전 C-Level 공유).
이 모듈은 자기만의 등록부를 두지 않고 owner_role=='coo' 모듈만 골라 읽는다."""
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "status" / "module_registry.json"

REQUIRED_KEYS = ["id", "owner_role", "owner_nick", "feature", "data_source",
                  "notify_spec", "front_card", "autonomy", "ai_free_fallback",
                  "feedback", "reversible", "enabled", "honesty_default"]
NOTIFY_KEYS = ["daily", "weekly", "monthly", "channel", "bot_id"]

# 점검 GAS 파이프 접속 정보 — data_source.ref는 포인터일 뿐, fetch 설정은 소비자가 보유(계약 §3).
CHECK_API = "https://script.google.com/macros/s/AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec"
CHECK_QUERIES = {"facility": "action=weekly&dept=facility", "support": "action=today_live&dept=support"}

# 업무·결재 SSOT 접속 정보 — 서버 사전집계 없음, 클라이언트 산식 복제(계약 §3).
TODO_API = "https://script.google.com/macros/s/AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"

# 표시용 짧은 이름(정본 스키마엔 name 필드 없음 — feature로 갈음하되 카드용 축약은 소비자 상수).
# 라벨 = 소스 구분 명시. "전사 업무·결재"=전사 업무·결재 SSOT 시트(todo_list, 모든 부서 실무 포함)
# — 09시 보고의 "C-Level 업무"(status/_queue.json 큐)와 다른 모집단이라 GM 화면서 혼동 방지(2026-07-10 시우).
DISPLAY_NAME = {"coo-check-status": "점검 현황", "coo-work-approval": "전사 업무·결재"}


def load_registry(path=REGISTRY_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def iter_coo(reg: dict) -> list:
    return [m for m in reg.get("modules", []) if m.get("owner_role") == "coo"]


def validate_registry(reg: dict) -> list:
    """관대 검증 — coo 소유 모듈만 13필드 계약 검사(타 도메인 모듈은 손대지 않음)."""
    errors = []
    mods = reg.get("modules")
    if not isinstance(mods, list):
        return ["modules 키가 리스트가 아님"]
    seen = set()
    for m in iter_coo(reg):
        mid = m.get("id")
        for k in REQUIRED_KEYS:
            if k not in m:
                errors.append(f"[{mid}] 필수키 누락: {k}")
        if mid in seen:
            errors.append(f"중복 id: {mid}")
        seen.add(mid)
        ns = m.get("notify_spec", {})
        for k in NOTIFY_KEYS:
            if k not in ns:
                errors.append(f"[{mid}] notify_spec.{k} 누락")
    return errors


def get_module(reg: dict, mid: str):
    for m in reg.get("modules", []):
        if m.get("id") == mid:
            return m
    return None


def iter_enabled(reg: dict) -> list:
    return [m for m in iter_coo(reg) if m.get("enabled") is True]


def _http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Cache-Control": "no-store"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def _kst_today() -> str:
    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")


def _pick_today(resp: dict) -> dict:
    """weekly 응답(data 배열) → KST 오늘 날짜(row['date']==today) 매칭, 없으면 마지막 폴백. today_live 응답 → 그대로."""
    if isinstance(resp.get("data"), list) and resp["data"]:
        today = _kst_today()
        for row in resp["data"]:
            if row.get("date") == today:
                return row
        return resp["data"][-1]
    return resp


_ISSUE_TEXT_KEYS = ["text", "issue", "내용", "memo", "비고", "detail", "area"]


def _issue_text(iss) -> str:
    """allIssues 항목을 사람이 읽을 문자열로 정제 — 라이브 GAS가 dict로 반환하는 경우 대비."""
    if not isinstance(iss, dict):
        return str(iss)
    for k in _ISSUE_TEXT_KEYS:
        v = iss.get(k)
        if v:
            return str(v)
    parts = [str(v) for v in iss.values() if v]
    if parts:
        return " ".join(parts)
    return str(iss)


def fetch_check_status(fetch_fn=_http_get_json) -> dict:
    """공통 status 계약 반환: {display, anomaly, reasons, tag, metrics} + 기존 depts(하위호환)."""
    depts, reasons = {}, []
    for dept, query in CHECK_QUERIES.items():
        row = _pick_today(fetch_fn(f"{CHECK_API}?{query}&_pv=0"))
        total = int(row.get("total") or 0)
        done = int(row.get("done") or 0)
        pct = row.get("pct")
        pct = int(pct) if pct is not None else (round(done / total * 100) if total else None)
        depts[dept] = {"pct": pct, "done": done, "total": total}
        if pct is None or pct > 100:
            reasons.append(f"{dept} 완료율 이상({pct}% — 100% 초과/미산출)")
        for iss in (row.get("allIssues") or []):
            reasons.append(f"{dept}: {_issue_text(iss)}")
    f_pct = depts.get("facility", {}).get("pct")
    s_pct = depts.get("support", {}).get("pct")
    display = f"시설 {f_pct if f_pct is not None else '-'}% · 지원 {s_pct if s_pct is not None else '-'}%"
    metrics = {f"{dept}_pct": d["pct"] for dept, d in depts.items()}
    return {"depts": depts, "anomaly": bool(reasons), "reasons": reasons, "tag": "measured",
            "display": display, "metrics": metrics}


def fetch_workapproval_status(fetch_fn=_http_get_json) -> dict:
    """업무·결재 SSOT(TODO_API) — 서버 사전집계 없음, 클라이언트 산식 복제. 공통 status 계약 반환."""
    rows = fetch_fn(f"{TODO_API}?action=todo_list").get("data", [])
    active = [r for r in rows if r.get("상태") not in ("완료", "보류")]
    pending = [r for r in rows
               if (r.get("결재상태") or r.get("결재요청")) and r.get("결재상태") != "결재완료"
               and "반려" not in (r.get("결재상태") or "")]
    today = _kst_today()
    overdue = [r for r in active if r.get("종료일") and r["종료일"] < today]
    rejected = [r for r in rows if "반려" in (r.get("결재상태") or "")]
    display = f"활성 {len(active)}건 · 결재대기 {len(pending)}건"
    reasons = []
    if overdue:
        reasons.append(f"마감 초과 {len(overdue)}건")
    if rejected:
        reasons.append(f"반려 {len(rejected)}건")
    metrics = {"active": len(active), "pending": len(pending),
               "overdue": len(overdue), "rejected": len(rejected)}
    return {"display": display, "anomaly": bool(reasons), "reasons": reasons, "tag": "measured",
            "metrics": metrics}


# fetcher 맵 — 소비자(coo_report_line/coo_check_anomaly)가 모듈 id로 공통 status 계약을 얻는 단일 경로.
STATUS_FETCHERS = {"coo-check-status": fetch_check_status, "coo-work-approval": fetch_workapproval_status}
