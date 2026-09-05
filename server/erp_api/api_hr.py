# -*- coding: utf-8 -*-
"""인사(CHRO) 도메인 API — 읽기 라우트 (인사 데이터 AWS 이관 1단계 · 2026-09-05 CHRO/A-5).

근거 = CTO 회신 status/briefs/CTO-2026-09-05-인사데이터-AWS이관-서버준비-회신.md
       (§1 표 3·4 경로·인증·스택 · §2 6단계 중 ①읽기 미러 · §3 테스트 데이터 격리).
표 정의 = common/schema.sql 의 hr 스키마 21개 표. 적재 = migrate_hr.py.
app.py 가 같은 폴더의 api_*.py 를 자동 등록한다 — app.py 본문은 건드리지 않는다.

  GET  /api/hr/health                 표별 행수 · 마지막 적재 실행 상태
  GET  /api/hr/{db}                   db = emp·exitroster·exit·appl·hire·eval·onbo·blacklist·leave
  POST /api/hr/read                   본문 {"db":"appl"} — 현행 화면이 GAS 를 부르던 모양 그대로

★ 화면 수정을 최소화하는 형태를 택한 근거(지시서 요구 · 판단 3가지)
  1) 봉투에 results 와 data 를 같이 싣는다.
     현행 허브(3. 웰페리온 가이드/chro/hub/index.html)의 유일한 정규화 함수가
     `extractResults(raw){ if(raw&&Array.isArray(raw.results)) return raw.results; ... }` 하나다(실측 1곳).
     그래서 results 를 그대로 실으면 화면 데이터 계층은 한 줄도 안 고쳐도 된다.
     동시에 ERP 표준 봉투는 {ok, data} 라(회신 §1-4 · 배990 선례) data 에도 같은 배열을 싣는다.
     한 배열을 두 이름으로 가리키는 것뿐이라 비용이 없고, ③단계(화면 전환)에서 results 를 떼면 된다.
  2) 본문 POST 호환 라우트를 둔다.
     허브는 `fetch(NOTION_FN,{method:"POST", headers:{"Content-Type":"text/plain;charset=utf-8"},
     body:JSON.stringify({db:key,password:SESSION_PW})})` 로 읽는다. GET 만 만들면 fetch 호출부 전체를
     고쳐야 하지만, 같은 모양의 POST 를 두면 화면은 주소 상수(NOTION_FN) 한 줄만 바꾸면 된다.
     ★Content-Type 이 text/plain 이라 FastAPI 자동 본문 파싱(Pydantic)이 못 받는다 —
       api_reception.py 와 같이 Request 로 원문을 받아 직접 json.loads 한다.
     ★본문의 password 는 읽지도, 기록하지도 않는다(아래 3).
  3) 각 행에 _sheet_row 를 그대로 실어 준다.
     화면·러너가 행번호를 58개소/7파일에서 쓴다(사진 파일명 r<row>.jpg 포함). 새 기본키(_id)를 같이 주되
     _sheet_row 를 끊지 않아야 ①단계에서 화면이 산다. ⚠️ 새 쓰기 경로는 _sheet_row 를 열쇠로 받지 않는다 —
     받으면 행번호 의존이 그대로 이사한다(schema.sql hr 머리말 ①).

인증·권한: nginx auth_request 가 /api/ 전체를 이미 막는다(erp_api/api.nginx.conf) — 로그인 쿠키가 없으면 401.
  ⛔ 라우터 안에서 비밀번호를 검사하지 않는다. 현행 GAS 의 공유 평문 비번(admin/viewer) 방식을 그대로 옮기지 않는다.
  ⚠️ 미결(매니저·시토 확인 필요): 현행 GAS 는 viewer 비번일 때 PII 를 가려서 준다(maskPiiForViewer_).
     지금 관문은 /api/ 에 X-Erp-User 만 넘기고 X-Erp-Role 은 안 넘긴다(api.nginx.conf 5·10행).
     그래서 이 API 는 역할을 알 수 없고, 관문을 통과한 사람에게 원문을 준다 = PII 노출 범위가 넓어진다.
     해소안 두 가지 — ⓐ api.nginx.conf 에 auth_request_set $erp_role $upstream_http_x_erp_role;
     + proxy_set_header X-Erp-Role $erp_role; 한 쌍 추가(erp_auth 는 이미 X-Erp-Role 을 돌려준다)
     ⓑ erp/modules.json 권한(인사 화면 = 나우열M 개인 예외 · 배1026)으로 화면 자체를 잠근다.
     아래 _role() 은 헤더가 오면 읽도록만 해 뒀고, 마스킹 정책 자체는 확정 전이라 넣지 않았다(추측 금지).

테스트/더미 행: 쓰기 관문과 같은 판정(common/db.py is_test_payload) 결과가 is_test 칸에 들어 있다 —
  읽기는 기본으로 뺀다(?include_test=1 이면 포함). 새 판정 함수를 만들지 않는다(회신 §3).

자체점검: python3 api_hr.py --selftest   (DB·네트워크 없음 — 봉투 모양·행 변환·열쇠표만)
"""
import datetime
import decimal
import json
import os
import sys
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # 저장소 server/ = 서버 /srv/erp/
from common import db  # noqa: E402  — DB 를 여는 유일한 자리 · 모든 조회는 tenant_id 로 거른다

