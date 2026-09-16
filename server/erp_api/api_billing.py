# -*- coding: utf-8 -*-
"""랩스 구독 카드 자동결제 — 토스페이먼츠 빌링 (배12680 · 2026-09-16 시토 · GM 확정 2026-09-16).

파트너(tenant, 예 '2_dietcamp')가 카드를 한 번 등록하면(authKey 교환 → 빌링키) 매달 1일 자동 청구한다.
정본 = erp/admin/company_roadmap.html §5-2 결제 방식 행 · §9 결정 6. 담당 근거·구조는 status/_queue.json 배12680 note.

  POST /api/billing/{tenant}/billing-key   {"authKey","customerKey"(생략시 자동생성),"plan"}
       고객이 토스 카드 등록 창(requestBillingAuth)에서 authKey 를 받은 뒤 여기로 넘기면
       토스 /v1/billing/authorizations/issue 로 교환해 빌링키를 받는다. 빌링키 원문은 billing_secrets
       표에만 저장하고(별도 표 · API 응답·로그에 절대 안 싣는다), billing_subscriptions 에는
       has_billing_key=true 만 남는다.
  GET  /api/billing/{tenant}               plan·amount·next_charge·status·has_billing_key·최근 청구 이력.
       빌링키 원문 없이.
  POST /api/billing/{tenant}/charge        수동 청구 1회(관리자 콘솔 "지금 청구" 버튼·시험용).
       매달 1일 정기 청구는 billing_charge.py(cron)가 이 파일의 charge_one() 을 직접 불러 돈다
       (HTTP 왕복 없이 — cron 은 같은 서버 프로세스라 내부 호출이 더 단순하고 안전하다).

인증 = 기존 관문 재사용(api_partner_secrets.py 와 같은 방식) — x-erp-user 헤더가 ERP_PLATFORM_ADMINS 에
있을 때만. nginx auth_request 뒤에서 로그인 자체는 이미 걸러진다.

청구 idempotency = billing_charges 표 PRIMARY KEY (tenant_id, tenant, ym) 그 자체 — 같은 달 두 번째
호출은 기존 행을 보고 건너뛴다(토스를 두 번 치지 않는다). 실패하면 이번 달 안에 딱 한 번만 재시도
(retry_at = 실패 시각 + 3일) — 재시도까지 또 실패하면 그 달은 status='failed' 로 끝(다음 달에 다시 시도).

카드번호·빌링키 원문은 절대 로그에 안 찍는다(INC-061). 토스 시크릿 키는 서버 api.env 의 TOSS_SECRET_KEY
하나(값은 GM/시토가 넣는다 — 이 파일은 이름만 읽는다). 테스트 키(test_sk_...)로 먼저 끝까지 돌리고,
가맹 승인 뒤 실키(live_sk_...)로 교체한다(값 교체뿐 — 코드는 그대로).
"""
import base64
import datetime as dt
import json
import os
import secrets
import sys
import urllib.error
import urllib.request

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db  # noqa: E402

router = APIRouter(prefix="/api/billing")

KST = dt.timezone(dt.timedelta(hours=9))
TOSS_BASE = "https://api.tosspayments.com"

# 랩스 소개서 §5 확정값(company_roadmap.html) — 금액은 부가세 별도. 운영(ops)은 "준비 중"이라 아직 안 판다.
PLAN_AMOUNTS = {"start": 190000, "growth": 390000, "ops": 690000}

# 파트너(과금 대상) tenant — api_chat.py/api_faq_intake.py TENANTS 에서 웰페리온 자신(1_wellperion)을 뺀 값.
# 모듈 독립(약속: 한 도메인 임포트 실패가 다른 도메인까지 죽이지 않는다)을 지키려 여기서 다시 적는다 —
# 새 파트너가 생기면 저 두 파일과 함께 여기도 늘린다.
PARTNER_TENANTS = ("2_dietcamp", "3_gocheokgolf")


class TossError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__("%s: %s" % (code, message))


def _user(request):
    return (request.headers.get("x-erp-user") or "").strip().lower()


def _admins():
    raw = os.environ.get("ERP_PLATFORM_ADMINS", "cao@wellperion.com")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _now():
    return dt.datetime.now(KST)


def _now_str():
    return _now().strftime("%Y-%m-%d %H:%M:%S")


def _ym(d=None):
    return (d or _now()).strftime("%Y-%m")


def next_month_first(d=None):
    """오늘 기준 다음 달 1일('YYYY-MM-DD') — next_charge 계산. 매달 1일 자동 청구 규칙 그대로."""
    d = d or _now()
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return "%04d-%02d-01" % (y, m)


