# -*- coding: utf-8 -*-
import sys, io, json, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

FB_GAS_URL = ("https://script.google.com/macros/s/"
              "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec")
FB_TOKEN = "wlp_intake_9f4c1b7e2a63"
FEEDBACK_ID = "FB260820-110540"

memo = (
    "[2026-08-20 확인완료] "
    "김현수1(010-9118-6539) rowIndex 201 종료사유 칸이 비어있음을 스냅샷으로 확인했습니다. "
    "LOSS 처리(2026-08-19) 당시 종료사유가 입력되지 않아 저장되지 않은 것으로 판단됩니다. "
    "처리 방법: 회원관리 화면에서 김현수1 행을 찾아 종료사유 칸에 직접 입력 후 저장 부탁드립니다. "
    "(사유 내용은 담당자(임정은)가 직접 입력해 주세요)"
)

payload = [{"id": FEEDBACK_ID, "status": "처리완료", "memo": memo}]
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
