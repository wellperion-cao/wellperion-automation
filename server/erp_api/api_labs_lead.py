# -*- coding: utf-8 -*-
"""AX 랩스 홈페이지 문의 칸 서버 문 — 배 12852 · GM 2026-09-19 지시(시모 설계 note).

POST /api/labs/lead — 무인증(공개 홈페이지 폼, /labs/ 안 iframe). 로그인·GAS 없이 서버가 직접 받는다.
  body {center, kind, phone, pain, agree, hp}
  - hp(허니팟) 값이 있으면 저장·알림 없이 {ok:true} 만 돌려준다(봇 트래픽 — 조용히 버린다).
  - agree(개인정보 수집 동의) 는 true 여야 한다.
  - center·phone 은 필수. 길이 상한: center 60·kind 20·phone 30·pain 300 — 넘으면 400.
  - IP 당 분당 3회·하루 20회(_rate_ok) — nginx 존과 별개로 앱단에서 한 번 더 거른다.
  - 저장 = LEADS_PATH(웹루트·저장소 밖) 에 한 줄 append, chmod 600. 시트·저장소엔 아무것도 안 남는다.
  - 저장 성공 뒤 텔레그램 즉시 알림(namuki_report_bot · TG_BOT_TOKEN/TG_CHAT_ID — erp_auth.tell_gm·
    sync_members._tell_gm·api_reception.notify 와 같은 발신 방식). 알림 실패해도 접수 자체는 성공이다.
  - 본문(개인정보)은 어떤 로그에도 print 하지 않는다.
  - CORS = erp.wellperion.com 한 곳만(폼이 그 도메인 /labs/ 안에서 같은 오리진으로 부른다).
  app.py 가 같은 폴더의 api_*.py 를 자동 등록한다 — app.py 본문은 건드리지 않는다.
  nginx 예외(로그인 없이 통과)는 서버 conf 에 location = /api/labs/lead 한 줄을 reception-public.conf 와
  같은 방식으로 추가해야 한다(이 파일만으로는 auth_request 를 안 벗어난다).
자체점검: python3 api_labs_lead.py --selftest (DB·네트워크 없음 — 허니팟·길이·동의·요청빈도 판정만)
"""
import json
import os
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

router = APIRouter(prefix="/api/labs")
KST = timezone(timedelta(hours=9))

LEADS_PATH = os.environ.get("ERP_LABS_LEADS_PATH", "/srv/erp/labs_leads.jsonl")
CORS_ORIGIN = os.environ.get("LABS_LEAD_CORS_ORIGIN", "https://erp.wellperion.com")
CORS = {"Access-Control-Allow-Origin": CORS_ORIGIN, "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"}

_LIMITS = {"center": 60, "kind": 20, "phone": 30, "pain": 300}
RATE_PER_MIN = 3
RATE_PER_DAY = 20

_RATE_LOCK = threading.Lock()
_RATE_MINUTE = {}   # (ip, minute_bucket) -> count
_RATE_DAY = {}       # (ip, day_str) -> count


def _kst_now() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def _client_ip(request: Request) -> str:
    """nginx 가 X-Forwarded-For 를 $remote_addr 로 덮어 보낸다(api_chat.py·api_hr.py 와 같은 값)."""
    fwd = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return fwd or (request.client.host if request.client else "")


