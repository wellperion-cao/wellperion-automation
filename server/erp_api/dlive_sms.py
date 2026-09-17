# -*- coding: utf-8 -*-
"""딜라이브 SMS/LMS 발송 모듈 (배 2714 · 2026-09-17 시토 · GM 지시 문자 자동발송 1단계 · CTO-2026-09-17-문자자동발송-설계.md §6).

정본 = 이 파일 하나. 화면마다 발신기를 만들지 않는다(약속 L21) — api_sms.py 는 이 위의 얇은 라우터뿐.
계정 6키(DLIVE_USER_ID·DLIVE_PASSWORD·DLIVE_SENDER_TEL·DLIVE_HOST·DLIVE_PORT·DLIVE_VERIFY_SSL)는
서버 /srv/erp/api.env 에만 있다 — 이 파일·로그·문서에 값을 적지 않는다(os.environ 으로만 읽는다).

킬스위치 SMS_ENABLED — "1" 이 아니면 실제 POST 없이 로그만 남긴다(status="dry"). 기본값 0(발효 전).
문구 정본 = SMS_TEMPLATES_PATH(기본 /srv/erp/sms_templates.json) · 파일이 없으면 이 폴더의
sms_templates.seed.json 으로 만든다(있으면 절대 덮지 않는다).
발송 로그 = SMS_LOG_PATH(기본 /srv/erp/sms_log.jsonl) · 수신번호는 뒷 4자리만, 본문은 문구 id + 변수 키만
남긴다(원문·번호 전체는 로그에 없다).
"""
import datetime as dt
import json
import os
import ssl
import tempfile
import time
import urllib.error
import urllib.request

SEED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sms_templates.seed.json")
KST = dt.timezone(dt.timedelta(hours=9))

_token_cache = {"access_token": None, "expires_at": 0.0}


def _templates_path():
    return os.environ.get("SMS_TEMPLATES_PATH", "/srv/erp/sms_templates.json")


def _log_path():
    return os.environ.get("SMS_LOG_PATH", "/srv/erp/sms_log.jsonl")


def _base_url():
    return "https://%s:%s" % (os.environ["DLIVE_HOST"], os.environ["DLIVE_PORT"])


def _ssl_context():
    if os.environ.get("DLIVE_VERIFY_SSL", "1") == "0":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return ssl.create_default_context()


