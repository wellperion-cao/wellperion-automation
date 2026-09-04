# -*- coding: utf-8 -*-
"""공개 접수 폼 쓰기 이중기록 통로 POST /api/intake/{form} (배 960 · 2026-09-03 시토).

wellperion.com 안의 폼(문의 wp_inquiry_form · 강사 접수 instructor_intake · GM의일요일)이 GAS 로 직접 보내던 본문을
  ① intake_log 에 먼저 적고(GAS 가 죽어도 여기 남는다 — INC-052 류 방어)
  ② /srv/erp/api.env 의 해당 GAS URL 로 본문을 그대로 POST 해(302 → echo URL 은 urllib 이 GET 으로 따라간다) 시트를 지금처럼 쌓고
  ③ GAS 응답을 그대로 돌려준다. GAS 에 못 닿으면 {ok:true, queued:true} — 손님은 성공을 보고, 행은 gas_status='error:…' 로 남는다.
로그인 없는 공개 폼이라 nginx 는 auth_request 없이 별도 location(intake.nginx.conf · 2MB · IP 당 분당 20회).
배 961 api_write.py(로그인 화면용 쓰기 관문)와 짝 — 이쪽은 트러스트 경계 밖(손님)이라 표·경로를 나눴다.
  POST /api/intake/inquiry     → INTAKE_GAS_URL      (wp_inquiry_form.html · _en)
  POST /api/intake/instructor  → INSTRUCTOR_GAS_URL  (instructor_intake.html)
  POST /api/intake/sunday      → INSTRUCTOR_GAS_URL  (GM의일요일.html · 강사 접수와 같은 GAS)
  POST /api/intake/reception   → RECEPTION_EXEC_URL  (reception_block.html · _en 의 reg_submit — 배 960 #4b)
  POST /api/intake/selftest    → 기록만(tenant 'selftest') · GAS 전달 없음 — 배포 검증용
  GET  /api/intake/health      → 폼별 건수 · GAS 실패 건수 · 폼별 원본 모드 · 미되밀기 건수 · 마지막 되밀기 시각

폼별 원본 모드(origin_switch.py · 배 960 레인 J):
  dual   위 ①②③ 그대로.
  server 원장에만 적고 즉시 ok — GAS 왕복을 안 기다리니 화면 응답이 빨라진다. 시트는 pushback.py(1분 cron)가 되민다.
         행은 gas_status='queued' + raw_body(본문 원본)로 남고, 되민 뒤 '200' + pushed_at 이 되어 대조(reconcile)에 그대로 잡힌다.
         이 모드에선 GAS 응답값(GAS 가 매기는 접수ID·검증 거부 문구)을 화면에 못 돌려준다 — 접수번호는 서버가 같은 모양으로 매긴다.
  GET  /api/intake/reconcile   → 이중기록 대조 결과(reconcile_dual_write.py 가 06:10 에 적는다 · 3일 연속 무결 카운터)
"""
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import origin_switch  # noqa: E402  — 폼별 dual/server 스위치
from common import db  # noqa: E402
from sync_inquiries import load_env  # noqa: E402  — /srv/erp/api.env 의 GAS URL

FORMS = {"inquiry": "INTAKE_GAS_URL", "instructor": "INSTRUCTOR_GAS_URL", "sunday": "INSTRUCTOR_GAS_URL",
         "reception": "RECEPTION_EXEC_URL", "selftest": None}
MAX_BODY = 2 * 1024 * 1024
BLOB_CHARS = 8192             # 이보다 긴 문자열 = 사진·서명 base64 (사람이 쓰는 칸은 이 길이가 안 나온다)
FORWARD_TIMEOUT = 55          # 폼 fetch 상한보다 짧게
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"}   # 폼은 wellperion.com(다른 origin) 에서 text/plain 으로 보낸다
router = APIRouter(prefix="/api/intake")
load_env()


def _kst_now():
    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%dT%H:%M:%S")


def _receipt_id():
    """server 모드에서 손님에게 보일 접수번호 — GAS(.deploy-intake/Intake.js `_iId`)와 같은 모양 'L'+yyMMdd-HHmmss.
    시트에 적히는 번호는 되밀 때 GAS 가 다시 매긴다(초 단위로 다를 수 있다 · 조회 열쇠는 이름·전화라 지장 없음)."""
    return datetime.now(timezone(timedelta(hours=9))).strftime("L%y%m%d-%H%M%S")


def redact_blobs(payload):
    """원장에 사진·서명 base64 를 통째로 넣지 않는다 — 길이·sha256 만 남긴다(GAS 로는 원본 본문이 그대로 간다).
    사진은 GAS 가 Drive 에 올려 URL 을 시트에 적으므로 서버가 원본을 이고 있을 이유가 없다(정의서 A §7 사진)."""
    if not isinstance(payload, dict):
        return payload
    return {k: ({"_redacted": len(v), "_sha256": hashlib.sha256(v.encode("utf-8", "replace")).hexdigest()}
                if isinstance(v, str) and len(v) > BLOB_CHARS else v)
            for k, v in payload.items()}


def gas_forward(url, body):
    """본문을 그대로 GAS 에 POST. (상태코드, 응답문자열). 302 echo 는 urllib 기본 처리(POST→GET)로 따라간다."""
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "text/plain;charset=utf-8"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=FORWARD_TIMEOUT) as r:
            return str(r.status), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return str(e.code), e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 — 사유를 행에 남긴다
        return "error:%s" % type(e).__name__, str(e)[:500]