def _default_customer_key(tenant):
    return "wellperion-%s" % tenant


# ── 토스 API 왕복 ──────────────────────────────────────────────────────────────────────────────
def _toss_headers():
    key = os.environ.get("TOSS_SECRET_KEY", "")
    if not key:
        raise RuntimeError("TOSS_SECRET_KEY 없음 — /srv/erp/api.env")
    b64 = base64.b64encode((key + ":").encode("utf-8")).decode("ascii")
    return {"Authorization": "Basic %s" % b64, "Content-Type": "application/json"}


def _toss_post(path, body):
    """토스 결제 서버로 POST. 실패하면 TossError(code, message) — 원문 body(카드정보 없음)는 예외에 안 싣는다."""
    req = urllib.request.Request(TOSS_BASE + path, data=json.dumps(body).encode("utf-8"),
                                 method="POST", headers=_toss_headers())
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8"))
        except Exception:
            detail = {}
        raise TossError(detail.get("code", "HTTP_%s" % e.code), detail.get("message", str(e)))
    except urllib.error.URLError as e:
        raise TossError("NETWORK_ERROR", str(e.reason))


def issue_billing_key(auth_key, customer_key):
    """POST /v1/billing/authorizations/issue — authKey(카드 등록 창 리다이렉트로 받음) → billingKey 교환."""
    return _toss_post("/v1/billing/authorizations/issue", {"authKey": auth_key, "customerKey": customer_key})


def charge_billing_key(billing_key, customer_key, amount, order_id, order_name):
    """POST /v1/billing/{billingKey} — 빌링키로 실제 청구 1건."""
    return _toss_post("/v1/billing/%s" % billing_key, {
        "customerKey": customer_key, "amount": amount, "orderId": order_id, "orderName": order_name,
    })


# ── DB ─────────────────────────────────────────────────────────────────────────────────────────
def _sub_row(r):
    return {"tenant": r["tenant"], "plan": r["plan"], "amount": r["amount"], "customer_key": r["customer_key"],
            "has_billing_key": bool(r["has_billing_key"]), "next_charge": r["next_charge"], "status": r["status"],
            "updated_at": r["updated_at"]}


def get_subscription(conn, tenant):
    r = conn.execute("SELECT * FROM billing_subscriptions WHERE tenant_id=%s AND tenant=%s",
                     (db.TENANT, tenant)).fetchone()
    return _sub_row(r) if r else None


def _save_billing_key(conn, tenant, billing_key):
    conn.execute(
        "INSERT INTO billing_secrets (tenant_id, tenant, billing_key, updated_at) VALUES (%s,%s,%s,%s)"
        " ON CONFLICT (tenant_id, tenant) DO UPDATE SET billing_key=EXCLUDED.billing_key, updated_at=EXCLUDED.updated_at",
        (db.TENANT, tenant, billing_key, _now_str()))


def _load_billing_key(conn, tenant):
    r = conn.execute("SELECT billing_key FROM billing_secrets WHERE tenant_id=%s AND tenant=%s",
                     (db.TENANT, tenant)).fetchone()
    return r["billing_key"] if r else None


def _upsert_subscription(conn, tenant, plan, amount, customer_key, next_charge, status):
    now = _now_str()
    conn.execute(
        "INSERT INTO billing_subscriptions (tenant_id, tenant, plan, amount, customer_key, has_billing_key,"
        " next_charge, status, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,TRUE,%s,%s,%s,%s)"
        " ON CONFLICT (tenant_id, tenant) DO UPDATE SET plan=EXCLUDED.plan, amount=EXCLUDED.amount,"
        " customer_key=EXCLUDED.customer_key, has_billing_key=TRUE, next_charge=EXCLUDED.next_charge,"
        " status=EXCLUDED.status, updated_at=EXCLUDED.updated_at",
        (db.TENANT, tenant, plan, amount, customer_key, next_charge, status, now, now))


def _set_next_charge(conn, tenant, next_charge):
    conn.execute("UPDATE billing_subscriptions SET next_charge=%s, updated_at=%s WHERE tenant_id=%s AND tenant=%s",
                 (next_charge, _now_str(), db.TENANT, tenant))


def _charge_row(conn, tenant, ym):
    return conn.execute("SELECT * FROM billing_charges WHERE tenant_id=%s AND tenant=%s AND ym=%s",
                        (db.TENANT, tenant, ym)).fetchone()


