# -*- coding: utf-8 -*-
"""월말 결산 A3 — 리더가 직접 쓰는 「특이사항 · 이번 달 계획」 칸의 저장 통로 (GM 지시 2026-09-17 19:0x · 시토).

GM 원문: 「[9월 결산 & 10월 계획] A3 각 부서별 1장씩 · 정리는 각자 해야 해 · 추가할 내용만 기록할 수 있게 칸을 만들어
주거나 회신 받아서 기록되게」. 숫자는 보고서(coo/report/매출회원현황보고.html 5~7면 · 시포 배 2523)가 자동으로 채우고,
글은 여기 한 곳에 달·부서별로 남는다 — 파일 하나(/srv/erp/status/closing_notes.json), 새 표 없음.

  GET  /api/closing/notes?month=2026-09            → {"ok":true,"month":"2026-09","notes":{"운영부":{"text","by","at"},…}}
  POST /api/closing/notes  {"month","dept","text"} → 로그인한 직원이면 저장(by = 관문이 덮어쓰는 X-Erp-User) · 같은 달·부서는 덮어씀
       · 이전 판은 history 에 남긴다(누가 언제 무엇을 썼는지 되짚기용 · 최근 20판)

/api/ 는 nginx auth_request 관문 뒤라 로그인 없는 호출은 여기까지 오지 않는다. 부서 이름은 아래 DEPTS 만 받는다.
"""
import json
import os
import re
import tempfile
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/closing")

KST = timezone(timedelta(hours=9))
STORE = os.path.join(os.environ.get("ERP_STATUS_DIR", "/srv/erp/status"), "closing_notes.json")
DEPTS = ("운영부", "시설부", "파트너팀")          # 리더 = 이경연 실장 · 이정헌 소장 · 나우열M
MONTH_RE = re.compile(r"^20[0-9]{2}-(0[1-9]|1[0-2])$")
MAX_TEXT = 4000
HISTORY_KEEP = 20


def _load():
    try:
        with open(STORE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STORE), prefix=".closing_notes.", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STORE)   # 다 쓴 뒤 교체 — 반쯤 쓰다 죽어도 옛 파일이 남는다


def _month_ok(m):
    return bool(m and MONTH_RE.match(m))


@router.get("/notes")
def get_notes(month: str = ""):
    if not _month_ok(month):
        raise HTTPException(400, "month 는 YYYY-MM")
    d = _load()
    notes = (d.get("months") or {}).get(month) or {}
    return {"ok": True, "month": month, "depts": list(DEPTS),
            "notes": {k: {"text": v.get("text", ""), "by": v.get("by", ""), "at": v.get("at", "")} for k, v in notes.items() if k in DEPTS}}


@router.post("/notes")
async def post_note(request: Request):
    who = (request.headers.get("x-erp-user") or "").strip().lower()
    if not who:
        raise HTTPException(403, "로그인한 계정만 저장할 수 있습니다")
    try:
        p = await request.json()
    except Exception:
        raise HTTPException(400, "본문이 JSON 이 아닙니다")
    month, dept, text = str(p.get("month") or ""), str(p.get("dept") or ""), p.get("text")
    if not _month_ok(month):
        raise HTTPException(400, "month 는 YYYY-MM")
    if dept not in DEPTS:
        raise HTTPException(400, "dept 는 %s 중 하나" % "·".join(DEPTS))
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        raise HTTPException(400, "text 는 %d자 이하 문자열" % MAX_TEXT)
    d = _load()
    months = d.setdefault("months", {})
    cur = months.setdefault(month, {})
    now = datetime.now(KST).isoformat(timespec="seconds")
    prev = cur.get(dept)
    if prev and prev.get("text") != text:
        hist = d.setdefault("history", [])
        hist.append({"month": month, "dept": dept, **prev})
        del hist[:-HISTORY_KEEP]
    cur[dept] = {"text": text.strip(), "by": who, "at": now}
    _save(d)
    return {"ok": True, "month": month, "dept": dept, "by": who, "at": now}


def selftest():
    """임시 폴더에 저장·덮어쓰기·이력·거부 4가지."""
    import asyncio

    class _Req:
        def __init__(self, headers, body):
            self.headers = headers; self._b = body

        async def json(self):
            return self._b

    global STORE
    with tempfile.TemporaryDirectory() as td:
        STORE = os.path.join(td, "closing_notes.json")
        r = asyncio.run(post_note(_Req({"x-erp-user": "tlacks001"}, {"month": "2026-09", "dept": "운영부", "text": "휴회 4건 · 10월 계획 = 문자 자동화"})))
        assert r["ok"] and r["by"] == "tlacks001"
        g = get_notes("2026-09")
        assert g["notes"]["운영부"]["text"].startswith("휴회 4건") and g["notes"]["운영부"]["by"] == "tlacks001"
        asyncio.run(post_note(_Req({"x-erp-user": "tlacks001"}, {"month": "2026-09", "dept": "운영부", "text": "고친 판"})))
        assert get_notes("2026-09")["notes"]["운영부"]["text"] == "고친 판" and len(_load()["history"]) == 1, "history"
        for bad in ({"month": "2026-9", "dept": "운영부", "text": "x"}, {"month": "2026-09", "dept": "총무부", "text": "x"}, {"month": "2026-09", "dept": "운영부", "text": 5}):
            try:
                asyncio.run(post_note(_Req({"x-erp-user": "a"}, bad))); assert False, bad
            except HTTPException as e:
                assert e.status_code == 400
        try:
            asyncio.run(post_note(_Req({}, {"month": "2026-09", "dept": "운영부", "text": "x"}))); assert False, "no-user"
        except HTTPException as e:
            assert e.status_code == 403
        assert get_notes("2026-10")["notes"] == {}
    print("selftest ok")


if __name__ == "__main__":
    selftest()
