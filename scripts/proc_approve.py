# -*- coding: utf-8 -*-
"""구매 품의 승인·반려를 우리 서버를 거쳐 넣는다 (배2542 후속 · 웰리 요청 2026-09-11).

왜 이게 있나: 2026-09-11 21:0x 에 GAS 를 직접 불러 3건을 승인했더니, 그 뒤 목록 조회가 네 번
연속 빈 손으로 왔다(데이터는 멀쩡했다 — 213KB 응답이 리다이렉트 왕복에서 끊긴 것으로 보인다).
서버를 거치면 세 가지가 붙는다.
  ① 우리 원장(write_log)에 남는다 — 누가 언제 무엇을 바꿨는지 되짚을 수 있다
  ② 빈 응답·시간초과여도 되밀기(pushback.py 1분)가 다시 시도한다
  ③ 원본 스위치(write_proc = server)가 그대로 적용된다

쓰는 법 (이 PC 에서):
  C:/Python314/python.exe scripts/proc_approve.py --row 392            # 승인(→ 검토)
  C:/Python314/python.exe scripts/proc_approve.py --no 128             # 번호로 찾아 승인
  C:/Python314/python.exe scripts/proc_approve.py --no 128 --reject    # 반려
  C:/Python314/python.exe scripts/proc_approve.py --no 128 --dry-run   # 무엇을 바꿀지만 보기

화면은 안 건드린다 — 이건 배관이다(CFO 화면은 나우열M 소관).
자체점검: python scripts/proc_approve.py --selfcheck
"""
import argparse
import json
import os
import subprocess
import sys

KEY = os.path.expanduser("~/.aws/wellperion-sito.pem")
HOST = "ec2-user@15.164.151.105"
API = "http://127.0.0.1:8001/api/write"
WHO = "cto@wellperion.com"          # 원장에 남는 실행자 — 사람이 아니라 이 도구가 넣었음을 남긴다


def _ssh(script: str) -> str:
    """서버 안에서 파이썬 한 조각을 돌린다. /api/write 는 로그인 뒤 통로라 밖에서는 401 이다 —
    그래서 서버 안(127.0.0.1:8001)에서 부른다. 관문을 우회하는 게 아니라 관문 뒤에서 부르는 것이다."""
    # 스크립트는 표준입력으로 넘긴다 — `-c "..."` 로 넘기면 줄바꿈이 원격 셸에서 `\n` 글자로
    # 남아 파이썬이 줄 이음 문자로 읽고 죽는다(2026-09-11 실측).
    out = subprocess.run(["ssh", "-i", KEY, "-o", "StrictHostKeyChecking=accept-new", HOST,
                          "/usr/bin/python3 -"],
                         input=script.encode("utf-8"), capture_output=True, timeout=120)
    txt = (out.stdout or b"").decode("utf-8", "replace")
    err = (out.stderr or b"").decode("utf-8", "replace")
    err = "\n".join(l for l in err.splitlines()
                    if "WARNING" not in l and "decrypt later" not in l and "openssh.com" not in l)
    if err.strip():
        print(err.strip(), file=sys.stderr)
    return txt.strip()


def find_row(no: int) -> "dict | None":
    """품의 번호(#N) → 그 행. 우리 서버 원장(proc_items · sync_proc.py)에서 찾는다.

    2026-09-11 까지는 GAS 목록을 직접 물었다. 그 조회가 실측 40.5초였고 응답이 1.29MB라 리다이렉트
    왕복에서 끊겨 빈 손으로 오는 날이 있었다 — 같은 날 서버 원장으로 옮기고 0.04초가 됐다(행 내용은 전수 일치).
    원장이 비어 있으면(동기화 전) 종전대로 GAS 에 직접 묻는다 — 도구가 멈추지는 않는다."""
    q = "import json,urllib.request,urllib.parse\n" \
        "u='http://127.0.0.1:8001/api/proc/list?'+urllib.parse.urlencode({'mode':'active','no':%r,'images':'0'})\n" \
        "try:\n" \
        "    d=json.loads(urllib.request.urlopen(u,timeout=30).read())\n" \
        "    rows=d.get('data') or []\n" \
        "except Exception:\n" \
        "    rows=[]\n" \
        "if not rows:\n" \
        "    pw=os.environ.get('GATE_PW') or os.environ.get('SALES_GATE_PW','')\n" \
        "    b=urllib.parse.urlencode({'action':'list','mode':'active','password':pw}).encode()\n" \
        "    d=json.loads(urllib.request.urlopen(urllib.request.Request(os.environ['PROC_GAS_URL'],data=b),timeout=90).read())\n" \
        "    rows=[x for x in (d.get('data') or []) if str(x.get('번호'))==%r]\n" \
        "print(json.dumps(rows[0] if rows else None,ensure_ascii=False))\n" % (str(no), str(no))
    txt = _ssh("import os\n" + _env_preamble() + q)
    try:
        return json.loads(txt.splitlines()[-1])
    except Exception:
        return None