@router.options("/{form}")
def preflight(form: str):
    return Response(status_code=204, headers=CORS)


@router.post("/{form}")
async def intake(form: str, request: Request):
    if form not in FORMS:
        raise HTTPException(404, "모르는 폼: %s" % form)
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(413, "본문 2MB 초과")
    text = body.decode("utf-8", "replace")
    try:
        payload = json.loads(text)
        if not isinstance(payload, dict):
            payload = {"_raw": payload}
    except ValueError:
        payload = {"_raw": text}
    tenant = "selftest" if form == "selftest" else db.TENANT
    server_mode = origin_switch.mode(form) == "server"      # 스위치 파일 한 줄 — 재시작 없이 갈린다
    conn = db.connect()
    with conn:
        row_id = conn.execute(
            "INSERT INTO intake_log (tenant_id, form, received_at, payload, gas_status, raw_body)"
            " VALUES (%s,%s,%s,%s::jsonb,%s,%s) RETURNING id",
            (tenant, form, _kst_now(), json.dumps(redact_blobs(payload), ensure_ascii=False),
             "queued" if server_mode else "pending", text if server_mode else None)).fetchone()[0]
    # 여기까지 오면 DB 엔 남았다 — 아래가 실패해도 접수는 잃지 않는다.
    if server_mode:
        conn.close()
        out = {"ok": True, "id": _receipt_id(), "form": form, "queued": True, "mode": "server", "row": row_id}
        return Response(json.dumps(out, ensure_ascii=False), media_type="application/json; charset=utf-8", headers=CORS)
    key = FORMS[form]
    url = os.environ.get(key or "", "")
    if key is None or not url:
        status, resp = ("skipped", "") if key is None else ("error:no-url", key + " 없음 — /srv/erp/api.env")
    else:
        status, resp = await run_in_threadpool(gas_forward, url, body)   # GAS 왕복(최대 55초)이 다른 요청을 막지 않게
    with conn:
        conn.execute("UPDATE intake_log SET gas_status=%s, gas_response=%s WHERE id=%s", (status, resp[:4000], row_id))
    conn.close()
    if status == "200":
        return Response(resp, media_type="application/json; charset=utf-8", headers=CORS)   # GAS 응답 그대로
    out = {"ok": True, "queued": True, "id": row_id, "form": form, "gas_status": status}
    return Response(json.dumps(out, ensure_ascii=False), media_type="application/json; charset=utf-8", headers=CORS)


@router.get("/reconcile")
def reconcile():
    """이중기록 대조 결과 — reconcile_dual_write.py 가 매일 06:10(KST) 적어 둔 파일 그대로.
    3일 연속 무결(streak_ok_days>=3) 이면 사람이 서버 원본 전환을 판단한다(자동 전환 없음)."""
    path = os.path.join(os.environ.get("ERP_STATUS_DIR", "/srv/erp/status"), "dual_write_reconcile.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        raise HTTPException(503, "아직 대조 전 — %s 없음" % path)


# 되밀기 시도 상한 — 여기까지 실패하면 그만 두드리고 사람이 본다(pushback.py 가 같은 값을 쓴다).
PUSH_MAX_TRIES = 5
# 아직 시트에 못 간 행 / 사람이 봐야 하는 행 — 두 원장을 같은 잣대로 센다.
_UNPUSHED = "gas_status='queued' AND pushed_at IS NULL"
_PUSH_FAILED = ("(pushed_at IS NULL AND push_tries >= %d) OR (pushed_at IS NOT NULL AND gas_status='gas-error')"
                % PUSH_MAX_TRIES)


@router.get("/health")
def health():
    conn = db.connect(readonly=True)
    with conn:
        rows = conn.execute("SELECT form, COUNT(*) c,"
                            " SUM(CASE WHEN gas_status IN ('200','skipped','queued') THEN 0 ELSE 1 END) bad,"
                            " COUNT(*) FILTER (WHERE " + _UNPUSHED + ") queued,"
                            " MAX(received_at) last FROM intake_log WHERE tenant_id=%s GROUP BY form",
                            (db.TENANT,)).fetchall()
        push = conn.execute(
            "SELECT COUNT(*) FILTER (WHERE " + _UNPUSHED + ") unpushed,"
            " COUNT(*) FILTER (WHERE " + _PUSH_FAILED + ") failed, MAX(pushed_at) last_pushed FROM ("
            "  SELECT gas_status, pushed_at, push_tries FROM intake_log WHERE tenant_id=%s"
            "  UNION ALL SELECT gas_status, pushed_at, push_tries FROM write_log WHERE tenant_id=%s) t",
            (db.TENANT, db.TENANT)).fetchone()
    conn.close()
    return {"ok": True,
            "forms": {r["form"]: {"count": r["c"], "gas_failed": int(r["bad"] or 0),
                                  "unpushed": r["queued"], "last": r["last"]} for r in rows},
            "origin_mode": origin_switch.modes(),                     # 지금 어느 폼·영역이 서버 원본인가
            "pushback": {"unpushed": push["unpushed"], "failed": push["failed"],   # 시트에 아직 못 간 건수
                         "last_pushed_at": push["last_pushed"] or ""}}             # 마지막 되밀기 시각(KST)
