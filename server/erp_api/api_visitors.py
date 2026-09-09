# -*- coding: utf-8 -*-
"""일일 입장객 — 순 방문자 수 (배908·1071 · 시포 2026-09-09). app.py 가 api_*.py 를 자동 등록한다.

  GET /api/visitors?date=2026-09-08   그날 브로제이 출석 적재분으로 센 정회원·준회원·유소년·직원·제외

무엇을 세나 — **운영부가 지금 쓰는 스프레드시트 수식을 그대로 옮긴 것**이다(이경연 실장 2026-09-09 공유).
시트는 브로제이 출석부를 엑셀로 내려받아 붙여넣고 아래 규칙으로 센다. 서버는 같은 원장을 API 로 받아
같은 규칙을 적용한다 — 사람이 내려받고 붙여넣는 손을 없애는 것이 목적이라 **규칙을 바꾸지 않는다**
(미러 읽기 규칙은 원본과 같은 칸·같은 조건으로만 · INC-055).

  칸 짝: 시트 G열 회원명 = name · I열 연락처 = phone · P열 입장 수강명 = ticket_info.name
  ① 직원  : 회원명이 「운영/지원/관리부/시설/고문/수영/스쿼시/골프/P.T/PL + 공백」 으로 시작하거나
            「공백 + 과장/프로」 로 끝나거나, 수강명에 '프리랜서' 가 있으면 직원(집계에서 뺀다)
  ② 유소년: 수강명에 (WSC)
  ③ 준회원: 수강명에 (준)
  ④ 정회원: 수강명에 (정) 또는 (단) 또는 (FD)
  ⑤ 그 외 : '제외' — 어느 태그도 없는 이용권은 세지 않는다
  중복 제거: 「회원명|연락처」 를 한 사람으로 본다(하루 여러 번 들어와도 1명 · 시트 COUNTUNIQUEIFS 와 같다)

★출석 실패(문이 안 열린 기록)도 시트가 걸러내지 않으므로 여기서도 걸러내지 않는다 — 실측으로
  2026-09-08 정회원 549 · 준회원 37 · 유소년 44 로 시트와 세 칸 모두 정확히 일치했다.

자체점검: python3 api_visitors.py   (DB·네트워크 없음 — 분류·중복제거 판정만)
"""
import json
import os
import re
import sys
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db  # noqa: E402

router = APIRouter(prefix="/api/visitors")

# 시트 V열 수식의 정규식 두 개를 그대로 옮긴다(회원명 기준 직원 판정).
STAFF_NAME_PREFIX = re.compile(r"^(운영|지원|관리부|시설|고문|수영|스쿼시|골프|P\.T|PL)\s")
STAFF_NAME_SUFFIX = re.compile(r"\s(과장|프로)$")
BUCKETS = ("정회원", "준회원", "유소년", "직원", "제외")


def category(member_name, ticket_name):
    """시트 V열 수식과 같은 순서로 판정한다 — 직원이 먼저고, 그다음 이용권 태그."""
    g = str(member_name or "")
    p = str(ticket_name or "")
    if STAFF_NAME_PREFIX.search(g) or STAFF_NAME_SUFFIX.search(g) or "프리랜서" in p:
        return "직원"
    if "(WSC)" in p:
        return "유소년"
    if "(준)" in p:
        return "준회원"
    if "(정)" in p or "(단)" in p or "(FD)" in p:
        return "정회원"
    return "제외"


def count(rows):
    """출석 행 목록 → 칸별 순 방문자 수. 회원명이 빈 행은 시트처럼 통째로 건너뛴다."""
    uniq = {b: set() for b in BUCKETS}
    entries = {b: 0 for b in BUCKETS}
    for r in rows:
        if not isinstance(r, dict):
            continue
        name = str(r.get("name") or "")
        if not name:
            continue
        ticket = str((r.get("ticket_info") or {}).get("name") or "")
        c = category(name, ticket)
        entries[c] += 1
        uniq[c].add(name + "|" + str(r.get("phone") or ""))
    out = {"visitors": {b: len(uniq[b]) for b in BUCKETS},
           "entries": entries,
           "total": len(uniq["정회원"] | uniq["준회원"] | uniq["유소년"]),
           "repeat_visitors": 0}
    # 하루 두 번 이상 들어온 사람 수(시트 K3) — 집계 대상 셋 안에서만 센다
    seen = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        name = str(r.get("name") or "")
        if not name:
            continue
        c = category(name, str((r.get("ticket_info") or {}).get("name") or ""))
        if c in ("직원", "제외"):
            continue
        k = name + "|" + str(r.get("phone") or "")
        seen[k] = seen.get(k, 0) + 1
    out["repeat_visitors"] = sum(1 for v in seen.values() if v > 1)
    return out