SOURCE = "hr-db"          # 다른 미러는 'sheet-mirror'(정본=시트). hr 은 ⑤단계 뒤 서버가 정본이 되므로 이름을 나눈다.
MAX_ROWS = 20000          # 안전 상한 — 휴무 5,603행이 최대라 평상시엔 안 닿는다. 닿으면 truncated=true 로 알린다.
router = APIRouter(prefix="/api/hr")

# 현행 GAS 읽기 열쇠(db:...) → hr 표. label 은 사람이 읽는 이름(오류 문구·health 용).
#   emp/exitroster 는 같은 표(hr.employee)를 status 로 가른다 — '현재근무자'와 '퇴사자 명부'는 같은 사람의 상태 차이다.
#   ⚠️ exitroster 는 정본 문서 db 목록에 빠져 있으나 실제로 살아 있는 읽기 열쇠다(70행). 빼면 퇴사자 명부가 통째로 사라진다.
DBS = {
    "emp":        {"table": "hr.employee",    "pk": "employee_id",   "where": "status <> '퇴사'",
                   "order": "dept_name_raw NULLS LAST, legacy_row",  "label": "현재근무자"},
    "exitroster": {"table": "hr.employee",    "pk": "employee_id",   "where": "status = '퇴사'",
                   "order": "resign_date DESC NULLS LAST, legacy_row", "label": "퇴사자 명부"},
    "exit":       {"table": "hr.resignation", "pk": "resignation_id", "where": "",
                   "order": "last_work_date DESC NULLS LAST, legacy_row", "label": "퇴사처리"},
    "appl":       {"table": "hr.applicant",   "pk": "applicant_id",  "where": "",
                   "order": "applied_at DESC NULLS LAST, legacy_row", "label": "지원자"},
    "hire":       {"table": "hr.job_posting", "pk": "posting_id",    "where": "",
                   "order": "start_date DESC NULLS LAST, legacy_row", "label": "채용공고"},
    "eval":       {"table": "hr.evaluation",  "pk": "eval_id",       "where": "",
                   "order": "period_start DESC NULLS LAST, legacy_row", "label": "인사평가"},
    "onbo":       {"table": "hr.onboarding_item", "pk": "item_id",   "where": "",
                   "order": "employee_name_raw, week_no NULLS LAST, legacy_row", "label": "입사·온보딩"},
    "blacklist":  {"table": "hr.hire_blacklist",  "pk": "blacklist_id", "where": "",
                   "order": "registered_at DESC NULLS LAST, legacy_row", "label": "채용블랙리스트"},
    "leave":      {"table": "hr.leave_entry", "pk": "leave_id",      "where": "",
                   "order": "work_date, person_name_raw", "label": "휴무"},
}
# 행 봉투에서 감추는 내부 칸 — data 원본이 없을 때 정규화 칸으로 행을 만들 때만 쓴다.
_HIDDEN = ("tenant_id", "data", "is_test", "created_at", "updated_at", "synced_at", "legacy_tab")