def _upsert_charge(conn, tenant, ym, **fields):
    row = _charge_row(conn, tenant, ym)
    if row is None:
        cols = ["tenant_id", "tenant", "ym"] + list(fields.keys())
        vals = [db.TENANT, tenant, ym] + list(fields.values())
        ph = ",".join(["%s"] * len(vals))
        conn.execute("INSERT INTO billing_charges (%s) VALUES (%s)" % (",".join(cols), ph), vals)
    else:
        sets = ",".join("%s=%%s" % k for k in fields)
        conn.execute("UPDATE billing_charges SET %s WHERE tenant_id=%%s AND tenant=%%s AND ym=%%s" % sets,
                     list(fields.values()) + [db.TENANT, tenant, ym])


def list_charges(conn, tenant, limit=6):
    rows = conn.execute(
        "SELECT ym, order_id, amount, status, toss_payment_key, error, tried_at, retry_at FROM billing_charges"
        " WHERE tenant_id=%s AND tenant=%s ORDER BY ym DESC LIMIT %s", (db.TENANT, tenant, limit)).fetchall()
    return [dict(r) for r in rows]


# ── 알림(지금은 dry-run 로그만 — 실발신 통로는 후속) ──────────────────────────────────────────────
def notify_dry_run(tenant, ok, detail):
    print("[billing][dry-run 알림] %s %s %s — %s" % (_now_str(), tenant, "성공" if ok else "실패", detail), flush=True)


# ── 청구 1회 (cron·수동 트리거 공용) ───────────────────────────────────────────────────────────────
def charge_one(tenant):
    """이번 달(ym) 청구를 시도. 이미 이번 달에 paid 면 건너뛴다(idempotency = PK 자체).
    실패했다가 재시도(status='retry')인 회차가 또 실패하면 이번 달은 'failed' 로 끝난다(1회 재시도 한도)."""
    conn = db.connect()
    try:
        sub = get_subscription(conn, tenant)
        if not sub or not sub["has_billing_key"]:
            return {"ok": False, "tenant": tenant, "error": "구독·빌링키 없음"}
        ym = _ym()
        existing = _charge_row(conn, tenant, ym)
        if existing and existing["status"] == "paid":
            return {"ok": True, "tenant": tenant, "ym": ym, "skipped": "already-paid"}
        if existing and existing["status"] == "failed":
            return {"ok": False, "tenant": tenant, "ym": ym, "skipped": "already-failed-terminal"}
        is_retry = bool(existing and existing["status"] == "retry")
        if is_retry and existing["retry_at"] and existing["retry_at"] > _now().strftime("%Y-%m-%d"):
            # next_charge 는 성공해야만 다음 달로 넘어가므로 due_new(next_charge<=오늘)가 매일 이 tenant 를
            # 다시 집는다 — retry_at 이 아직 안 왔으면 여기서 멈춘다(3일 뒤 "딱 한 번" 재시도를 지킨다).
            return {"ok": True, "tenant": tenant, "ym": ym, "skipped": "retry-not-due", "retry_at": existing["retry_at"]}
        billing_key = _load_billing_key(conn, tenant)
        if not billing_key:
            return {"ok": False, "tenant": tenant, "error": "빌링키 원문 없음(billing_secrets)"}
        order_id = "BILL-%s-%s-%s" % (tenant, ym.replace("-", ""), secrets.token_hex(3))
        order_name = "웰페리온랩스 구독 %s(%s)" % (sub["plan"], ym)
        try:
            resp = charge_billing_key(billing_key, sub["customer_key"], sub["amount"], order_id, order_name)
            with conn:
                _upsert_charge(conn, tenant, ym, order_id=order_id, amount=sub["amount"], status="paid",
                               toss_payment_key=resp.get("paymentKey", ""), error="", tried_at=_now_str(), retry_at="")
                _set_next_charge(conn, tenant, next_month_first())
            notify_dry_run(tenant, True, "%s원 청구 성공(%s)" % (sub["amount"], ym))
            return {"ok": True, "tenant": tenant, "ym": ym, "amount": sub["amount"]}
        except TossError as e:
            status = "failed" if is_retry else "retry"
            retry_at = "" if is_retry else (_now() + dt.timedelta(days=3)).strftime("%Y-%m-%d")
            with conn:
                _upsert_charge(conn, tenant, ym, order_id=order_id, amount=sub["amount"], status=status,
                               toss_payment_key="", error=str(e)[:300], tried_at=_now_str(), retry_at=retry_at)
            notify_dry_run(tenant, False, "청구 실패(%s) — %s" % (ym, e))
            return {"ok": False, "tenant": tenant, "ym": ym, "status": status, "error": str(e)[:300]}
    finally:
        conn.close()


