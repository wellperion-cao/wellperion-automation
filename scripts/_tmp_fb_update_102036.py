# -*- coding: utf-8 -*-
import sys, io, json, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

FB_GAS_URL = ("https://script.google.com/macros/s/"
              "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec")
FB_TOKEN = "wlp_intake_9f4c1b7e2a63"
FEEDBACK_ID = "FB260820-102036"

memo = (
    "[2026-08-20] GM 결재 대기 중. "
    "어제(FB260819-182908)에 동일 건 접수·분석 완료 — 송소림 01071812020, "
    "rowKey=20260819155328|01071812020|송소림(오후3:53 데이터)을 '중복(삭제)' 소프트 삭제 예정. "
    "삭제는 되돌릴 수 없는 작업으로 GM 결재 후 실행 규칙 준수 중. "
    "배 NEXT-20260819-183555('GM 결재 후 rowKey=...|송소림 행 삭제 실행') PENDING 상태 유지. "
    "GM님 승인 즉시 자동 실행 예정."
)

payload = [{"id": FEEDBACK_ID, "status": "GM결재대기", "memo": memo}]
body = json.dumps({"action": "staff_feedback_update", "t": FB_TOKEN, "updates": payload})
try:
    r = requests.post(FB_GAS_URL, data=body.encode("utf-8"),
                      headers={"Content-Type": "text/plain;charset=utf-8"},
                      allow_redirects=True, timeout=60)
    r.encoding = "utf-8"
    data = r.json()
    print("staff_feedback_update:", "OK" if data.get("ok") else "FAIL", data)
except Exception as e:
    print("ERROR:", e)