def _open():
    try:
        return db.connect(readonly=True)          # 읽기 전용으로 연다 — 이 프로세스가 hr 표를 못 건드리게 못을 박는다
    except db.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)


def _role(request):
    """관문이 넘겨 주면 읽는다. 지금 api.nginx.conf 는 X-Erp-User 만 넘기므로 대개 빈 문자열이다(위 미결 참고)."""
    return (request.headers.get("x-erp-role") or "").strip()


def jsonable(v):
    """DATE·TIME·TIMESTAMPTZ·NUMERIC 을 화면이 받던 문자열·숫자 모양으로. 지어내지 않고 표준 표기만 쓴다."""
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, datetime.datetime):
        return v.isoformat(sep=" ", timespec="seconds")
    if isinstance(v, (datetime.date, datetime.time)):
        return v.isoformat()
    return v


def row_out(r, key, pk):
    """행 1개 → 화면이 받던 모양.
    data(시트 원본 레코드)가 있으면 그것을 그대로 준다 — 한글 칸 이름을 여기서 지어내지 않기 위한 선택이다.
    ⑤단계(GAS 끄기) 뒤 data 를 지우면 정규화 칸으로 자동 전환된다(그때 화면 어댑터를 ③단계에서 이미 바꿔 둔다)."""
    keys = list(r.keys())
    src = r["data"] if "data" in keys else None
    if isinstance(src, str):                      # 드라이버 설정에 따라 문자열로 올 수 있다
        try:
            src = json.loads(src)
        except (TypeError, ValueError):
            src = None
    d = dict(src) if isinstance(src, dict) else {k: jsonable(r[k]) for k in keys if k not in _HIDDEN}
    d["_id"] = r[pk] if pk in keys else None
    d["_sheet_row"] = r["legacy_row"] if "legacy_row" in keys else None   # 화면·사진 파일명·과거 로그가 쓰는 rNN
    d["_db"] = key
    d["_source"] = SOURCE
    return d


def envelope(key, rows, total, truncated=False):
    """{ok, data} = ERP 표준 봉투(회신 §1-4) + results = 현행 화면 extractResults 호환. 같은 배열 하나를 두 이름으로."""
    return {"ok": True, "db": key, "count": len(rows), "total": total,
            "results": rows, "data": rows, "truncated": truncated, "_source": SOURCE}


def _fetch(key, limit, offset, include_test, date_from, date_to):
    spec = DBS[key]
    where, args = ["tenant_id = %s"], [db.TENANT]
    if spec["where"]:
        where.append(spec["where"])
    if not include_test:
        where.append("is_test = FALSE")
    if key == "leave":                            # 휴무만 기간 좁히기 — 5,603행을 매번 다 보낼 이유가 없다
        if date_from:
            where.append("work_date >= %s")
            args.append(date_from)
        if date_to:
            where.append("work_date <= %s")
            args.append(date_to)
    w = " AND ".join(where)
    cap = MAX_ROWS if not limit else min(limit, MAX_ROWS)
    conn = _open()
    with conn:
        total = conn.execute("SELECT COUNT(*) FROM %s WHERE %s" % (spec["table"], w), args).fetchone()[0]
        rs = conn.execute("SELECT * FROM %s WHERE %s ORDER BY %s LIMIT %%s OFFSET %%s"
                          % (spec["table"], w, spec["order"]), args + [cap, offset]).fetchall()
    conn.close()
    rows = [row_out(r, key, spec["pk"]) for r in rs]
    return rows, total, (not limit and total > offset + len(rows))


