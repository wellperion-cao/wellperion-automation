# -*- coding: utf-8 -*-
"""server 모드 문의 쓰기(member_inquiry_update·lesson_inquiry_update)를 문의 거울(inquiries)에 그 자리에서 반영 (2026-09-15 시토).

왜 필요한가 — 2026-09-11 write_member 가 server 로 바뀐 뒤 문의 수정은 서버 원장(write_log)에만 적고 즉시 답한다.
시트는 pushback.py(1분)가 되밀고 그 뒤에야 sync_inquiries.py 가 거울을 다시 뜬다. 그 사이(실측 40초~2분) 거울은
저장 전 값이라, 화면(membership.html)은 쓰기 뒤 6분 동안 GAS 를 직접 읽는 우회를 타고 있었다 — 느리고(GAS 왕복)
그마저 시트가 아직 안 바뀌어 옛값이 떴다(실무진 피드백 FB260915-162312 「수정이 너무 느려졌어요 · 새로고침도 잘 안 돼요」).
그래서 mirror_patch(업무·결재)·mirror_proc(구매요청)과 같은 모양으로, 서버가 쓰기를 받는 순간 거울 행을 직접 고친다.
화면은 이제 쓰기 뒤에도 거울(/api/inquiries)을 읽는다.

★안전한 이유: 거울 한 곳만 고치고 시트에는 손대지 않는다. 이 반영이 틀려도 1~2분 뒤 sync_inquiries 가 GAS 판으로
  덮어써 스스로 낫는다. 모르는 액션·못 찾는 행은 조용히 False — 예외를 밖으로 내지 않는다(저장을 막으면 안 된다).
반영 규칙 = payload 의 칸 이름이 곧 거울 data 의 칸 이름이다(2026-09-15 실측: status·reservations·regProgram·lossReason·
  contacts·owner 전부 같은 이름). reservations·contacts 는 화면이 JSON 문자열로 보내고 거울은 목록으로 갖는다 → 풀어서 넣는다.

자체점검: python3 mirror_inquiry.py
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db  # noqa: E402

ACTIONS = ("member_inquiry_update", "lesson_inquiry_update")
SKIP = {"action", "idem", "keyPhone", "rowIndex", "rowKey", "staff", "type", "gid", "wpKey", "key", "sport"}


def _now():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds")


def fields_of(payload):
    out = {}
    for k, v in (payload or {}).items():
        if k in SKIP or v is None:
            continue
        if isinstance(v, str) and v[:1] in "[{":
            try:
                v = json.loads(v)
            except Exception:  # noqa: BLE001 — 문자열 그대로 둔다
                pass
        out[k] = v
    return out


def apply(conn, action, payload):
    """반영했으면 True. 모르는 액션·키 없음·거울에 없는 행이면 False."""
    if action not in ACTIONS:
        return False
    key = str((payload or {}).get("rowKey") or "").strip()
    kind = "멤버십" if action == "member_inquiry_update" else str((payload or {}).get("type") or "").strip()
    fields = fields_of(payload)
    if not key or not kind or not fields:
        return False
    with conn:
        cur = conn.execute(
            "UPDATE inquiries SET data = data || %s::jsonb, status = COALESCE(%s, status), synced_at = %s"
            " WHERE tenant_id=%s AND type=%s AND row_key=%s",
            (json.dumps(fields, ensure_ascii=False), fields.get("status"), _now(), db.TENANT, kind, key))
    return bool(getattr(cur, "rowcount", 0))


if __name__ == "__main__":
    class _Cur:
        rowcount = 1
    class _Conn:
        def __init__(self):
            self.calls = []
        def execute(self, q, p):
            self.calls.append((q, p)); return _Cur()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
    c = _Conn()
    ok = apply(c, "member_inquiry_update", {"action": "member_inquiry_update", "idem": "x", "keyPhone": "010", "rowIndex": "114",
                                            "rowKey": "20260127|010|김명옥", "staff": "임정은", "reservations": '[{"date":"2026-09-22"}]', "status": "가망"})
    assert ok and len(c.calls) == 1
    q, p = c.calls[0]
    assert json.loads(p[0]) == {"reservations": [{"date": "2026-09-22"}], "status": "가망"} and p[1] == "가망" and p[3] == db.TENANT and p[4] == "멤버십" and p[5] == "20260127|010|김명옥", p
    assert apply(c, "member_inquiry_update", {"rowKey": "k"}) is False          # 바꿀 칸 없음
    assert apply(c, "member_inquiry_delete", {"rowKey": "k", "status": "x"}) is False   # 모르는 액션
    assert apply(c, "lesson_inquiry_update", {"rowKey": "k", "owner": "임정은"}) is False  # type 없음
    assert apply(c, "lesson_inquiry_update", {"rowKey": "k", "type": "성인강습", "owner": "임정은"}) is True
    print("selftest ok")