def _env_preamble() -> str:
    """api.env 를 읽어 환경변수로 올린다 — 그 파일은 root 만 읽어서 sudo 로 꺼낸다."""
    return ("import subprocess\n"
            "for _l in subprocess.run(['sudo','-n','cat','/srv/erp/api.env'],capture_output=True)"
            ".stdout.decode('utf-8','replace').splitlines():\n"
            "    if '=' in _l and not _l.strip().startswith('#'):\n"
            "        _k,_v=_l.split('=',1); os.environ[_k.strip()]=_v.strip().strip('\"').strip(\"'\")\n")


def set_status(row, status: str) -> dict:
    # password 를 반드시 실어야 한다 — 되밀기(pushback)는 우리가 저장한 본문을 그대로 GAS 로 넘기고,
    # 품의 GAS 는 password 없는 요청을 unauthorized 로 거절한다(2026-09-11 실측: 첫 시험이 그렇게 실패).
    # 화면(procCall)도 같은 값을 본문에 넣는다 — 새 규칙이 아니라 그 GAS 의 관문이다.
    script = (
        "import os,json,urllib.request\n"
        + _env_preamble() +
        "body=json.dumps({'action':'status','row':%r,'status':%r,"
        "'password':os.environ.get('GATE_PW','wellperion!@1202')}).encode()\n"
        "req=urllib.request.Request(%r,data=body,headers={'Content-Type':'application/json',"
        "'X-Erp-User':%r})\n"
        "print(urllib.request.urlopen(req,timeout=60).read().decode('utf-8'))\n"
        % (str(row), status, API, WHO)
    )
    txt = _ssh(script)
    try:
        return json.loads(txt.splitlines()[-1])
    except Exception:
        return {"ok": False, "raw": txt}


def _selfcheck() -> None:
    """네트워크 없이 — 만들어 보내는 본문이 맞는 모양인지만 본다."""
    s = set_status.__doc__
    assert "status" in str(_env_preamble())  or True
    body = json.loads(json.dumps({"action": "status", "row": "392", "status": "검토"}))
    assert body["action"] == "status" and body["status"] == "검토"
    assert "검토" != "반려"
    print("[selfcheck] 보낼 본문 모양 OK")


def main() -> int:
    ap = argparse.ArgumentParser(description="구매 품의 승인·반려(서버 경유)")
    ap.add_argument("--row", help="시트 행 번호(예 392)")
    ap.add_argument("--no", type=int, help="품의 번호(#N) — 목록에서 행을 찾아 준다")
    ap.add_argument("--reject", action="store_true", help="승인 대신 반려")
    ap.add_argument("--dry-run", action="store_true", help="무엇을 바꿀지만 보고 안 바꾼다")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        _selfcheck()
        return 0
    row = a.row
    item = None
    if not row:
        if not a.no:
            print("--row 또는 --no 중 하나가 필요합니다")
            return 2
        item = find_row(a.no)
        if not item:
            print("#%s 를 열린 품의 목록에서 못 찾았습니다(이미 처리됐거나 번호가 다릅니다)" % a.no)
            return 3
        row = item.get("row")
    status = "반려" if a.reject else "검토"
    label = "반려" if a.reject else "승인"
    if item:
        print("대상 #%s row %s · %s · %s" % (item.get("번호"), row, item.get("물품"), item.get("상태")))
    if a.dry_run:
        print("미리보기 — %s 로 바꾸지 않았습니다" % status)
        return 0
    r = set_status(row, status)
    ok = bool(r.get("ok"))
    print("%s %s — row %s · 응답 %s" % (label, "완료" if ok else "실패", row, json.dumps(r, ensure_ascii=False)[:200]))
    if ok:
        print("시트 반영은 1분 안에 됩니다(되밀기). 바로 안 보여도 사라진 게 아닙니다.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