@router.get("/health")
def health():
    """표별 행수 + 마지막 적재 실행. 적재가 running 인 채로 남아 있으면(중단) 여기서 바로 보인다."""
    try:
        conn = db.connect(readonly=True)
    except db.Error as e:
        return {"ok": False, "detail": "DB 열기 실패: %s" % e, "_source": SOURCE}
    with conn:
        rows = {}
        for key, spec in DBS.items():
            w = "tenant_id=%s" + ((" AND " + spec["where"]) if spec["where"] else "")
            rows[key] = conn.execute("SELECT COUNT(*) FROM %s WHERE %s" % (spec["table"], w), (db.TENANT,)).fetchone()[0]
        run = conn.execute("SELECT run_id, mode, status, started_at, finished_at, note FROM hr.migration_run"
                           " WHERE tenant_id=%s ORDER BY run_id DESC LIMIT 1", (db.TENANT,)).fetchone()
    conn.close()
    last = None
    if run is not None:
        last = {"run_id": run["run_id"], "mode": run["mode"], "status": run["status"],
                "started_at": jsonable(run["started_at"]), "finished_at": jsonable(run["finished_at"]),
                "note": run["note"]}
    return {"ok": sum(rows.values()) > 0, "rows": rows, "last_migration": last,
            "stale_run": bool(last and last["status"] == "running"), "_source": SOURCE}


