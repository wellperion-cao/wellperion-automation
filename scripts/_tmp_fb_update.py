# -*- coding: utf-8 -*-
import sys, io, json, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

FB_GAS_URL = ("https://script.google.com/macros/s/"
              "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec")
FB_TOKEN = "wlp_intake_9f4c1b7e2a63"
FEEDBACK_ID = "FB260819-174248"

memo = ("[2026-08-19 처리완료] 시트에 중복 데이터가 있는 것이 아니라, "
        "LOSS 처리 직후 이전 유효회원 캐시가 남아 검색 결과에 같은 회원이 두 번 표시되는 화면 버그였습니다. "
        "교차검색 중복 제거 로직을 추가하여 수정 완료했습니다(커밋 c668b892d). "
        "페이지 새로고침 후 이상준 회원이 1건만 표시됩니다.")

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
