# -*- coding: utf-8 -*-
"""인사 백엔드(Apps Script) 읽기 비밀번호를 서버 환경파일에 직접 넣는 통로 (2026-09-15 시토 · GM 「문제없게 진행」).

왜 있나 — 인사 시트 적재(migrate_hr.py)는 HR_GAS_PASSWORD 가 있어야 시트를 읽는데, 그 값은 나우열M 만 안다.
값을 채팅(텔레그램·카톡)으로 주고받으면 방 기록·봇 큐·세션 로그에 남는다(2026-09-15 다이어트캠프 계정 사고와 같은 길).
그래서 값이 사람 손에서 서버 환경파일로 **곧장** 가는 문을 하나 둔다 — 화면도 응답도 로그도 값을 되돌려 주지 않는다.

  GET  /api/hr-secret            로그인한 인사 관리자에게만 입력 화면(HTML 한 장 · 값을 절대 표시하지 않는다)
  GET  /api/hr-secret/status     {"set": true|false} — 값이 서버에 있는지만
  POST /api/hr-secret            {"password": "…"} → 인사 GAS 에 읽기 한 번 시험 → 통하면 api.env 에 저장(원자적 교체·0600)

권한 — 관문(nginx auth_request)이 로그인 이메일을 X-Erp-User 로 넘긴다(위조 불가). 그 이메일이
HR_ADMIN_EMAILS(인사 관리자 · 나우열M) 또는 ERP_PLATFORM_ADMINS(회사 관리자) 에 있을 때만 연다. 둘 다 서버 api.env 값.
저장 — 실행 중인 두 워커의 환경도 같이 바꾼다(os.environ). 적재 스크립트는 별도 프로세스라 파일을 다시 읽는다.
로그 — 본문을 어디에도 적지 않는다. 결과 로그는 「누가 · 통했나 · 직원 행 수」 뿐.
"""
import json
import os
import tempfile
import urllib.request

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter(prefix="/api/hr-secret")

ENV_FILE = os.environ.get("ERP_API_ENV", "/srv/erp/api.env")
KEY = "HR_GAS_PASSWORD"
PROBE_DB = "emp"          # 읽기 시험 = 현재근무자 탭 한 번(행 수만 센다 · 내용은 버린다)
TIMEOUT = 50


def _user(request):
    return (request.headers.get("x-erp-user") or "").strip().lower()


def _admins():
    out = set()
    for k in ("HR_ADMIN_EMAILS", "ERP_PLATFORM_ADMINS"):
        out |= {e.strip().lower() for e in os.environ.get(k, "").split(",") if e.strip()}
    return out


def _probe(pw):
    """인사 GAS 읽기 계약 {db, password} 로 한 번 읽는다 → (ok, 직원 행 수 | 오류 낱말)."""
    url = os.environ.get("HR_GAS_URL", "")
    if not url:
        return False, "no-url"
    body = json.dumps({"db": PROBE_DB, "password": pw}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "text/plain;charset=utf-8"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return False, type(e).__name__
    if not data.get("ok"):
        return False, str(data.get("error") or "unauthorized")[:40]
    return True, len(data.get("results") or [])


def save_env(path, key, value):
    """KEY=값 한 줄을 바꾸거나 붙인다. 임시 파일에 쓰고 0600 으로 바꾼 뒤 원자적으로 교체한다."""
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    done = False
    for i, ln in enumerate(lines):
        if ln.startswith(key + "="):
            lines[i] = key + "=" + value
            done = True
    if not done:
        lines.append(key + "=" + value)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix=".env-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>인사 시트 비밀번호 등록</title>
<style>body{font-family:system-ui,sans-serif;max-width:420px;margin:40px auto;padding:0 16px;line-height:1.6}
input{font-size:18px;padding:8px;width:100%;box-sizing:border-box}button{font-size:16px;padding:8px 16px;margin-top:10px}
#out{margin-top:14px;font-weight:600}</style>
<h2>인사 시트 비밀번호 등록</h2>
<p>인사 화면 백엔드(구글 Apps Script)의 읽기 비밀번호를 서버 환경파일에만 넣습니다.<br>
값은 화면·응답·로그·채팅 어디에도 남지 않습니다. 저장 전에 시트 읽기를 한 번 시험합니다.</p>
<p>현재 상태: <b id="st">확인 중…</b></p>
<input id="pw" type="password" autocomplete="off" placeholder="비밀번호">
<button id="go">시험하고 저장</button>
<div id="out"></div>
<script>
const st=document.getElementById('st'),out=document.getElementById('out'),pw=document.getElementById('pw');
fetch('/api/hr-secret/status').then(r=>r.json()).then(d=>st.textContent=d.set?'등록됨':'없음').catch(()=>st.textContent='확인 실패');
document.getElementById('go').onclick=async()=>{
  out.textContent='시험 중…';
  const r=await fetch('/api/hr-secret',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw.value})});
  const d=await r.json().catch(()=>({}));
  pw.value='';
  out.textContent=d.ok?('저장 완료 — 직원 행 '+d.rows+'건 읽힘'):('저장 안 됨 — '+(d.error||r.status));
  if(d.ok)st.textContent='등록됨';
};
</script>"""


@router.get("", response_class=HTMLResponse)
def page(request: Request):
    if _user(request) not in _admins():
        return HTMLResponse("<meta charset=utf-8><p>인사 관리자 계정만 엽니다.</p>", status_code=403)
    return HTMLResponse(PAGE)


@router.get("/status")
def status(request: Request):
    if _user(request) not in _admins():
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    return {"ok": True, "set": bool(os.environ.get(KEY))}


@router.post("")
async def put(request: Request):
    who = _user(request)
    if who not in _admins():
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    pw = str((body or {}).get("password") or "").strip()
    if not pw:
        return JSONResponse({"ok": False, "error": "empty"}, status_code=400)
    ok, info = _probe(pw)
    if not ok:
        print("[hr-secret] %s 시험 실패 %s" % (who, info), flush=True)
        return JSONResponse({"ok": False, "error": "시트 읽기 실패(%s)" % info}, status_code=400)
    save_env(ENV_FILE, KEY, pw)
    os.environ[KEY] = pw
    print("[hr-secret] %s 저장 · 직원 행 %d" % (who, info), flush=True)
    return {"ok": True, "rows": info}


def selftest():
    """DB·네트워크 없이 — 환경파일 교체가 값을 바꾸고·붙이고·권한 0600 을 지키는지."""
    import stat
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "api.env")
        with open(p, "w", encoding="utf-8") as f:
            f.write("A=1\nHR_GAS_PASSWORD=\nB=2\n")
        save_env(p, KEY, "x y")
        assert open(p, encoding="utf-8").read() == "A=1\nHR_GAS_PASSWORD=x y\nB=2\n"
        save_env(p, "NEW_KEY", "v")
        assert open(p, encoding="utf-8").read().endswith("B=2\nNEW_KEY=v\n")
        assert stat.S_IMODE(os.stat(p).st_mode) == 0o600 or os.name == "nt"
    os.environ["HR_ADMIN_EMAILS"] = "A@x.com, b@y.com"
    os.environ["ERP_PLATFORM_ADMINS"] = ""
    assert _admins() == {"a@x.com", "b@y.com"}
    print("selftest ok")


if __name__ == "__main__":
    selftest()