@router.post("/read")
async def read(request: Request):
    """현행 화면이 GAS 를 부르던 모양 그대로 — 본문 {"db":"appl"}. 주소 상수 한 줄만 바꾸면 화면이 그대로 산다.
    ⛔ 본문에 password 가 실려 와도 읽지 않고 기록하지 않는다. 인증은 앞단 nginx auth_request 가 이미 했다."""
    try:
        payload = json.loads((await request.body()).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError
    except Exception:
        return JSONResponse({"ok": False, "error": "bad-payload", "_source": SOURCE}, status_code=400)
    key = str(payload.get("db") or "").strip()
    if key not in DBS:
        return JSONResponse({"ok": False, "error": "알 수 없는 db 열쇠: %s" % key[:40],
                             "keys": sorted(DBS), "_source": SOURCE}, status_code=400)
    rows, total, truncated = _fetch(key, 0, 0, False, None, None)
    out = envelope(key, rows, total, truncated)
    role = _role(request)
    if role:                       # 관문이 역할을 넘겨 줄 때만 실어 준다(블랙리스트 화면이 r.role==="admin" 을 본다)
        out["role"] = role
    return out


@router.get("/{db_key}")
def read_get(
    db_key: str,
    limit: int = Query(0, ge=0, le=MAX_ROWS),     # 0 = 전체. 화면이 전량을 받아 집계하므로 전체가 기본이다.
    offset: int = Query(0, ge=0),
    include_test: int = Query(0, ge=0, le=1),     # 테스트/더미 행 포함 여부(기본 제외)
    date_from: Optional[str] = Query(None, alias="from"),   # 휴무 전용 — work_date 하한(YYYY-MM-DD)
    date_to: Optional[str] = Query(None, alias="to"),       # 휴무 전용 — work_date 상한
):
    if db_key not in DBS:
        raise HTTPException(404, "알 수 없는 db 열쇠: %s (가능: %s)" % (db_key[:40], ", ".join(sorted(DBS))))
    rows, total, truncated = _fetch(db_key, limit, offset, bool(include_test), date_from, date_to)
    out = envelope(db_key, rows, total, truncated)
    out["limit"] = limit
    out["offset"] = offset
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  쓰기 — 2단계(회신 §2 ②쓰기 서버화). 이번 커밋 범위 밖이라 뼈대만 적어 둔다.
#  TODO(2단계) 라우트 목록 — 현행 GAS 액션과 1:1 로 맞춘다
#    POST /api/hr/applicant            register-applicant / update-applicant   (등록 3게이트 유지)
#    POST /api/hr/applicant/stage      set-stage      ★stage 를 덮지 말고 hr.application_stage_history 에 쌓는다
#    POST /api/hr/applicant/photo      set-photo      ★파일명 r<row>.jpg 는 당분간 유지(러너 3종이 묶여 있다)
#    POST /api/hr/employee             hire-complete / fix-emp-field / resign
#    POST /api/hr/onboarding           add-onboarding / update-onboarding / onbo-checkin-save
#    POST /api/hr/evaluation           save-eval
#    POST /api/hr/leave                set-leave / set-leave-bulk  ★단건 UPSERT — full-sync 월 병합 규칙이 필요 없어진다
#    POST /api/hr/log                  log-add        ★actor_code 없는 쓰기는 거절(공통 셀프체크 6 을 서버가 강제)
#  2단계에서 반드시 지킬 것
#    · db.is_test_payload(payload) 를 그대로 재사용해 is_test 를 찍는다 — 새 판정 함수를 만들지 않는다(회신 §3).
#    · 쓴 사람 = request.headers["x-erp-user"](관문이 넘긴 로그인 이메일). 화면이 보낸 이름을 믿지 않는다.
#    · 쓰기 응답에 '갱신된 그 행'을 그대로 실어 준다 — 화면이 전체를 다시 읽지 않게(휴무 1칸 저장 후 5,603행 재조회 소멸).
#    · 트랜잭션 + UNIQUE 제약이 있으므로 재전송이 안전해진다 → 현행 '쓰기 재전송 절대 금지' 규칙의 폐기 근거.
#      ⚠️ 단 폐기는 이관 검증 통과 후. 병행 기간에는 종전 규칙을 그대로 지킨다.
# ═══════════════════════════════════════════════════════════════════════════════════════════


def selftest():
    """DB·네트워크 없이 — 열쇠표 정합 · 봉투 모양 · 행 변환만."""
    assert set(DBS) == {"emp", "exitroster", "exit", "appl", "hire", "eval", "onbo", "blacklist", "leave"}
    for k, s in DBS.items():
        assert s["table"].startswith("hr."), k
        assert s["pk"] and s["order"] and s["label"], k
    # 봉투 — results 와 data 가 같은 배열을 가리켜야 화면 정규화 함수가 그대로 산다
    e = envelope("appl", [{"a": 1}], 1)
    assert e["ok"] is True and e["results"] == e["data"] and e["count"] == 1 and e["_source"] == SOURCE
    assert e["results"] is e["data"], "같은 배열 하나여야 한다(복사본이면 메모리만 두 배)"
    # 행 변환 — data 원본이 있으면 그대로, _sheet_row·_id 는 항상 덧붙는다
    r = {"applicant_id": 7, "legacy_row": 112, "tenant_id": "wellperion",
         "data": {"지원자명": "홍길동", "전형 단계": "서류"}, "applicant_name": "홍길동"}
    o = row_out(r, "appl", "applicant_id")
    assert o["지원자명"] == "홍길동" and o["_sheet_row"] == 112 and o["_id"] == 7 and o["_db"] == "appl"
    # data 가 문자열로 와도 같은 결과
    r2 = dict(r, data=json.dumps({"지원자명": "홍길동"}, ensure_ascii=False))
    assert row_out(r2, "appl", "applicant_id")["지원자명"] == "홍길동"
    # data 가 없으면 정규화 칸으로 — 내부 칸은 감춘다
    r3 = {"leave_id": 3, "legacy_row": 20, "tenant_id": "wellperion", "person_name_raw": "홍길동",
          "work_date": datetime.date(2026, 9, 5), "shift_start": datetime.time(9, 0),
          "is_test": False, "synced_at": datetime.datetime(2026, 9, 5, 12, 0)}
    o3 = row_out(r3, "leave", "leave_id")
    assert o3["work_date"] == "2026-09-05" and o3["shift_start"] == "09:00:00" and o3["_sheet_row"] == 20
    assert "tenant_id" not in o3 and "is_test" not in o3 and "synced_at" not in o3
    assert jsonable(decimal.Decimal("4.50")) == 4.5
    # 라우터 안에 자체 비밀번호 검사가 없어야 한다(관문 위임 · 지시서 요구).
    # 머리말 docstring 은 현행 화면 호출 모양을 인용하느라 password 라는 낱말을 쓰므로 그 뒤부터,
    # 그리고 이 점검 함수 자신(금지어 목록이 여기 있다)은 빼고 = 라우트 본문만 본다.
    code = open(os.path.abspath(__file__), encoding="utf-8").read().split('"""', 2)[2].split("def selftest(", 1)[0]
    # ⛔ 금지어 목록에 실제 비밀번호 조각을 적지 않는다 — 공개 저장소다. '비번을 다루는 모양'만 잡는다.
    for banned in ("adminPassword", "SESSION_PW", "password ==", 'payload.get("password")', "payload.get('password')"):
        assert banned not in code, "라우터가 비밀번호를 다루면 안 된다: " + banned
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else 0)
