# -*- coding: utf-8 -*-
"""
기외호(M00248) 종료일자 확인·피드백 처리 (접수ID FB260917-185706)

실무진 피드백(임정은): 기외호님 종료일자 26/9/17로 변경해줘
현황: DB 이미 2026-09-17 — 이전 수정(FB260917-175506)으로 반영 완료.
이 스크립트: staff_feedback_update 상태만 처리완료로 갱신.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SSH_KEY = os.path.expanduser("~/.aws/wellperion-sito.pem")
SSH_HOST = "ec2-user@15.164.151.105"
FB_GAS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec"
)
FB_TOKEN = "wlp_intake_9f4c1b7e2a63"
FB_ID = "FB260917-185706"
TARGET_MEMBER_NO = "M00248"
TARGET_NAME = "기외호"
TARGET_END_DATE = "2026-09-17"


def _ssh(script: str) -> str:
    out = subprocess.run(
        ["ssh", "-i", SSH_KEY, "-o", "StrictHostKeyChecking=accept-new", SSH_HOST,
         "/usr/bin/python3 -"],
        input=script.encode("utf-8"), capture_output=True, timeout=120,
    )
    return (out.stdout or b"").decode("utf-8", "replace").strip()


def verify_db() -> str:
    script = (
        "import sys; sys.path.insert(0, '/srv/erp/api')\n"
        "import sync_inquiries as si; si.load_env()\n"
        "conn = si.db.connect()\n"
        "cur = conn.execute(\"SELECT end_date::text FROM members WHERE member_no = 'M00248'\")\n"
        "r = cur.fetchone()\n"
        "print(r[0] if r else 'NOT_FOUND')\n"
    )
    return _ssh(script).strip()


def update_feedback(success: bool, detail: str = "") -> bool:
    import urllib.request
    if success:
        memo = (
            f"[2026-09-17 처리완료] {TARGET_NAME} 멤버십 종료일자 {TARGET_END_DATE} 확인 완료. "
            f"서버 DB 실측: {TARGET_END_DATE}. "
            f"이전 FB260917-175506 처리(GAS write-through)로 이미 반영된 상태. {detail}"
        )
    else:
        memo = f"[2026-09-17 처리불가] DB 실측값이 기대와 다름. 화면에서 직접 확인 요망. {detail}"
    status_str = "처리완료" if success else "처리불가"
    payload = [{"id": FB_ID, "status": status_str, "memo": memo}]
    body = json.dumps({"action": "staff_feedback_update", "t": FB_TOKEN, "updates": payload}).encode("utf-8")
    req = urllib.request.Request(FB_GAS_URL, data=body, headers={"Content-Type": "text/plain;charset=utf-8"})
    try:
        raw = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
        data = json.loads(raw)
        ok = bool(data.get("ok"))
        print(f"[feedback] {status_str} — ok={ok}")
        if not ok:
            print(f"[feedback] error={data.get('error') or data}")
        return ok
    except Exception as e:
        print(f"[feedback] 실패: {e}")
        return False


def main() -> int:
    current = verify_db()
    print(f"[verify] M00248 end_date = {current}")
    if current == TARGET_END_DATE:
        print(f"[OK] DB 이미 {TARGET_END_DATE} — 피드백 처리완료 갱신")
        update_feedback(True, f"DB 실측: {current}")
        return 0
    else:
        print(f"[WARN] DB={current} 기대={TARGET_END_DATE} — 불일치")
        update_feedback(False, f"DB 실측: {current}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
