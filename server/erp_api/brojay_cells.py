# -*- coding: utf-8 -*-
"""매출·회원 현황 보고 — 시트 없이 브로제이 결제 + ERP 회원 원장만으로 채우는 칸 (배 2523 · 시포 2026-09-16).

GM 지시 2026-09-16: 「시트를 배제한 상태에서 브로제이랑 웰페리온 ERP 로만 매출 및 회원 + 운영 현황 보고를
최종 서버판으로 만들어라」. 이 모듈은 22칸 가운데 시트 손입력에 남아 있던 매출 11칸(I4·I6·I7·I8~I15 금일·누적)과
등록 6칸(N7~N12)을 서버 원천으로 계산한다. 회원 5칸(N2~N6)은 sales_report_render.compute_overrides, 입장 3칸
(N13~N15)은 api_visitors 가 이미 서버 원천이다.

원천
  결제  brojay_records kind='sales' (sync_brojay 가 하루 3회 담는 그날 결제 목록 · 결제 전액 · 부가세 포함 ·
        결제일 그대로 — GM 확정 2026-09-15 매출 정의)
  회원  members 표(ERP 회원관리 원장 · 등록분류·LOSS일자·전화)
칸 규칙
  회원권(I6)  = 매출분류 운영부 중 상품유형 MEMBERSHIP·FACILITY_TICKET(일일·단기 이용권)
  옵션(I7)    = 매출분류 운영부 중 LOCKER_TICKET(락커) · 그 밖의 운영부 유형은 회원권으로(실측 9/8~15 세 유형뿐)
  팀 8칸      = 매출분류(sales_tag_name) → 팀 (status/sales_targets.json brojay_tag · 못 읽으면 아래 TAG_TEAM)
  총 매출(I4) = 그날 결제 전부(분류 못 지은 것 포함 — 빠뜨리지 않는다 · unmapped 로 따로 센다)
  누적(J*)    = 그달 1일~기준일
  신규/재등록(N7~N10) = 그날 회원권 결제(MEMBERSHIP) 를 전화로 members 와 이어 등록분류가 「신규」면 신규, 그 밖은
                재등록 · 못 이은 건은 unmatched 로 따로 센다(지어내지 않는다)
  환불(N11)   = history_type 이 REFUND 인 건의 합(9/8~15 실측 0건 — 사양은 첫 환불이 오면 확인)
  로스자(N12) = members loss_date == 기준일

반환 형식은 sales_report_render 가 비교하는 시트 칸과 같은 문자열(금액 "1,234,567" · 사람 "N명") — 22칸
대조기가 그대로 짝을 지을 수 있게. 숫자 원본은 "raw" 에 함께 둔다.
실행: python3 brojay_cells.py [YYYY-MM-DD]   자체점검: python3 brojay_cells.py --selftest
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

KST = timezone(timedelta(hours=9))
REPO_DIR = os.environ.get("ERP_REPO_DIR", "/srv/erp/repo")

# 매출분류 → 팀 칸 행(보고탭 I8~I15) — 정본은 status/sales_targets.json teams[].brojay_tag(GM 확정 2026-09-15).
# 파일을 못 읽는 자리(자체점검·로컬)에서만 이 표를 쓴다. 두 표가 갈리면 파일이 이긴다.
TAG_TEAM = {"수영": 8, "PT": 9, "골프": 10, "스쿼시": 11, "체조&트램폴린": 12, "필라테스": 13, "뮤지컬": 14, "유료GX": 15}
TEAM_KEY_ROW = {"swim": 8, "pt": 9, "golf": 10, "squash": 11, "gym": 12, "pilates": 13, "musical": 14, "gxe": 15}
OPS_TAG = "운영부"
LOCKER_TYPES = {"LOCKER_TICKET"}


def _money(n):
    return format(int(n), ",")


def _digits(v):
    return re.sub(r"\D", "", str(v or ""))


def tag_rows(repo_dir=REPO_DIR):
    """{매출분류: 보고탭 행} — sales_targets.json 이 있으면 거기서, 없으면 TAG_TEAM."""
    p = os.path.join(repo_dir, "status", "sales_targets.json")
    try:
        with open(p, encoding="utf-8") as f:
            teams = json.load(f).get("teams") or []
        out = {}
        for t in teams:
            row = TEAM_KEY_ROW.get(str(t.get("key") or ""))
            tag = t.get("brojay_tag")
            if row and tag:
                out[str(tag)] = row
        return out or dict(TAG_TEAM)
    except Exception:
        return dict(TAG_TEAM)


def _day_of(rec):
    return str(rec.get("paid_at") or "")[:10]


def aggregate(payments, ref_date, tags, members_by_phone=None, phone_of_member=None, loss_count=0):
    """순수 계산 — payments = [{paid_at, history_type, product_type, sales_tag_name, member_id, total_payment_price}, ...]
    (그달 1일~기준일 전부). members_by_phone = {전화: 등록분류} · phone_of_member = {member_id: 전화}."""
    members_by_phone = members_by_phone or {}
    phone_of_member = phone_of_member or {}
    day = {"I4": 0, "I6": 0, "I7": 0}
    month = {"J4": 0, "J6": 0, "J7": 0}
    for r in range(8, 16):
        day["I%d" % r] = 0
        month["J%d" % r] = 0
    unmapped = {}
    refund_day = 0
    new_amt = new_n = re_amt = re_n = 0
    unmatched = 0
    for p in payments:
        d = _day_of(p)
        if not d or d > ref_date:
            continue
        amt = int(p.get("total_payment_price") or 0)
        is_day = d == ref_date
        if str(p.get("history_type") or "") == "REFUND":
            if is_day:
                refund_day += amt
            continue
        tag = str(p.get("sales_tag_name") or "")
        ptype = str(p.get("product_type") or "")
        if tag == OPS_TAG:
            cell = 7 if ptype in LOCKER_TYPES else 6
        elif tag in tags:
            cell = tags[tag]
        else:
            cell = None
            unmapped[tag or "(분류없음)"] = unmapped.get(tag or "(분류없음)", 0) + amt
        month["J4"] += amt
        if cell:
            month["J%d" % cell] += amt
        if is_day:
            day["I4"] += amt
            if cell:
                day["I%d" % cell] += amt
            if cell == 6 and ptype == "MEMBERSHIP":
                cls = members_by_phone.get(phone_of_member.get(str(p.get("member_id") or ""), ""))
                if cls is None:
                    unmatched += 1
                elif "신규" in cls:
                    new_amt += amt
                    new_n += 1
                else:
                    re_amt += amt
                    re_n += 1
    cells = {}
    for k, v in list(day.items()) + list(month.items()):
        cells[k] = _money(v)
    cells.update({"N7": _money(new_amt), "N8": "%d명" % new_n, "N9": _money(re_amt), "N10": "%d명" % re_n,
                  "N11": _money(refund_day), "N12": "%d명" % loss_count})
    return {"cells": cells, "raw": {"day": day, "month": month, "refund_day": refund_day,
                                    "new": [new_n, new_amt], "re": [re_n, re_amt]},
            "unmapped": unmapped, "unmatched_membership": unmatched, "payments": len(payments)}


def compute(ref_date=None):
    """DB 에서 그달 결제·회원 원장을 읽어 aggregate 로 넘긴다. 결제 적재가 없는 달은 None."""
    from sync_sales import db, load_env  # noqa: PLC0415
    load_env()
    if not ref_date:
        ref_date = (datetime.now(KST) - timedelta(days=1)).strftime("%Y-%m-%d")
    first = ref_date[:8] + "01"
    conn = db.connect(readonly=True)
    try:
        rows = conn.execute(
            "SELECT key, data FROM brojay_records WHERE tenant_id=%s AND kind='sales' AND key BETWEEN %s AND %s",
            (db.TENANT, first, ref_date)).fetchall()
        payments = []
        for r in rows:
            d = json.loads(r["data"])
            lst = d.get("data") if isinstance(d, dict) else d
            if isinstance(lst, dict):
                lst = lst.get("data")
            for p in (lst or []):
                if isinstance(p, dict):
                    payments.append(p)
        if not payments:
            return None
        mem = conn.execute(
            "SELECT phone, reg_class, loss_date FROM members WHERE tenant_id=%s AND scope IN ('valid','ended')",
            (db.TENANT,)).fetchall()
        members_by_phone = {_digits(m["phone"]): str(m["reg_class"] or "") for m in mem if _digits(m["phone"])}
        loss_count = sum(1 for m in mem if str(m["loss_date"] or "")[:10] == ref_date)
        snap = conn.execute(
            "SELECT data FROM brojay_records WHERE tenant_id=%s AND kind='members' ORDER BY key DESC LIMIT 1",
            (db.TENANT,)).fetchone()
        phone_of_member = {}
        if snap:
            d = json.loads(snap["data"])
            lst = d.get("data") if isinstance(d, dict) else d
            if isinstance(lst, dict):
                lst = lst.get("data")
            for m in (lst or []):
                if isinstance(m, dict) and m.get("member_id"):
                    phone_of_member[str(m["member_id"])] = _digits(m.get("phone_number"))
    finally:
        conn.close()
    out = aggregate(payments, ref_date, tag_rows(), members_by_phone, phone_of_member, loss_count)
    out.update({"ref_date": ref_date, "_source": "brojay+erp", "members_joined": bool(phone_of_member)})
    return out


def selftest():
    tags = dict(TAG_TEAM)
    pays = [
        {"paid_at": "2026-09-15T10:00:00+09:00", "history_type": "PAYMENT", "product_type": "MEMBERSHIP",
         "sales_tag_name": "운영부", "member_id": "A", "total_payment_price": 1000000},
        {"paid_at": "2026-09-15T11:00:00+09:00", "history_type": "PAYMENT", "product_type": "LOCKER_TICKET",
         "sales_tag_name": "운영부", "member_id": "A", "total_payment_price": 120000},
        {"paid_at": "2026-09-15T12:00:00+09:00", "history_type": "PAYMENT", "product_type": "RESERVATION_TICKET",
         "sales_tag_name": "수영", "member_id": "B", "total_payment_price": 209000},
        {"paid_at": "2026-09-14T12:00:00+09:00", "history_type": "PAYMENT", "product_type": "RESERVATION_TICKET",
         "sales_tag_name": "골프", "member_id": "C", "total_payment_price": 330000},
        {"paid_at": "2026-09-15T13:00:00+09:00", "history_type": "PAYMENT", "product_type": "RESERVATION_TICKET",
         "sales_tag_name": "요가", "member_id": "D", "total_payment_price": 50000},          # 분류 못 지음
        {"paid_at": "2026-09-15T14:00:00+09:00", "history_type": "REFUND", "product_type": "MEMBERSHIP",
         "sales_tag_name": "운영부", "member_id": "E", "total_payment_price": 300000},
        {"paid_at": "2026-09-16T09:00:00+09:00", "history_type": "PAYMENT", "product_type": "MEMBERSHIP",
         "sales_tag_name": "운영부", "member_id": "F", "total_payment_price": 999},           # 기준일 뒤 — 제외
    ]
    o = aggregate(pays, "2026-09-15", tags, {"01011112222": "신규"}, {"A": "01011112222"}, loss_count=2)
    c = o["cells"]
    assert c["I4"] == "1,379,000", c["I4"]          # 회원권 100만 + 락커 12만 + 수영 20.9만 + 요가 5만(분류 없음도 총액엔 포함)
    assert c["I6"] == "1,000,000" and c["I7"] == "120,000" and c["I8"] == "209,000" and c["I10"] == "0"
    assert c["J10"] == "330,000" and c["J4"] == "1,709,000"
    assert c["N7"] == "1,000,000" and c["N8"] == "1명" and c["N9"] == "0" and c["N10"] == "0명"
    assert c["N11"] == "300,000" and c["N12"] == "2명"
    assert o["unmapped"] == {"요가": 50000} and o["unmatched_membership"] == 0
    o2 = aggregate(pays, "2026-09-15", tags, {}, {"A": "01011112222"})
    assert o2["unmatched_membership"] == 1 and o2["cells"]["N8"] == "0명"   # 원장에 없으면 지어내지 않는다
    assert tag_rows("/nonexistent") == TAG_TEAM
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    arg = next((a for a in sys.argv[1:] if re.match(r"^\d{4}-\d{2}-\d{2}$", a)), None)
    res = compute(arg)
    print(json.dumps(res, ensure_ascii=False, indent=1) if res else "결제 적재 없음")
