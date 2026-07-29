import json, urllib.request, sys
FB_GAS_URL = ("https://script.google.com/macros/s/"
              "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec")
FB_TOKEN = "wlp_intake_9f4c1b7e2a63"
payload = [{"id": "FB260728-141756", "status": "처리완료",
            "memo": ("LOSS 카운트 시점 수정 완료 — membership.html "
                     "진행상황 LOSS 전환 시 미등록 사유 모달 저장 후 카운트 반영. "
                     "커밋 951beb522.")}]
body = json.dumps({"action": "staff_feedback_update", "t": FB_TOKEN, "updates": payload}).encode("utf-8")
req = urllib.request.Request(FB_GAS_URL, data=body, headers={"Content-Type": "text/plain;charset=utf-8"})
try:
    raw = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
    print(raw)
    data = json.loads(raw)
    sys.exit(0 if data.get("ok") else 1)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