def run_due_charges(today=None):
    """cron 진입점 — next_charge 도래 건 + retry_at 도래 건을 전부 청구. billing_charge.py 가 이걸 부른다."""
    today = today or _now().strftime("%Y-%m-%d")
    conn = db.connect(readonly=True)
    try:
        due_new = conn.execute(
            "SELECT tenant FROM billing_subscriptions WHERE tenant_id=%s AND status='active'"
            " AND has_billing_key AND next_charge<=%s", (db.TENANT, today)).fetchall()
        due_retry = conn.execute(
            "SELECT tenant FROM billing_charges WHERE tenant_id=%s AND status='retry' AND retry_at<=%s",
            (db.TENANT, today)).fetchall()
    finally:
        conn.close()
    tenants = sorted({r["tenant"] for r in due_new} | {r["tenant"] for r in due_retry})
    return [charge_one(t) for t in tenants]


# ── 라우트 ─────────────────────────────────────────────────────────────────────────────────────
def _billing_key_sync(tenant, auth_key, customer_key, plan):
    conn = db.connect()
    try:
        resp = issue_billing_key(auth_key, customer_key)
        billing_key = resp.get("billingKey")
        if not billing_key:
            raise TossError("NO_BILLING_KEY", "토스 응답에 billingKey 없음")
        amount = PLAN_AMOUNTS[plan]
        next_charge = next_month_first()
        with conn:
            _save_billing_key(conn, tenant, billing_key)
            _upsert_subscription(conn, tenant, plan, amount, customer_key, next_charge, "active")
        print("[billing] %s 빌링키 등록 완료 · plan=%s" % (tenant, plan), flush=True)   # 빌링키 원문은 절대 안 찍는다
        return {"ok": True, "tenant": tenant, "plan": plan, "amount": amount, "next_charge": next_charge}
    finally:
        conn.close()


@router.post("/{tenant}/billing-key")
async def register_billing_key(tenant: str, request: Request):
    if _user(request) not in _admins():
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    if tenant not in PARTNER_TENANTS:
        return JSONResponse({"ok": False, "error": "알 수 없는 tenant"}, status_code=400)
    body = await request.json()
    auth_key = str(body.get("authKey") or "")
    plan = str(body.get("plan") or "")
    customer_key = str(body.get("customerKey") or "") or _default_customer_key(tenant)
    if not auth_key or plan not in PLAN_AMOUNTS:
        return JSONResponse({"ok": False, "error": "authKey·plan(start|growth|ops) 필요"}, status_code=400)
    try:
        result = await run_in_threadpool(_billing_key_sync, tenant, auth_key, customer_key, plan)
    except TossError as e:
        print("[billing] %s 빌링키 등록 실패(코드 %s)" % (tenant, e.code), flush=True)
        return JSONResponse({"ok": False, "error": "toss-error", "code": e.code, "message": e.message}, status_code=502)
    except RuntimeError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    return result


@router.get("/{tenant}")
def billing_status(tenant: str, request: Request):
    if _user(request) not in _admins():
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    conn = db.connect(readonly=True)
    try:
        sub = get_subscription(conn, tenant)
        charges = list_charges(conn, tenant) if sub else []
    finally:
        conn.close()
    if not sub:
        return {"ok": True, "tenant": tenant, "subscribed": False}
    return {"ok": True, "tenant": tenant, "subscribed": True, **sub, "charges": charges}


@router.post("/{tenant}/charge")
async def manual_charge(tenant: str, request: Request):
    if _user(request) not in _admins():
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    if tenant not in PARTNER_TENANTS:
        return JSONResponse({"ok": False, "error": "알 수 없는 tenant"}, status_code=400)
    return await run_in_threadpool(charge_one, tenant)