def _post(path, body, token=None, timeout=15):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(_base_url() + path, data=data, method="POST",
                                  headers={"Content-Type": "application/json; charset=utf-8"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(path, token, timeout=15):
    req = urllib.request.Request(_base_url() + path, method="GET")
    req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r:
        return json.loads(r.read().decode("utf-8"))


def get_token(force=False):
    """메모리 캐시 — 만료 60초 전 재발급. 파일에 안 남긴다."""
    now = time.time()
    if not force and _token_cache["access_token"] and _token_cache["expires_at"] - 60 > now:
        return _token_cache["access_token"]
    resp = _post("/token", {"userId": os.environ["DLIVE_USER_ID"], "password": os.environ["DLIVE_PASSWORD"]})
    if resp.get("errorCode") != "0":
        raise RuntimeError("dlive token 실패 errorCode=%s" % resp.get("errorCode"))
    tok = resp["accessToken"]
    _token_cache["access_token"] = tok
    _token_cache["expires_at"] = now + int(resp.get("expiresIn") or 3600)
    return tok


# ── 문구 저장소 ──────────────────────────────────────────────────────────

def load_templates():
    path = _templates_path()
    if not os.path.exists(path):
        if os.path.exists(SEED_FILE):
            with open(SEED_FILE, encoding="utf-8") as f:
                seed = json.load(f)
            _save_templates(seed)
            return seed
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f) or {}


def _save_templates(data):
    path = _templates_path()
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".smt-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def save_template(template_id, patch, updated_by):
    """name·trigger·body·sample·sndr·state 만 받는다(§3 스키마) — 나머지 칸은 무시."""
    data = load_templates()
    row = data.get(template_id, {"id": template_id})
    for k in ("name", "trigger", "body", "sample", "sndr", "state"):
        if k in patch:
            row[k] = patch[k]
    row["id"] = template_id
    row["updated_by"] = updated_by
    row["updated_at"] = now_kst()
    data[template_id] = row
    _save_templates(data)
    return row


def now_kst():
    return dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M")


def today_str():
    return now_kst()[:10]


# ── 렌더·글자수 판정 ─────────────────────────────────────────────────────

def render(body, variables):
    text = body or ""
    for k, v in (variables or {}).items():
        text = text.replace("{%s}" % k, str(v))
    return text


def msg_type_for(text):
    # ponytail: 딜라이브 규격은 한글/영문 기준이 다르지만(45자/90자) 우리 문구는 한글이 대부분이라
    # 총 문자수 45 를 기준으로만 가른다. 영문 위주 문구가 생기면 그때 바이트 판정으로 정교화.
    return "SMS" if len(text) <= 45 else "LMS"


# ── msgKey (§4) ──────────────────────────────────────────────────────────

def make_msg_key(trigger, ref_id):
    key = "%s-%s-%s" % (trigger or "sms", ref_id or "x", today_str().replace("-", ""))
    return key[:64]


# ── 발송 로그 ────────────────────────────────────────────────────────────

def _mask_tail4(phone):
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if not digits:
        return ""
    return ("*" * max(0, len(digits) - 4)) + digits[-4:]


def _append_log(row):
    path = _log_path()
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_log():
    path = _log_path()
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def recent_log(limit=50):
    return list(reversed(_read_log()))[:limit]


def _is_night():
    return dt.datetime.now(KST).hour >= 21 or dt.datetime.now(KST).hour < 8


# ── 하루 상한·건수 (GM 지시 2026-09-17 10:5x 「갯수 파악·하루 30건 제한」) ──────

def _daily_limit():
    return int(os.environ.get("SMS_DAILY_LIMIT", "30"))


def counts():
    """관리자 화면 맨 위 띠 + /api/admin/sms/counts 원천. dry(킬스위치 꺼짐)는 상한 대상이 아니라 따로 센다."""
    rows = _read_log()
    today, month = today_str(), today_str()[:7]
    today_sent = sum(1 for r in rows if r.get("status") == "sent" and r.get("at", "").startswith(today))
    today_dry = sum(1 for r in rows if r.get("status") == "dry" and r.get("at", "").startswith(today))
    month_sent = sum(1 for r in rows if r.get("status") == "sent" and r.get("at", "").startswith(month))
    by_template_today = {}
    for r in rows:
        if r.get("at", "").startswith(today) and r.get("status") in ("sent", "dry"):
            tid = r.get("template_id", "")
            by_template_today[tid] = by_template_today.get(tid, 0) + 1
    return {"today_sent": today_sent, "today_dry": today_dry, "today_limit": _daily_limit(),
            "month_sent": month_sent, "by_template_today": by_template_today}


# ── 보내기 ───────────────────────────────────────────────────────────────

def send(template_id, rcpt, variables=None, origin_key="", force=False, tag=None, require_active=True):
    """template_id 문구를 rcpt 에 보낸다.
    force=True — 야간(21~08시) 보류를 건너뛴다(관리자 1회 버튼용). 자동 발송은 force 없이 불러 보류시킨다.
    require_active=False — 문구 state 가 '발효' 아니어도 보낸다(관리자 시험 발송 전용).
    같은 msgKey 로 이미 보낸(또는 실패한) 로그가 있으면 다시 보내지 않는다(hold 상태는 아직 안 보낸 것이라 예외).
    하루 실제 발송(status=sent) 이 SMS_DAILY_LIMIT(기본 30)에 닿으면 force 여도 넘지 않고 status=limit 으로 기록만 한다."""
    templates = load_templates()
    tpl = templates.get(template_id)
    if not tpl:
        return {"ok": False, "status": "no_template", "template_id": template_id}
    if require_active and tpl.get("state") != "발효":
        return {"ok": False, "status": "not_active", "template_id": template_id}

    text = render(tpl.get("body", ""), variables)
    mtype = msg_type_for(text)
    # 2026-09-17 시토 실측: 접수 문구 3종(접수·진행·완료)이 같은 trigger("reception")라 같은 접수건은 둘째부터
    #   skip_duplicate 로 막혔다. 중복 키는 「문구 id + 원장 id + 날짜」 — 같은 문구를 같은 건에 하루 두 번만 막는다.
    msg_key = make_msg_key(template_id, origin_key or template_id)

    log_rows = _read_log()
    if any(r.get("msg_key") == msg_key and r.get("status") != "hold" for r in log_rows):
        return {"ok": True, "status": "skip_duplicate", "msg_key": msg_key}

    row = {"at": now_kst(), "template_id": template_id, "trigger": tpl.get("trigger", ""),
           "var_keys": sorted((variables or {}).keys()), "rcpt_tail4": _mask_tail4(rcpt),
           "msg_type": mtype, "msg_key": msg_key, "tag": tag}

    today = today_str()
    sent_today = sum(1 for r in log_rows if r.get("status") == "sent" and r.get("at", "").startswith(today))
    if sent_today >= _daily_limit():
        row["status"] = "limit"
        _append_log(row)
        return {"ok": False, "status": "limit", "msg_key": msg_key}

    if _is_night() and not force:
        row["status"] = "hold"
        _append_log(row)
        return {"ok": True, "status": "hold", "msg_key": msg_key}

    if os.environ.get("SMS_ENABLED") != "1":
        row["status"] = "dry"
        _append_log(row)
        return {"ok": True, "status": "dry", "msg_key": msg_key}

    body = {"msgType": mtype, "msgKey": msg_key, "sndrTel": os.environ["DLIVE_SENDER_TEL"],
            "rcptTel": "".join(ch for ch in str(rcpt) if ch.isdigit()), "message": text}
    if mtype == "LMS":
        body["subject"] = tpl.get("name", "웰페리온")[:30]

    result = _send_with_retry(body)
    row["status"] = "sent" if result.get("errorCode") == "0" else "fail"
    row["error_code"] = result.get("errorCode")
    _append_log(row)
    return {"ok": row["status"] == "sent", "status": row["status"], "msg_key": msg_key,
            "error_code": result.get("errorCode")}


def _send_with_retry(body, retries=1, wait_s=5):
    """실패 1회 재시도(5초 뒤) · 401 이면 토큰 1회 재발급 후 재시도(§6)."""
    last = {"errorCode": "unknown"}
    for attempt in range(retries + 1):
        try:
            token = get_token()
            try:
                return _post("/legacy", body, token=token)
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    token = get_token(force=True)
                    return _post("/legacy", body, token=token)
                raise
        except Exception as e:
            last = {"errorCode": "local_error", "description": str(e)}
            if attempt < retries:
                time.sleep(wait_s)
    return last


def pull_report():
    """/report 를 당겨 로그 행에 결과를 붙인다. 스케줄 연결(주기 실행)은 다음 단계 — 여기는 함수만."""
    token = get_token()
    resp = _get("/report", token)
    results = {r["msgKey"]: r for r in resp.get("results", [])}
    if not results:
        return 0
    rows = _read_log()
    changed = 0
    for r in rows:
        rep = results.get(r.get("msg_key"))
        if rep:
            r["send_status"] = rep.get("sendStatus")
            r["error_code"] = rep.get("errorCode")
            r["delivery_time"] = rep.get("deliveryTime")
            changed += 1
    if changed:
        path = _log_path()
        d = os.path.dirname(path) or "."
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".sml-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    return changed


# ── 자체점검 (네트워크·실제 /srv/erp 접근 없음 — 임시 파일로만) ────────────────

def _selfcheck():
    import shutil
    tmpdir = tempfile.mkdtemp(prefix="smstest-")
    saved_env = {k: os.environ.get(k) for k in
                 ("SMS_TEMPLATES_PATH", "SMS_LOG_PATH", "DLIVE_SENDER_TEL", "SMS_ENABLED")}
    real_is_night = _is_night
    g = globals()
    try:
        os.environ["SMS_TEMPLATES_PATH"] = os.path.join(tmpdir, "templates.json")
        os.environ["SMS_LOG_PATH"] = os.path.join(tmpdir, "log.jsonl")
        os.environ["DLIVE_SENDER_TEL"] = "0212345678"
        os.environ["SMS_ENABLED"] = "0"

        assert render("휴회 {시작}~{종료}", {"시작": "9/20", "종료": "10/19"}) == "휴회 9/20~10/19", "render"
        assert msg_type_for("짧은 문자") == "SMS", "SMS 판정"
        assert msg_type_for("가" * 50) == "LMS", "LMS 판정"

        k1 = make_msg_key("hold", "M00001")
        assert len(k1) <= 64 and k1.startswith("hold-M00001-"), "msgKey 규칙"

        tpls = load_templates()
        assert "hold_confirm" in tpls and tpls["hold_confirm"]["state"] == "GM확정", "씨앗 로딩"
        # 실측(2026-09-17) — 확정 문구 4종은 전부 45자를 넘겨 LMS 로 나간다(브리프 §3 "SMS 45자 이내" 가정은 틀렸다 — 시토 보고).
        for tid in ("rcpt_received", "rcpt_progress", "rcpt_done", "hold_confirm"):
            body = render(tpls[tid]["body"], tpls[tid].get("sample") or {})
            assert msg_type_for(body) == "LMS" and len(body) <= 45 + 100, tid + " 글자수 실측 어긋남"

        r0 = send("hold_confirm", "01011112222", {"시작": "9/20", "종료": "10/19"})
        assert r0["status"] == "not_active", r0

        save_template("hold_confirm", {"state": "발효"}, "selfcheck@local")

        g["_is_night"] = lambda: False
        r1 = send("hold_confirm", "01011112222", {"시작": "9/20", "종료": "10/19"}, origin_key="M00001")
        assert r1["status"] == "dry", r1
        r2 = send("hold_confirm", "01011112222", {"시작": "9/20", "종료": "10/19"}, origin_key="M00001")
        assert r2["status"] == "skip_duplicate", r2

        g["_is_night"] = lambda: True
        r3 = send("hold_confirm", "01011112222", {"시작": "9/21", "종료": "10/20"}, origin_key="M00002")
        assert r3["status"] == "hold", r3
        r4 = send("hold_confirm", "01011112222", {"시작": "9/21", "종료": "10/20"}, origin_key="M00002", force=True)
        assert r4["status"] == "dry", r4

        g["_is_night"] = lambda: False
        r5 = send("rcpt_received", "01033334444", {}, origin_key="test-1", require_active=False, tag="test")
        assert r5["status"] == "dry", r5

        # 하루 상한(GM 2026-09-17 「하루 30건 제한」) — 30건 채운 뒤 31번째는 force 여도 limit.
        for i in range(_daily_limit()):
            _append_log({"at": now_kst(), "template_id": "hold_confirm", "trigger": "hold", "var_keys": [],
                         "rcpt_tail4": "0000", "msg_type": "LMS", "msg_key": "fake-%d" % i, "tag": None, "status": "sent"})
        c = counts()
        assert c["today_sent"] == _daily_limit() and c["today_limit"] == _daily_limit(), c
        r6 = send("hold_confirm", "01099998888", {"시작": "9/22", "종료": "10/21"}, origin_key="M00099", force=True)
        assert r6["status"] == "limit", r6

        rows = recent_log(50)
        assert len(rows) >= 4, "로그 누적"
        assert all(len(r.get("rcpt_tail4", "")) <= 20 and "0101111" not in json.dumps(r) for r in rows), "번호 전체 노출 금지"
        print("selfcheck ok — %d rows" % len(rows))
    finally:
        g["_is_night"] = real_is_night
        shutil.rmtree(tmpdir, ignore_errors=True)
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


if __name__ == "__main__":
    import sys
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        print("usage: python dlive_sms.py --selfcheck")