def _rate_ok(ip: str) -> bool:
    """IP 당 분당 RATE_PER_MIN·하루 RATE_PER_DAY 상한. ponytail: 워커 프로세스별 메모리 전역이라
    워커 2개(erp-api) = 실효 최대 분당 6·하루 40건 — 넘어야 할 이유가 생기면 파일·redis 공유 카운터로 승격."""
    if not ip:
        return True
    now = time.time()
    minute_bucket = int(now // 60)
    day = _kst_now()[:10]
    with _RATE_LOCK:
        for k in [k for k in _RATE_MINUTE if k[1] != minute_bucket]:
            _RATE_MINUTE.pop(k, None)
        for k in [k for k in _RATE_DAY if k[1] != day]:
            _RATE_DAY.pop(k, None)
        mkey, dkey = (ip, minute_bucket), (ip, day)
        _RATE_MINUTE[mkey] = _RATE_MINUTE.get(mkey, 0) + 1
        _RATE_DAY[dkey] = _RATE_DAY.get(dkey, 0) + 1
        return _RATE_MINUTE[mkey] <= RATE_PER_MIN and _RATE_DAY[dkey] <= RATE_PER_DAY


def _append_lead(data: dict) -> None:
    """LEADS_PATH 에 한 줄 append — chmod 600(사람 손 안 타는 서버 파일 · 웹루트·저장소 밖)."""
    line = json.dumps(data, ensure_ascii=False) + "\n"
    fd = os.open(LEADS_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(LEADS_PATH, 0o600)   # 기존 파일이 다른 권한으로 있었더라도 강제


def _notify_gm(center: str, kind: str, phone: str, pain: str) -> bool:
    """텔레그램 즉시 알림 — 서버가 이미 쓰는 발신 방식(api_reception.notify 와 같은 패턴) 그대로,
    새 발신기를 만들지 않는다. 실패해도 접수는 이미 저장됐으므로 응답에 영향 없다."""
    token, chat = os.environ.get("TG_BOT_TOKEN"), os.environ.get("TG_CHAT_ID")
    if not token or not chat:
        return False
    text = ("🆕 AX 랩스 문의\n센터: %s\n업종: %s\n연락처: %s\n%s"
            % (center, kind or "-", phone, pain[:100] if pain else "-"))
    try:
        req = urllib.request.Request(
            "https://api.telegram.org/bot%s/sendMessage" % token,
            data=json.dumps({"chat_id": chat, "text": text}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=8)
        return True
    except Exception:
        return False


def _process(body: bytes, ip: str):
    """본문 판정 + 저장 + 알림(순수 입출력 경계만 얇게 — 나머지는 테스트 가능한 순수 로직)."""
    try:
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError
    except Exception:
        return {"ok": False, "error": "bad-payload"}, 400

    if str(payload.get("hp") or "").strip():
        return {"ok": True}, 200   # 허니팟 — 저장·알림 없이 조용히 버린다

    if not _rate_ok(ip):
        return {"ok": False, "error": "요청이 많습니다. 잠시 후 다시 시도해 주세요."}, 429

    if payload.get("agree") is not True:
        return {"ok": False, "error": "개인정보 수집에 동의해 주세요."}, 400

    fields = {k: str(payload.get(k) or "").strip() for k in ("center", "kind", "phone", "pain")}
    if not fields["center"] or not fields["phone"]:
        return {"ok": False, "error": "센터명과 연락처는 필수입니다."}, 400
    for k, limit in _LIMITS.items():
        if len(fields[k]) > limit:
            return {"ok": False, "error": "입력값이 너무 깁니다: %s" % k}, 400

    now = _kst_now()
    _append_lead({"ts": now, "ip": ip, **fields})
    _notify_gm(fields["center"], fields["kind"], fields["phone"], fields["pain"])
    return {"ok": True}, 200


@router.options("/lead")
def lead_preflight():
    return Response(status_code=204, headers=CORS)


@router.post("/lead")
async def lead(request: Request):
    """DB 는 없지만 파일 append·텔레그램이 동기라 스레드풀에서 돈다(이벤트루프 차단 방지 — api_intake.py:147
    과 같은 패턴)."""
    body = await request.body()
    ip = _client_ip(request)
    data, code = await run_in_threadpool(_process, body, ip)
    return JSONResponse(data, status_code=code, headers=CORS)


def _selftest():
    global LEADS_PATH
    import tempfile
    real_path = LEADS_PATH
    LEADS_PATH = os.path.join(tempfile.mkdtemp(), "labs_leads.jsonl")
    try:
        good = json.dumps({"center": "테스트센터", "kind": "요가", "phone": "010-0000-0000",
                            "pain": "체험 문의", "agree": True}).encode("utf-8")

        # 허니팟 — ok 지만 저장 안 됨
        hp = json.dumps({"center": "봇", "phone": "010", "agree": True, "hp": "spammy"}).encode("utf-8")
        data, code = _process(hp, "9.9.9.1")
        assert data == {"ok": True} and code == 200
        assert not os.path.exists(LEADS_PATH), "허니팟은 파일에 안 남아야 한다"

        # 정상 접수 — 저장됨, 개인정보(전화번호)는 안 실린 로그가 안 남는지는 별도 print 자체가 없음으로 보증
        data, code = _process(good, "9.9.9.2")
        assert data == {"ok": True} and code == 200
        with open(LEADS_PATH, encoding="utf-8") as f:
            lines = [json.loads(ln) for ln in f if ln.strip()]
        assert len(lines) == 1 and lines[0]["center"] == "테스트센터" and lines[0]["phone"] == "010-0000-0000"

        # agree 누락/거짓
        bad_agree = json.dumps({"center": "c", "phone": "010", "agree": False}).encode("utf-8")
        data, code = _process(bad_agree, "9.9.9.3")
        assert code == 400 and data["ok"] is False

        # 필수값 누락
        no_phone = json.dumps({"center": "c", "agree": True}).encode("utf-8")
        data, code = _process(no_phone, "9.9.9.4")
        assert code == 400 and data["ok"] is False

        # 길이 초과
        too_long = json.dumps({"center": "c" * 61, "phone": "010", "agree": True}).encode("utf-8")
        data, code = _process(too_long, "9.9.9.5")
        assert code == 400 and data["ok"] is False
        too_long_pain = json.dumps({"center": "c", "phone": "010", "agree": True, "pain": "p" * 301}).encode("utf-8")
        data, code = _process(too_long_pain, "9.9.9.6")
        assert code == 400 and data["ok"] is False

        # 요청 빈도 상한 — 분당 3회, 4번째부터 429(전용 IP)
        ip = "9.9.9.7"
        codes = [_process(good, ip)[1] for _ in range(4)]
        assert codes == [200, 200, 200, 429], codes

        # bad json
        data, code = _process(b"not-json", "9.9.9.8")
        assert code == 400 and data["ok"] is False
    finally:
        LEADS_PATH = real_path

    print("api_labs_lead selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
