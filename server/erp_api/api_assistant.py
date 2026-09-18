# -*- coding: utf-8 -*-
"""AI 비서 쓰임 내역 — 배 12816 · GM 2026-09-18 17:4x(시보 설계).

api_meeting.py(회의 요약)·api_translate.py(번역)가 성공 응답마다 log_usage() 를 불러 한 줄 남긴다.
저장 = /srv/erp/assistant/{tenant}/usage.jsonl append. 녹취록·번역 원문 text 는 저장하지 않는다
(in_chars 만) — 저장 기본값은 결과만이다(GM 09-18 「녹취 원문 저장 안 함」).

조회 = GET /api/assistant/usage?tenant=&limit=100(최대 500). 플랫폼 관리자(ERP_PLATFORM_ADMINS)는
tenant 를 골라 볼 수 있고, 그 외 계정은 쿼리 tenant 를 무시하고 로그인 계정의 perms.tenant 로
고정한다 — 파트너는 남의 센터 내역을 못 본다.

인증 = 기존 관문 재사용(api_write.py·api_guide.py 와 같은 방식) — X-Erp-User 헤더(nginx auth_request 가
클라이언트 값을 늘 덮어씀 · api.nginx.conf)로 이메일만 받고, 그 계정의 perms.tenant 는 DB users 표에서
직접 읽는다. X-Erp-Role 헤더는 아직 신뢰 대상이 아니라서(api_guide.py 머리말 참고) 관리자 판정도
이메일을 ERP_PLATFORM_ADMINS 와 대조하는 방식(app.py PLATFORM_ADMINS 와 같은 판정)을 그대로 쓴다.
tenant 값은 저장·조회 어느 경로든 [a-z0-9_-] 만 통과시켜 경로 조작을 막는다(safe_tenant).

자체점검: python api_assistant.py --selftest (네트워크·DB 없음 · tenant 검증·경로 조작 거부·원문 미저장만 검사)
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db  # noqa: E402

router = APIRouter(prefix="/api/assistant")

KST = timezone(timedelta(hours=9))
ASSISTANT_DIR = os.environ.get("ERP_ASSISTANT_DIR", "/srv/erp/assistant")
DEFAULT_TENANT = "wellperion"
TENANT_RE = re.compile(r"^[a-z0-9_-]+$")
# 응답에 실어도 되는 계약 필드만(위 머리말) — log_usage 가 이 목록 밖 키(transcript·text 등)를 받아도 버린다.
_USAGE_FIELDS = ("title", "source", "target", "out")


def _admins():
    raw = os.environ.get("ERP_PLATFORM_ADMINS", "cao@wellperion.com")
    return frozenset(e.strip().lower() for e in raw.split(",") if e.strip())


def _user_email(request: Request) -> str:
    return (request.headers.get("x-erp-user") or "").strip().lower()


def safe_tenant(raw) -> str:
    """[a-z0-9_-] 만 통과 — 대문자는 소문자로 눌러 맞추고, 빈 값·경로 조작(../ 등)은 기본 tenant 로 앉는다."""
    t = str(raw or "").strip().lower()
    return t if t and TENANT_RE.match(t) else DEFAULT_TENANT


def _own_tenant(email: str) -> str:
    """이 계정의 perms.tenant — DB 를 직접 본다(X-Erp-Role 은 아직 못 믿는다 · api_guide.py 머리말 참고).
    조회 실패·미가입·tenant 없음은 전부 기본 tenant(wellperion)로 본다."""
    if not email:
        return DEFAULT_TENANT
    conn = None
    try:
        conn = db.connect(readonly=True)
        row = conn.execute("SELECT perms FROM users WHERE tenant_id=%s AND email=%s",
                            (db.TENANT, email)).fetchone()
    except Exception:
        return DEFAULT_TENANT
    finally:
        if conn is not None:
            conn.close()
    if not row or not row["perms"]:
        return DEFAULT_TENANT
    try:
        perms = json.loads(row["perms"])
    except (ValueError, TypeError):
        return DEFAULT_TENANT
    if not isinstance(perms, dict):
        return DEFAULT_TENANT
    return safe_tenant(perms.get("tenant"))


def _usage_path(tenant) -> str:
    return os.path.join(ASSISTANT_DIR, safe_tenant(tenant), "usage.jsonl")


def log_usage(request: Request, kind: str, in_chars: int, **fields) -> None:
    """요약·번역 성공 응답 뒤 한 줄 남긴다. 실패해도 부른 쪽 응답은 그대로 성공이다 — 여기서 전부 삼킨다.
    fields 는 title·source·target·out 중 값이 있는 것만(계약 밖 키는 버린다 · 원문 text 는 절대 안 받는다)."""
    try:
        email = _user_email(request)
        tenant = _own_tenant(email)
        line = {"ts": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"), "tenant": tenant, "email": email,
                "kind": kind, "in_chars": int(in_chars)}
        for k in _USAGE_FIELDS:
            v = fields.get(k)
            if v:
                line[k] = v
        path = _usage_path(tenant)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception as e:
        print("[api_assistant] 기록 실패(응답엔 영향 없음): %s" % e, flush=True)


def _read_usage(tenant, limit: int) -> list:
    path = _usage_path(tenant)
    items = []
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    items.append(json.loads(ln))
                except ValueError:
                    continue
    except FileNotFoundError:
        return []
    items.reverse()   # 최신순
    return items[:limit]


@router.get("/usage")
def usage(request: Request, tenant: str = "", limit: int = 100):
    email = _user_email(request)
    is_admin = bool(email) and email in _admins()
    t = safe_tenant(tenant) if (is_admin and tenant) else _own_tenant(email)
    lim = max(1, min(int(limit or 100), 500))
    return JSONResponse({"items": _read_usage(t, lim)})


def _selftest():
    global ASSISTANT_DIR
    assert safe_tenant("2_dietcamp") == "2_dietcamp"
    assert safe_tenant("../../etc") == DEFAULT_TENANT, "경로 조작 문자는 기본 tenant 로 눌러 앉아야 한다"
    assert safe_tenant("") == DEFAULT_TENANT and safe_tenant(None) == DEFAULT_TENANT
    assert safe_tenant("Has Space") == DEFAULT_TENANT
    assert safe_tenant("UP-PER") == "up-per"          # 대문자는 소문자로 눌러 맞춘다(막지 않는다)

    p = _usage_path("../../etc/passwd")
    assert os.path.basename(os.path.dirname(p)) == DEFAULT_TENANT, p     # 조작 시도는 기본 폴더로 눌러앉는다
    assert p.startswith(ASSISTANT_DIR)                                   # ASSISTANT_DIR 밖으로 못 나간다

    # 원문 미저장 — log_usage 가 만드는 줄에 계약 필드 밖의 것(transcript·text)은 못 들어간다.
    class _Req:
        headers = {"x-erp-user": "tester@x"}
    import tempfile
    real_dir = ASSISTANT_DIR
    ASSISTANT_DIR = tempfile.mkdtemp()
    try:
        log_usage(_Req(), "summary", 1234, title="회의", transcript="원문이 새면 안 된다", out={"summary": ["a"]})
        items = _read_usage(DEFAULT_TENANT, 10)   # DB 없는 환경 — _own_tenant 조회 실패 시 기본 tenant 로 떨어진다
        assert len(items) == 1, items
        row = items[0]
        assert row["in_chars"] == 1234 and row.get("title") == "회의"
        assert "transcript" not in row and "text" not in row, row
        assert set(row) <= {"ts", "tenant", "email", "kind", "in_chars", "title", "source", "target", "out"}, row
    finally:
        ASSISTANT_DIR = real_dir

    print("api_assistant selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