def selftest():
    """토스 호출은 monkeypatch(실제 네트워크 0) · DB 는 진짜 접속(tenant='selftest' · api_proc.py 와 같은 관례).
    ERP_DB_URL 이 없는 자리(개발 PC)에서는 DB 파트를 건너뛰고 순수 로직만 잰다."""
    global TOSS_BASE
    assert next_month_first(dt.datetime(2026, 9, 16, tzinfo=KST)) == "2026-10-01"
    assert next_month_first(dt.datetime(2026, 12, 20, tzinfo=KST)) == "2027-01-01"
    assert PLAN_AMOUNTS["start"] == 190000 and PLAN_AMOUNTS["growth"] == 390000

    calls = []

    def fake_issue(auth_key, customer_key):
        calls.append(("issue", auth_key, customer_key))
        return {"billingKey": "billing_test_key_should_never_be_logged", "customerKey": customer_key}

    def fake_charge_ok(billing_key, customer_key, amount, order_id, order_name):
        calls.append(("charge", order_id, amount))
        return {"paymentKey": "pay_test_123", "status": "DONE"}

    def fake_charge_fail(billing_key, customer_key, amount, order_id, order_name):
        calls.append(("charge", order_id, amount))
        raise TossError("REJECT_CARD_COMPANY", "카드사 거절(테스트)")

    global issue_billing_key, charge_billing_key
    real_issue, real_charge = issue_billing_key, charge_billing_key
    try:
        issue_billing_key = fake_issue
        if not os.environ.get("ERP_DB_URL") and not os.path.exists(os.environ.get("ERP_DB_ENV", "/srv/erp/db.env")):
            print("selftest: DB 없음(개발 PC) — 순수 로직만 확인, DB 파트는 서버에서 재실행", flush=True)
            print("selftest ok (부분)")
            return
        tenant = "selftest"
        conn = db.connect()
        with conn:
            conn.execute("DELETE FROM billing_charges WHERE tenant_id=%s AND tenant=%s", (db.TENANT, tenant))
            conn.execute("DELETE FROM billing_subscriptions WHERE tenant_id=%s AND tenant=%s", (db.TENANT, tenant))
            conn.execute("DELETE FROM billing_secrets WHERE tenant_id=%s AND tenant=%s", (db.TENANT, tenant))
        conn.close()
        try:
            r = _billing_key_sync(tenant, "authkey-abc", _default_customer_key(tenant), "start")
            assert r["ok"] and r["amount"] == 190000

            charge_billing_key = fake_charge_ok
            r1 = charge_one(tenant)
            assert r1["ok"] and r1.get("skipped") is None
            n_calls_after_first = len(calls)
            r2 = charge_one(tenant)  # 같은 달 두 번째 — idempotency
            assert r2["ok"] and r2.get("skipped") == "already-paid"
            assert len(calls) == n_calls_after_first, "이미 청구된 달인데 토스를 또 쳤다"

            conn = db.connect()
            with conn:
                conn.execute("DELETE FROM billing_charges WHERE tenant_id=%s AND tenant=%s", (db.TENANT, tenant))
            conn.close()
            charge_billing_key = fake_charge_fail
            r3 = charge_one(tenant)
            assert r3["status"] == "retry"
            conn = db.connect(readonly=True)
            row = conn.execute("SELECT retry_at FROM billing_charges WHERE tenant_id=%s AND tenant=%s AND ym=%s",
                               (db.TENANT, tenant, _ym())).fetchone()
            conn.close()
            expect_retry = (_now() + dt.timedelta(days=3)).strftime("%Y-%m-%d")
            assert row["retry_at"] == expect_retry, (row["retry_at"], expect_retry)
            r3b = charge_one(tenant)  # retry_at 이 아직 안 왔다 — 매일 도는 due_new 가 조르지 못하게 멈춘다
            assert r3b.get("skipped") == "retry-not-due"
            assert len(calls) == n_calls_after_first + 1, "retry_at 전인데 토스를 또 쳤다"
            conn = db.connect()   # "3일 뒤"를 흉내 — retry_at 을 과거로 당긴다(실제 대기 없이 재시도 경로만 확인)
            with conn:
                conn.execute("UPDATE billing_charges SET retry_at=%s WHERE tenant_id=%s AND tenant=%s AND ym=%s",
                             ("2000-01-01", db.TENANT, tenant, _ym()))
            conn.close()
            r4 = charge_one(tenant)  # 재시도 도래 뒤에도 또 실패 — 이번 달 종결
            assert r4["status"] == "failed"
            r5 = charge_one(tenant)  # 종결 뒤 또 부르면 건너뛴다(재시도 한도 = 1회)
            assert r5.get("skipped") == "already-failed-terminal"

            dump = json.dumps(calls) + json.dumps([r, r1, r2, r3, r3b, r4, r5])
            assert "billing_test_key_should_never_be_logged" not in dump, "빌링키 원문이 응답/로그에 샜다"
        finally:
            conn = db.connect()
            with conn:
                conn.execute("DELETE FROM billing_charges WHERE tenant_id=%s AND tenant=%s", (db.TENANT, tenant))
                conn.execute("DELETE FROM billing_subscriptions WHERE tenant_id=%s AND tenant=%s", (db.TENANT, tenant))
                conn.execute("DELETE FROM billing_secrets WHERE tenant_id=%s AND tenant=%s", (db.TENANT, tenant))
            conn.close()
    finally:
        issue_billing_key, charge_billing_key = real_issue, real_charge
    print("selftest ok")


if __name__ == "__main__":
    selftest()
