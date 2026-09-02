# -*- coding: utf-8 -*-
"""
FB260902-151336 피드백 처리상태 업데이트
레코드 확인 완료 결과를 실무진 화면에 기록.
"""
from __future__ import annotations
import json, sys, urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

FB_GAS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec"
)
FB_TOKEN = "wlp_intake_9f4c1b7e2a63"
FB_ID = "FB260902-151336"

MEMO = (
    "[2026-09-02 처리완료] "
    "정지숙(010-9955-8757) 강습문의 레코드 확인. "
    "단체강습 시트 2831행, 2025-09-21 접수. "
    "현재 상태LOSS·담당없음 확인. "
    "월수 새벽7시 단체강습 2026-09-02 등록완료·담당 김성은으로 "
    "시트 직접 수정 필요(2831행 상태→등록완료, 담당→김성은)."
)

def main() -> int:
    payload = [{"id": FB_ID, "status": "처리완료", "memo": MEMO}]
    body = json.dumps(
        {"action": "staff_feedback_update", "t": FB_TOKEN, "updates": payload}
    ).encode("utf-8")
    req = urllib.request.Request(
        FB_GAS_URL, data=body, headers={"Content-Type": "text/plain;charset=utf-8"}
    )
    try:
        raw = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
        data = json.loads(raw)
    except Exception as e:
        print(f"[error] {e}")
        return 1
    if not data.get("ok"):
        print(f"[error] ok=false: {data.get('error') or data}")
        return 1
    updated = data.get("updated") or []
    not_found = data.get("notFound") or []
    print(f"[OK] updated={updated} notFound={not_found}")
    print(f"memo={MEMO}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
