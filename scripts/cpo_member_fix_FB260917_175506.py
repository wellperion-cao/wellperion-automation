# -*- coding: utf-8 -*-
"""
기외호(M00248) 종료일자 교정 (2026-09-17 · 접수ID FB260917-175506)

실무진 피드백(임정은):
  기외호님 종료일자가 자꾸 26-9-16으로 바뀌는 현상
  → 종료일자 26-9-17로 수정 요청

원인(change_log 실측):
  오늘 3회(10:23 1202 · 10:44 임정은 · 12:23 이름미상) 9/17→9/16 변경
  → GAS/시트에 9/16이 남아 있어 sync가 서버를 덮어씀
  해결: 서버 write-through로 GAS에도 9/17 기록 → sync 역행 차단

사용:
  python scripts\\cpo_member_fix_FB260917_175506.py --dry-run   # 확인만
  python scripts\\cpo_member_fix_FB260917_175506.py             # 실제 변경
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SSH_KEY = os.path.expanduser("~/.aws/wellperion-sito.pem")
SSH_HOST = "ec2-user@15.164.151.105"
SERVER_WRITE_API = "http://127.0.0.1:8001/api/write"
WRITE_WHO = "cpo@wellperion.com"

FB_GAS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec"
)
FB_TOKEN = "wlp_intake_9f4c1b7e2a63"
FB_ID = "FB260917-175506"

TARGET_MEMBER_NO = "M00248"
TARGET_NAME = "기외호"
TARGET_PHONE = "01052221585"
TARGET_END_DATE = "2026-09-17"

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def _ssh(script: str) -> str:
    out = subprocess.run(
        ["ssh", "-i", SSH_KEY, "-o", "StrictHostKeyChecking=accept-new", SSH_HOST,
         "/usr/bin/python3 -"],
        input=script.encode("utf-8"), capture_output=True, timeout=120,
    )
    txt = (out.stdout or b"").decode("utf-8", "replace")
    err = (out.stderr or b"").decode("utf-8", "replace")
    err = "\n".join(
        l for l in err.splitlines()
        if "WARNING" not in l and "decrypt later" not in l and "openssh.com" not in l
    )
    if err.strip():
        print(err.strip(), file=sys.stderr)
    return txt.strip()


def _server_write(payload: dict) -> tuple[bool, str]:
    body_json = json.dumps(payload, ensure_ascii=False)
    script = (
        "import urllib.request\n"
        "body=%r.encode('utf-8')\n"
        "req=urllib.request.Request(%r,data=body,headers={'Content-Type':'application/json',"
        "'X-Erp-User':%r,'X-Erp-Allowed':'*'})\n"
        "print(urllib.request.urlopen(req,timeout=60).read().decode('utf-8'))\n"
        % (body_json, SERVER_WRITE_API, WRITE_WHO)
    )
    txt = _ssh(script)
    try:
        data = json.loads(txt.splitlines()[-1])
        return bool(data.get("ok")), json.dumps(data, ensure_ascii=False)
    except Exception:
        return False, txt


def _verify_current(dry: bool) -> str | None:
    """서버 DB 현재 end_date 확인."""
    script = (
        "import sys, json\n"
        "sys.path.insert(0, '/srv/erp/api')\n"
        "import sync_inquiries as si\n"
        "si.load_env()\n"
        "conn = si.db.connect()\n"
        "cur = conn.execute(\"SELECT end_date::text FROM members WHERE member_no = 'M00248'\")\n"
        "r = cur.fetchone()\n"
        "print(r[0] if r else 'NOT_FOUND')\n"
    )
    return _ssh(script).strip()


def _update_feedback(dry: bool, success: bool, detail: str = "") -> None:
    if dry:
        print("[feedback] DRY — 건너뜀")
        return
    if success:
        memo = (
            f"[2026-09-17 처리완료] {TARGET_NAME}({TARGET_PHONE}) 멤버십 종료일자 교정. "
            f"9/17→9/16으로 변경되는 원인: GAS 시트에 9/16이 남아 sync가 서버를 덮어씀. "
            f"서버 write-through로 GAS에도 9/17 기록 → sync 역행 차단. "
            f"재발 방지: 화면에서 저장 시 서버+GAS 동시 반영되므로 다른 담당자와 조율 필요. {detail}"
        )
        status_str = "처리완료"
    else:
        memo = (
            f"[2026-09-17 처리불가] {TARGET_NAME}({TARGET_PHONE}) 서버 write-through 실패. "
            f"멤버십 회원관리 화면에서 직접 수정 요망(종료일 → 2026-09-17). {detail}"
        )
        status_str = "처리불가"

    import urllib.request
    payload = [{"id": FB_ID, "status": status_str, "memo": memo}]
    body = json.dumps({"action": "staff_feedback_update", "t": FB_TOKEN, "updates": payload}).encode("utf-8")
    req = urllib.request.Request(FB_GAS_URL, data=body, headers={"Content-Type": "text/plain;charset=utf-8"})
    try:
        raw = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
        data = json.loads(raw)
        if data.get("ok"):
            print(f"[feedback] {status_str} — staff_feedback_update OK")
        else:
            print(f"[feedback] ok=false: {data.get('error') or data}")
    except Exception as e:
        print(f"[feedback] 실패: {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # 1. 현재 서버 값 확인
    current = _verify_current(args.dry_run)
    print(f"[verify-before] DB end_date = {current}")

    if args.dry_run:
        print(f"[DRY] member_active_update: {TARGET_MEMBER_NO} end_date → {TARGET_END_DATE}")
        _update_feedback(dry=True, success=True)
        return 0

    # 2. 서버 write-through (member_active_update)
    payload = {
        "action": "member_active_update",
        "member_no": TARGET_MEMBER_NO,
        "keyPhone": TARGET_PHONE,
        "end_date": TARGET_END_DATE,
    }
    print(f"[write] member_active_update {TARGET_MEMBER_NO} end_date → {TARGET_END_DATE}")
    ok, resp = _server_write(payload)
    print(f"[write] ok={ok} resp={resp[:300]}")

    if not ok:
        _update_feedback(dry=False, success=False, detail=resp[:200])
        return 1

    # 3. 적용 후 재확인
    after = _verify_current(args.dry_run)
    print(f"[verify-after] DB end_date = {after}")

    if after != TARGET_END_DATE:
        print(f"[warn] DB 값이 기대값({TARGET_END_DATE})과 다름: {after}")
        _update_feedback(dry=False, success=False, detail=f"DB 재확인 실패: {after}")
        return 1

    print(f"[OK] {TARGET_NAME} 종료일자 {TARGET_END_DATE} 확인 완료")
    _update_feedback(dry=False, success=True, detail=f"서버 DB 재확인: {after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