@router.get("")
def visitors(date: Optional[str] = Query(None, description="YYYY-MM-DD · 기본 어제(KST)")):
    from datetime import datetime, timedelta, timezone   # noqa: PLC0415
    kst = timezone(timedelta(hours=9))
    day = date or (datetime.now(kst).date() - timedelta(days=1)).isoformat()
    try:
        conn = db.connect(readonly=True)
    except db.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)
    with conn:
        row = conn.execute(
            "SELECT data, synced_at FROM brojay_records WHERE tenant_id=%s AND kind='entries' AND key=%s",
            (db.TENANT, day)).fetchone()
    conn.close()
    if not row:
        return {"date": day, "ok": False, "detail": "그 날짜 출석 적재분이 없다", "_source": "brojay"}
    try:
        payload = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
    except Exception:
        payload = None
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(rows, dict):
        rows = rows.get("data")
    out = count(rows or [])
    out.update({"date": day, "ok": True, "synced_at": row["synced_at"], "_source": "brojay",
                "rule": "운영부 시트 수식 이식(2026-09-09 이경연 실장 공유) — 규칙을 바꾸지 않는다"})
    return out


if __name__ == "__main__":   # python3 api_visitors.py
    assert category("김철수", "★★(정)플래티넘 ▶ GYM+사우나 ▶ 12개월") == "정회원"
    assert category("김철수", "★(FD)노블레스+골프") == "정회원"
    assert category("김철수", "★★(단)플래티넘 ▶ 1개월") == "정회원"
    assert category("김철수", "(준)수영강습 단체반 8회") == "준회원"
    assert category("김철수", "★★(WSC)수영 ▶ 1:5 ▶ 4회") == "유소년"
    assert category("김철수", "★노블레스 ▶ GYM+골프+수영+사우나") == "제외"   # 태그가 하나도 없다
    # 직원 — 이름 앞머리(부서) · 이름 끝(직함) · 이용권에 프리랜서
    assert category("수영 홍길동", "★★(정)플래티넘") == "직원"
    assert category("P.T 김코치", "★★(정)플래티넘") == "직원"
    assert category("홍길동 프로", "★★(정)플래티넘") == "직원"
    assert category("홍길동 과장", "★★(정)플래티넘") == "직원"
    assert category("홍길동", "★프리랜서") == "직원"
    assert category("수영장 이용객", "★★(정)플래티넘") == "정회원"   # 공백 없이 붙은 말은 부서가 아니다
    # 중복 제거 — 같은 사람이 두 번 들어와도 1명, 동명이인은 연락처로 갈린다
    rows = [
        {"name": "김철수", "phone": "010-1111-1111", "ticket_info": {"name": "★★(정)플래티넘"}},
        {"name": "김철수", "phone": "010-1111-1111", "ticket_info": {"name": "★★(정)플래티넘"}},
        {"name": "김철수", "phone": "010-2222-2222", "ticket_info": {"name": "★★(정)플래티넘"}},
        {"name": "박영희", "phone": "010-3333-3333", "ticket_info": {"name": "(준)수영강습 단체반"}},
        {"name": "이유아", "phone": "010-4444-4444", "ticket_info": {"name": "★★(WSC)수영"}},
        {"name": "수영 강사", "phone": "010-5555-5555", "ticket_info": {"name": "★★(정)플래티넘"}},
        {"name": "무태그", "phone": "010-6666-6666", "ticket_info": {"name": "★노블레스"}},
        {"name": "", "phone": "010-7777-7777", "ticket_info": {"name": "★★(정)플래티넘"}},
    ]
    out = count(rows)
    assert out["visitors"]["정회원"] == 2, out       # 동명이인 2명(같은 사람 2회는 1명)
    assert out["visitors"]["준회원"] == 1 and out["visitors"]["유소년"] == 1
    assert out["visitors"]["직원"] == 1 and out["visitors"]["제외"] == 1
    assert out["total"] == 4                          # 직원·제외는 총합에서 뺀다
    assert out["entries"]["정회원"] == 3               # 입장 횟수는 3
    assert out["repeat_visitors"] == 1                 # 두 번 들어온 사람 1명
    print("자체점검 통과")
