"""토큰 수집기 열쇠 — 로그인한 회사 계정에게만 보여 준다(채팅에 안 남기려고 · 나우열M 쪽 요청 2026-09-14 15:27).

경로 = GET /api/token_key  (nginx /api/ 는 auth_request 를 지나므로 X-Erp-User 가 로그인 이메일이다 —
/api/token_usage/ 처럼 열쇠 헤더로 여는 무로그인 통로가 아니다). 허용 = KEY_READERS 세 계정뿐.
열쇠 값 자체는 api.env ERP_TOKEN_PUSH_KEY 한 곳(api_token_usage.py 와 같은 값) — 여기 복사하지 않는다.
쓰는 법: 그 계정으로 ERP 에 로그인한 브라우저에서 https://erp.wellperion.com/api/token_key 를 열어
한 줄을 복사 → %USERPROFILE%\\.claude\\token_push.key 로 저장.
"""
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/api/token_key")
KEY_READERS = ("cao@wellperion.com", "info@wellperion.com", "lessons@wellperion.com")


def reader_ok(email):
    return (email or "").strip().lower() in KEY_READERS


@router.get("", response_class=PlainTextResponse)
def token_key(request: Request):
    if not reader_ok(request.headers.get("x-erp-user", "")):
        raise HTTPException(403, "이 계정은 열쇠를 볼 수 없습니다")
    key = os.environ.get("ERP_TOKEN_PUSH_KEY", "")
    if not key:
        raise HTTPException(503, "서버에 열쇠가 없습니다")
    return key


def selftest():
    assert reader_ok("info@wellperion.com") and reader_ok(" CAO@wellperion.com ")
    assert not reader_ok("") and not reader_ok("someone@gmail.com")
    print("selftest ok")


if __name__ == "__main__":
    selftest()
