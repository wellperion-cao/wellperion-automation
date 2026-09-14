"""구매요청 거울(proc_items) 즉시 반영 — 서버 원본 쓰기(add·status·delete·photo)가 ok 를 주는 그 자리에서.

왜(2026-09-14 · 나우열M 요청 · [나우열M 요청 2026-09-14]):
  write_proc 이 server 모드라 쓰기는 즉시 ok 지만 시트는 되밀기(1분) 뒤, 거울은 그 뒤 sync_proc(≈1분) 뒤에야 바뀐다.
  그 사이 서버 목록을 읽는 화면은 지워진 행·옛 상태를 보여 승인·삭제가 시트에서 거부됐다(14:03 실사고).
  업무·결재 거울(mirror_patch.py)이 하는 것과 같은 자리·같은 뜻으로 구매요청 거울도 그 자리에서 고친다.
  이 반영이 틀려도 sync_proc.py(되밀기 뒤 + 10분 cron)가 GAS 판으로 덮어써 스스로 낫는다 — 그래서 실패해도 저장을 막지 않는다.

GAS procurement.js 와 같은 뜻으로(각 함수 주석에 그 자리를 적는다):
  add    → appendRow(마지막 행 + 1) · 상태 「품의」 · 번호 = 서버 채번(payload.no)            (addItem)
  status → 12열 상태 · 「검토」면 13열 승인날짜=오늘 · ACTIVE 밖이면 done 목록(src=all)으로   (setStatus)
  delete → deleteRow — 그 뒤 행이 전부 한 칸 올라온다(행번호가 열쇠라 거울도 같이 밀어야 한다)  (delRow)
  photo  → 11열 이미지 = data:mime;base64,썸네일                                             (putPhoto)

ponytail: add 의 새 행번호 = 거울 최댓값+1. 시트 끝에 요청자 빈 줄이 있으면 실제 appendRow 행과 어긋날 수 있다 —
  그 경우 sync_proc 가 되밀기 뒤 바로잡는다(열쇠를 품의번호로 바꾸는 것이 다음 단계).
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db  # noqa: E402

KST = timezone(timedelta(hours=9))
ACTIVE = {"품의", "검토", "정산"}          # procurement.js listItems 의 ACTIVE 와 같다


def _today():
    n = datetime.now(KST)
    return "%d. %d. %d" % (n.year, n.month, n.day)   # GAS today() "yyyy. M. d"


def _now():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def _price(v):
    m = re.sub(r"[^0-9]", "", str(v or ""))
    return int(m) if m else 0


def _row(payload):
    try:
        return int(str(payload.get("row") or "").strip())
    except ValueError:
        return 0


def _load(conn, row):
    r = conn.execute("SELECT src, data FROM proc_items WHERE tenant_id=%s AND row=%s", (db.TENANT, row)).fetchone()
    if not r:
        return None, None
    d = r["data"] if isinstance(r["data"], dict) else json.loads(r["data"])
    return r["src"], d


def _save(conn, row, src, d):
    conn.execute(
        "UPDATE proc_items SET src=%s, status=%s, data=%s, synced_at=%s WHERE tenant_id=%s AND row=%s",
        (src, d.get("상태") or "", json.dumps(d, ensure_ascii=False), _now(), db.TENANT, row))


def add(conn, p):
    """addItem — 열 순서·기본값 그대로(이미지·승인날짜·증빙은 빈칸, 상태 품의)."""
    last = conn.execute("SELECT COALESCE(MAX(row), 0) FROM proc_items WHERE tenant_id=%s", (db.TENANT,)).fetchone()[0]
    row = int(last) + 1
    pay = str(p.get("결제") or "").strip()
    d = {
        "row": row, "날짜": _today(), "요청자": p.get("요청자") or "", "소속": p.get("소속") or "",
        "물품": p.get("물품") or "", "링크": p.get("링크") or "", "가격": p.get("가격") or "",
        "목적": p.get("목적") or "", "승인자": p.get("승인자") or "", "이미지": "", "상태": "품의",
        "승인날짜": "", "지출증빙": "", "항목1": p.get("항목1") or "", "항목2": p.get("항목2") or "",
        "번호": p.get("no") if p.get("no") not in (None, "") else "",
        "구매날짜": p.get("구매날짜") or "", "배송비": p.get("배송비") or "",
        "결제": pay if pay in ("현금", "카드") else "",
        "자산": "Y" if str(p.get("자산") or "").strip().upper() == "Y" else "",
    }
    conn.execute(
        "INSERT INTO proc_items (tenant_id,row,src,no,ymd,requester,dept,item,status,price,data,synced_at)"
        " VALUES (%s,%s,'active',%s,%s,%s,%s,%s,'품의',%s,%s,%s)"
        " ON CONFLICT (tenant_id,row) DO NOTHING",
        (db.TENANT, row, str(d["번호"]), d["날짜"], d["요청자"], d["소속"], d["물품"], _price(d["가격"]),
         json.dumps(d, ensure_ascii=False), _now()))
    return row


def status(conn, p):
    row = _row(p)
    src, d = _load(conn, row)
    if d is None:
        return False
    st = str(p.get("status") or "")
    d["상태"] = st
    if st == "검토":
        d["승인날짜"] = _today()
    _save(conn, row, "active" if st in ACTIVE else "all", d)
    return True


def delete(conn, p):
    """delRow — 지우고 그 뒤 행을 한 칸씩 올린다. PK(tenant,row) 충돌을 피해 두 단계(음수 경유)로 민다."""
    row = _row(p)
    n = conn.execute("DELETE FROM proc_items WHERE tenant_id=%s AND row=%s", (db.TENANT, row)).rowcount
    if not n:
        return False
    conn.execute("UPDATE proc_items SET row = -(row - 1) WHERE tenant_id=%s AND row > %s", (db.TENANT, row))
    conn.execute("UPDATE proc_items SET row = -row WHERE tenant_id=%s AND row < 0", (db.TENANT,))
    # data 안의 row 도 화면이 그대로 쓴다(승인·삭제 버튼의 data-row) — 같이 맞춘다.
    rows = conn.execute("SELECT row, data FROM proc_items WHERE tenant_id=%s AND row >= %s", (db.TENANT, row)).fetchall()
    for r in rows:
        d = r["data"] if isinstance(r["data"], dict) else json.loads(r["data"])
        if d.get("row") != r["row"]:
            d["row"] = r["row"]
            conn.execute("UPDATE proc_items SET data=%s WHERE tenant_id=%s AND row=%s",
                         (json.dumps(d, ensure_ascii=False), db.TENANT, r["row"]))
    return True


def photo(conn, p):
    row = _row(p)
    src, d = _load(conn, row)
    if d is None:
        return False
    thumb = re.sub(r"[^A-Za-z0-9+/=]", "", str(p.get("thumb") or p.get("fileData") or ""))
    mime_ok = lambda m: bool(re.match(r"^image/[A-Za-z0-9.+-]{1,30}$", str(m or "")))   # noqa: E731
    mime = p.get("thumbMime") if mime_ok(p.get("thumbMime")) else (p.get("mimeType") if mime_ok(p.get("mimeType")) else "image/jpeg")
    if thumb:
        d["이미지"] = "data:%s;base64,%s" % (mime, thumb)
    _save(conn, row, src, d)
    return True


HANDLERS = {"add": add, "status": status, "delete": delete, "photo": photo}


def apply(conn, action, payload):
    """api_write 가 부르는 자리(서버 모드 · 구매요청 GAS 목적지). 모르는 액션은 아무것도 안 한다."""
    fn = HANDLERS.get(action)
    if fn is None:
        return None
    with conn:
        return fn(conn, payload or {})


def selftest():
    """실제 DB 에서 시험 테넌트(t_selftest_proc)로 한 바퀴 — 끝나면 지운다."""
    conn = db.connect()
    real = db.TENANT
    db.TENANT = "t_selftest_proc"
    try:
        with conn:
            conn.execute("DELETE FROM proc_items WHERE tenant_id=%s", (db.TENANT,))
            for row, no, st in ((395, "133", "검토"), (396, "135", "품의"), (397, "136", "품의")):
                conn.execute(
                    "INSERT INTO proc_items (tenant_id,row,src,no,ymd,requester,dept,item,status,price,data,synced_at)"
                    " VALUES (%s,%s,'active',%s,'2026. 9. 14','r','d','i',%s,1,%s,%s)",
                    (db.TENANT, row, no, st, json.dumps({"row": row, "번호": no, "상태": st}, ensure_ascii=False), _now()))
        assert apply(conn, "add", {"no": 137, "요청자": "홍길동", "소속": "시설", "물품": "장갑", "가격": "1,000", "결제": "현금", "자산": "y"}) == 398
        _, d = _load(conn, 398)
        assert d["번호"] == 137 and d["상태"] == "품의" and d["결제"] == "현금" and d["자산"] == "Y" and d["날짜"] == _today(), d
        assert apply(conn, "status", {"row": "396", "status": "검토"}) is True
        src, d = _load(conn, 396)
        assert src == "active" and d["상태"] == "검토" and d["승인날짜"] == _today(), d
        assert apply(conn, "status", {"row": "396", "status": "완료"}) is True
        src, d = _load(conn, 396)
        assert src == "all" and d["상태"] == "완료", (src, d)          # ACTIVE 밖 = done 목록으로
        assert apply(conn, "photo", {"row": "397", "thumb": "QUJD", "thumbMime": "image/png"}) is True
        assert _load(conn, 397)[1]["이미지"] == "data:image/png;base64,QUJD"
        assert apply(conn, "delete", {"row": "396"}) is True          # 397→396, 398→397 로 밀린다
        rows = [(r["row"], json.loads(r["data"])["row"], r["no"]) for r in conn.execute(
            "SELECT row, data, no FROM proc_items WHERE tenant_id=%s ORDER BY row", (db.TENANT,)).fetchall()]
        assert rows == [(395, 395, "133"), (396, 396, "136"), (397, 397, "137")], rows
        assert apply(conn, "status", {"row": "999", "status": "검토"}) is False   # 없는 행 = 거짓, 예외 아님
        assert apply(conn, "asset_update", {}) is None                         # 모르는 액션 = 무동작
        print("selftest ok")
    finally:
        with conn:
            conn.execute("DELETE FROM proc_items WHERE tenant_id=%s", (db.TENANT,))
        db.TENANT = real
        conn.close()


if __name__ == "__main__":
    selftest()
