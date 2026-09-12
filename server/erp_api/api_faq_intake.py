# -*- coding: utf-8 -*-
"""FAQ 답받기 원장 API (배 CTO-2026-09-11-FAQ-답받기-원장-읽기-쓰기-통로-1개-업체별-파).

GET  /api/faq-intake/{tenant}   원장 전체 (읽기 전용, 로그인 필요)
PUT  /api/faq-intake/{tenant}   항목 1개 저장 {no, a, by, note, locked}
     · locked=true 항목은 관리자(x-erp-role=admin)만 수정 가능
     · locked 해제(false 설정)도 관리자 전용
     · by 는 x-erp-user 헤더로 덮어씀(화면 전달 값 불신)
     · updated 는 KST 시각으로 채움
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

TENANTS = {"1_wellperion", "2_dietcamp", "3_gocheokgolf"}   # api_chat.py 와 동일

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))

INTAKE_DIR = os.environ.get("ERP_FAQ_INTAKE_DIR", "/srv/erp/faq_intake")
SEED_DIR = os.path.join(_REPO_ROOT, "status", "faq_intake")

KST = timezone(timedelta(hours=9))
ROLE_ADMIN = "admin"

router = APIRouter(prefix="/api/faq-intake")


def _live_path(tenant: str) -> Path:
    return Path(INTAKE_DIR) / f"{tenant}.json"


def _seed_path(tenant: str) -> Path:
    return Path(SEED_DIR) / f"{tenant}.json"


def _load(tenant: str) -> dict:
    live = _live_path(tenant)
    if live.exists():
        return json.loads(live.read_text("utf-8"))
    seed = _seed_path(tenant)
    if seed.exists():
        return json.loads(seed.read_text("utf-8"))
    return {"tenant": tenant, "items": []}


def _save(tenant: str, data: dict) -> None:
    path = _live_path(tenant)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")


def _is_admin(request: Request) -> bool:
    return (request.headers.get("x-erp-role") or "").strip().lower() == ROLE_ADMIN


class IntakeItem(BaseModel):
    no: int
    a: str = ""
    by: str = ""        # 서버가 x-erp-user 로 덮어씀 — 화면이 보낸 값은 폴백 전용
    note: str = ""
    locked: Optional[bool] = None


@router.get("/{tenant}")
def get_intake(tenant: str):
    if tenant not in TENANTS:
        raise HTTPException(400, "tenant 는 %s 중 하나" % sorted(TENANTS))
    return _load(tenant)


@router.put("/{tenant}")
def put_intake(tenant: str, item: IntakeItem, request: Request):
    if tenant not in TENANTS:
        raise HTTPException(400, "tenant 는 %s 중 하나" % sorted(TENANTS))

    user = (request.headers.get("x-erp-user") or "").strip() or item.by or "unknown"
    admin = _is_admin(request)

    data = _load(tenant)
    items = data.get("items", [])

    target = next((x for x in items if x.get("no") == item.no), None)
    if target is None:
        raise HTTPException(404, "no=%d 항목 없음" % item.no)

    if target.get("locked") and not admin:
        raise HTTPException(403, "no=%d 는 잠금 상태입니다. 관리자만 수정할 수 있습니다." % item.no)

    target["a"] = item.a
    target["by"] = user
    target["note"] = item.note
    if item.locked is not None:
        if not item.locked and not admin:
            raise HTTPException(403, "잠금 해제는 관리자만 가능합니다.")
        target["locked"] = item.locked
    target["updated"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    _save(tenant, data)
    return {"ok": True, "no": item.no, "updated": target["updated"], "by": user}


# ── 자체점검 ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import tempfile

    class _Req:
        def __init__(self, headers): self.headers = headers

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ERP_FAQ_INTAKE_DIR"] = tmp

        # GET — 씨앗 폴백(실제 SEED_DIR 를 건드리지 않도록 라이브 경로에 직접 씀)
        seed_data = {"tenant": "1_wellperion", "items": [
            {"no": 1, "q": "test q", "a": "", "by": "", "note": "", "locked": False, "updated": "2026-09-11"},
            {"no": 2, "q": "locked q", "a": "기존답", "by": "admin", "note": "", "locked": True, "updated": "2026-09-11"},
        ]}
        Path(tmp).mkdir(parents=True, exist_ok=True)
        (Path(tmp) / "1_wellperion.json").write_text(json.dumps(seed_data, ensure_ascii=False), "utf-8")

        result = _load("1_wellperion")
        assert len(result["items"]) == 2, "GET: 항목 수 오류"

        # PUT 일반 — 저장
        req = _Req({"x-erp-user": "test@wellperion.com", "x-erp-role": "staff"})
        res = put_intake("1_wellperion", IntakeItem(no=1, a="새 답변", note="테스트"), req)
        assert res["ok"] and res["by"] == "test@wellperion.com", "PUT: by 오버라이드 실패"

        # 저장 확인
        saved = _load("1_wellperion")
        assert saved["items"][0]["a"] == "새 답변", "PUT: 저장 실패"

        # PUT locked — 일반 사용자 거부
        req_staff = _Req({"x-erp-user": "staff@w.com", "x-erp-role": "staff"})
        try:
            put_intake("1_wellperion", IntakeItem(no=2, a="덮어쓰기"), req_staff)
            assert False, "잠금 거부 안 됨"
        except HTTPException as e:
            assert e.status_code == 403, "잠금 거부 상태코드 오류"

        # PUT locked — 관리자 통과
        req_admin = _Req({"x-erp-user": "admin@w.com", "x-erp-role": "admin"})
        res2 = put_intake("1_wellperion", IntakeItem(no=2, a="관리자 수정"), req_admin)
        assert res2["ok"], "관리자 잠금 항목 수정 실패"

        # tenant 화이트리스트
        try:
            get_intake("4_unknown")
            assert False, "화이트리스트 거부 안 됨"
        except HTTPException as e:
            assert e.status_code == 400

    print("api_faq_intake selfcheck ok")
