# -*- coding: utf-8 -*-
"""매출보고 캡처용 erp 세션 토큰 — SSH 로 서버에서 즉석 발급, 새 HTTP 문 없음(배 12818 연장 · 시토).

mint(minutes=10)  cao@wellperion.com(tenant wellperion) 앞 HS256 세션 토큰을 서버 SSH 로 만들어 반환한다.
                  서버가 이미 내는 것과 같은 클레임(uid·email·role·exp·ver) — server/erp_auth/app.py::issue() 참고.
                  auth.env(ERP_JWT_SECRET)·db.env(ERP_DB_URL) 는 서버 안에서만 읽는다 — 이 파일·호출자 쪽에는
                  비밀값이 한 글자도 안 온다(토큰 자체도 로그·파일·예외 메시지에 안 남긴다 — 메모리로만 오간다).

쓰는 곳: 09:00 매출보고 캡처(시포 몫 scripts/sales_report_server_send.py)가 이 mint() 로 받은 토큰을
        erp_session 쿠키(domain=erp.wellperion.com)로 넣어 매출회원현황보고.html 을 erp 주소에서 직접
        찍는다 — github.io 공개 사본(GAS member_inquiry_list 무인증 폴백)을 더는 거치지 않는다.
"""
import os
import subprocess
import time
import types

HOST = "ec2-user@15.164.151.105"
KEY = os.path.expanduser("~/.aws/wellperion-sito.pem")
SSH = ["ssh", "-i", KEY, "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10", HOST]
MAX_MINUTES = 15
EMAIL = "cao@wellperion.com"

# 서버 안에서 도는 원격 스크립트 — 커맨드라인이 아니라 stdin 으로 흘린다(따옴표·이스케이프 사고 회피).
# db.py 는 그대로 재사용(ERP_DB_URL 자동 탐색 — common/db.py::_url 참고) · auth.env 만 여기서 한 줄 직접 읽는다
# (그 파일을 읽는 공용 helper 가 아직 없어서다).
_REMOTE_PY = r"""
import sys, time
sys.path.insert(0, "/srv/erp/common")
import db
import jwt

minutes = int(sys.argv[1])
email = sys.argv[2]

secret = None
with open("/srv/erp/auth.env", encoding="utf-8") as f:
    for line in f:
        if line.startswith("ERP_JWT_SECRET="):
            secret = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
if not secret:
    print("ERR:no_secret", file=sys.stderr)
    sys.exit(1)

conn = db.connect()
row = conn.execute(
    "SELECT id, email, role, session_ver FROM users WHERE tenant_id=%s AND email=%s AND status='active'",
    (db.TENANT, email),
).fetchone()
if not row:
    print("ERR:no_user", file=sys.stderr)
    sys.exit(1)

exp = int(time.time()) + minutes * 60
claims = {"uid": row["id"], "email": row["email"], "role": row["role"], "exp": exp,
          "ver": int(row["session_ver"] or 0)}
print(jwt.encode(claims, secret, algorithm="HS256"))
"""


def mint(minutes: int = 10):
    """(token, None) 성공 또는 (None, 사유) 실패. minutes 는 최대 15분으로 자른다.
    토큰은 이 반환값에만 담긴다 — 여기서도 호출자 쪽에서도 파일·로그·print 에 남기면 안 된다."""
    m = min(max(1, int(minutes)), MAX_MINUTES)
    try:
        p = subprocess.run(
            SSH + ["python3", "-", str(m), EMAIL],
            input=_REMOTE_PY, capture_output=True, text=True, timeout=20,
        )
    except Exception as e:
        return None, "ssh_fail:%s" % type(e).__name__   # 인자만 쓰는 예외라 비밀값이 섞일 자리가 없다
    if p.returncode != 0 or not p.stdout.strip():
        last = (p.stderr or "").strip().splitlines()
        return None, "remote_fail:%s" % (last[-1][:60] if last else "empty")
    tok = p.stdout.strip()
    if tok.count(".") != 2:   # JWT 형식만 확인 — 내용을 찍지 않는다
        return None, "bad_token_shape"
    return tok, None


if __name__ == "__main__":
    import sys as _sys

    if "--selftest" in _sys.argv:
        # 네트워크 0 — ssh 호출부(subprocess.run)만 흉내낸다.
        calls = []

        def _ok(cmd, input=None, capture_output=None, text=None, timeout=None):
            calls.append(cmd)
            return types.SimpleNamespace(returncode=0, stdout="aa.bb.cc\n", stderr="")

        def _fail(cmd, input=None, capture_output=None, text=None, timeout=None):
            return types.SimpleNamespace(returncode=1, stdout="", stderr="Traceback\nERR:no_user\n")

        _orig = subprocess.run
        subprocess.run = _ok
        try:
            tok, err = mint(9999)                              # 상한(15분) 확인
            assert tok == "aa.bb.cc" and err is None, (tok, err)
            assert calls[0][-2:] == [str(MAX_MINUTES), EMAIL], calls[0]
            tok, err = mint(5)
            assert tok == "aa.bb.cc" and calls[1][-2:] == ["5", EMAIL]

            subprocess.run = _fail
            tok, err = mint(5)
            assert tok is None and "no_user" in err, err
        finally:
            subprocess.run = _orig
        print("erp_capture_token 자체점검 통과")
    elif "--live" in _sys.argv:
        tok, err = mint(10)
        if not tok:
            print("실패:", err)
            _sys.exit(1)
        import urllib.error
        import urllib.request
        req = urllib.request.Request("https://erp.wellperion.com/auth/me")
        req.add_header("Cookie", "erp_session=%s" % tok)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                print("auth/me =", resp.status)
        except urllib.error.HTTPError as e:
            print("auth/me =", e.code)
        # 토큰 문자열은 여기서 끝 — stdout 에 안 찍는다
    else:
        print("사용법: python erp_capture_token.py --selftest | --live")
