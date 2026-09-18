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

목록 4종("lists" · 배 12523 2단계 · 2026-09-18)
  registered  그날 결제(환불 제외) 전부 — 이름·분류는 전화로 members 를 이어(신규/재등록/미상), 못 이으면 브로제이
              회원 스냅샷 이름만 붙인다
  loss        members.loss_date == 기준일
  contact     members.reg_consult_date == 기준일 또는 재등록예약목록(reg_reservation) 안의 날짜 항목
  lesson      강습 8팀 신규/재등록/미상 — 결제 회원 전화가 lesson_records roster(성인강습·유소년강습 · ERP 강습
              명단) 에 있으면 재등록, 없으면 브로제이 결제 이력(9/1~기준일)에서 같은 회원·같은 팀 이전 결제
              유무로 가른다. 전화도 회원번호도 못 이으면 미상(2026-09-18 수정 — registry 는 문의 목록이라
              등록 여부를 모른다). day/month 날짜 비교는 KST 기준(_kst_day) — paid_at 에 +09:00 이 없는
              결제(강습 예약권 일부)도 하루 안 밀리게 잰다
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
TAG_TEAM = {"수영": 8, "PT": 9, "골프": 10, "스쿼시": 11, "체조&트램폴린": 12, "필라테스": 13, "영어뮤지컬": 14, "유료GX": 15}
TEAM_KEY_ROW = {"swim": 8, "pt": 9, "golf": 10, "squash": 11, "gym": 12, "pilates": 13, "musical": 14, "gxe": 15}
ROW_KEY = {v: k for k, v in TEAM_KEY_ROW.items()}   # 행 → sales_targets key
ROW_TAG = {v: k for k, v in TAG_TEAM.items()}       # 행 → 매출분류 태그(팀 이름 폴백)
OPS_TAG = "운영부"
LOCKER_TYPES = {"LOCKER_TICKET"}
REG_START = "2026-09-01"   # 브로제이 적재 시작일(GM 확정 2026-09-15) — 강습 신규/재등록 이력 조회 하한
# 매출분류(sales_tag_name)가 빈 결제 — 상품명으로 팀 행을 짚는다(2026-09-17 시포 · 실측 9/4 「(준)수영강습 아쿠아로빅 8회」
#   5건 1,210,000 이 분류 없이 총액에만 들어가 팀 합 ≠ 총액). 상품명에 낱말이 없으면 종전대로 unmapped(지어내지 않는다).
NAME_ROW = (("아쿠아", 8), ("수영", 8), ("P.T", 9), ("PT", 9), ("골프", 10), ("스쿼시", 11), ("체조", 12), ("트램폴린", 12),
            ("필라테스", 13), ("뮤지컬", 14), ("GX", 15))


def _row_by_name(name):
    n = str(name or "")
    for word, row in NAME_ROW:
        if word.lower() in n.lower():
            return row
    return None


def _money(n):
    return format(int(n), ",")


def _digits(v):
    return re.sub(r"\D", "", str(v or ""))


def _mid_mask(v):
    """010-****-5691 꼴(코드베이스 관례 · reconcile_dual_write.py 참조) — 가운데를 가리고 앞3·뒤4만 남긴다.
    8자리 미만은 원본 그대로(가릴 게 없다)."""
    d = _digits(v)
    if len(d) < 8:
        return str(v or "")
    return d[:3] + "-****-" + d[-4:]


def _reg_class_label(cls):
    """members.reg_class 문자열 → 신규/재등록/미상 — N7~N10 분류(aggregate)와 같은 규칙."""
    cls = str(cls or "")
    if not cls:
        return "미상"
    if "신규" in cls or "대기" in cls:
        return "신규"
    return "재등록"


def _kind_of(cell):
    if cell == 6:
        return "회원권"
    if cell == 7:
        return "옵션"
    if cell and cell >= 8:
        return "강습"
    return "기타"


def _cell_of(tag, ptype, product_name, tags):
    """매출분류·상품유형·상품명 → 보고탭 행(6~15) — aggregate 의 칸 판정 그 자체(한 곳에서만 정의)."""
    if tag == OPS_TAG:
        return 7 if ptype in LOCKER_TYPES else 6
    if tag in tags:
        return tags[tag]
    if not tag:
        return _row_by_name(product_name)
    return None


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


def _team_names(repo_dir=REPO_DIR):
    """행(8~15)→팀 이름(사람이 읽는 name) — sales_targets.json teams[].name 그대로. 못 읽으면 매출분류 태그를 이름으로."""
    p = os.path.join(repo_dir, "status", "sales_targets.json")
    try:
        with open(p, encoding="utf-8") as f:
            by_key = {t.get("key"): t.get("name") for t in (json.load(f).get("teams") or [])}
        return {row: by_key.get(key) or ROW_TAG.get(row, "") for row, key in ROW_KEY.items()}
    except Exception:
        return dict(ROW_TAG)


def _day_of(rec):
    return str(rec.get("paid_at") or "")[:10]


_TZ_RE = re.compile(r"([+-]\d{2}:?\d{2}|Z)$")


def _kst_day(paid_at):
    """paid_at → KST 날짜(YYYY-MM-DD) — +09:00 이 아닌 시간대(UTC 등)로 온 값도 KST 로 바꿔 잰다(2026-09-18
    실측: 강습 예약권 결제 일부가 +09:00 없이 와 day_of 앞10자 슬라이스가 하루 밀렸다 — lists.lesson.day 텅 빔).
    시간대 표기가 없거나 이미 +09:00 이면 _day_of 와 같은 앞 10자 슬라이스(기존 동작 그대로 — day/month 22칸은
    안 건드린다)."""
    s = str(paid_at or "")
    if not s:
        return ""
    m = _TZ_RE.search(s)
    if not m or m.group(1) in ("+09:00", "+0900"):
        return s[:10]
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(KST).strftime("%Y-%m-%d")
    except ValueError:
        return s[:10]


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
    daily = {}   # 날짜별 총매출(환불 제외) — 보고 1면 「일 단위 최근 7일」 막대가 일자탭 대신 읽는다(시트 0칸)
    day_pays = []      # lists.registered 원본 — 기준일 결제(환불 제외) 전부
    lesson_pays = []   # lists.lesson 원본 — 강습 8팀(행 8~15) 결제 전부(그달 1일~기준일)
    for p in payments:
        d = _day_of(p)
        if not d or d > ref_date:
            continue
        amt = int(p.get("total_payment_price") or 0)
        is_day = d == ref_date
        tag = str(p.get("sales_tag_name") or "")
        ptype = str(p.get("product_type") or "")
        if str(p.get("history_type") or "") == "REFUND":
            # N11 「환불」 = 시트와 같은 뜻(운영부 회원권·옵션 환불만) — 강습 예약권 환불(2026-09-16 체조 2건 -418,000)이
            #   여기 실려 GM 이 「어떻게 생긴 값인지 모르겠다」(2026-09-17). 팀 매출은 결제 전액 기준이라 환불을 빼지 않는다.
            if is_day and tag == OPS_TAG:
                refund_day += amt
            continue
        daily[d] = daily.get(d, 0) + amt
        cell = _cell_of(tag, ptype, p.get("product_name"), tags)
        if cell is None:
            unmapped[tag or "(분류없음)"] = unmapped.get(tag or "(분류없음)", 0) + amt
        month["J4"] += amt
        if cell:
            month["J%d" % cell] += amt
        member_id = str(p.get("member_id") or "")
        if cell and cell >= 8:
            # is_day 는 _kst_day 로 따로 잰다(위 is_day 는 _day_of 앞10자 그대로 — I4·N7~N12 22칸은 안 건드린다).
            # 강습 예약권 결제 일부가 paid_at 에 +09:00 없이 와 _day_of 슬라이스가 하루 밀렸었다(2026-09-18 실측).
            lesson_pays.append({"cell": cell, "member_id": member_id, "phone": phone_of_member.get(member_id, ""),
                                 "amt": amt, "is_day": _kst_day(p.get("paid_at")) == ref_date,
                                 "paid_at": p.get("paid_at")})
        if is_day:
            day["I4"] += amt
            if cell:
                day["I%d" % cell] += amt
            day_pays.append({"cell": cell, "member_id": member_id, "amt": amt, "tag": tag, "ptype": ptype,
                              "product_name": p.get("product_name"), "paid_at": p.get("paid_at")})
            # 신규/재등록 = 회원권 칸(cell 6) 결제 전부 — MEMBERSHIP 만 세던 것을 FACILITY_TICKET(플래티넘+골프 등)까지.
            #   등록분류 「대기」(시작일이 앞날인 신규)도 신규다. 2026-09-16 실측: 시트 신규 2명 7,000,000 · 재등록 1명 3,230,000
            #   인데 서버는 신규 0 · 재등록 3,600,000 — FACILITY_TICKET 2건 누락 + 「대기」를 재등록으로 셈(GM 2026-09-17 지적).
            if cell == 6:
                cls = members_by_phone.get(phone_of_member.get(member_id, ""))
                if cls is None:
                    unmatched += 1
                elif "재등록" in cls:
                    re_amt += amt
                    re_n += 1
                elif "신규" in cls or "대기" in cls:
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
                                    "new": [new_n, new_amt], "re": [re_n, re_amt], "daily": daily,
                                    "day_pays": day_pays, "lesson_pays": lesson_pays},
            "unmapped": unmapped, "unmatched_membership": unmatched, "payments": len(payments)}


def _registered_list(day_pays, team_names, member_info_by_phone, phone_of_member, snap_name_by_id):
    """lists.registered — 기준일 결제(환불 제외) 전부. 이름·분류는 전화로 members 를 이어(신규/재등록/미상),
    못 이으면 브로제이 회원 스냅샷 이름만 붙인다(지어내지 않는다)."""
    out = []
    for p in day_pays:
        phone = phone_of_member.get(p["member_id"], "")
        info = member_info_by_phone.get(phone)
        if info:
            name, reg_class = info["name"] or snap_name_by_id.get(p["member_id"], ""), _reg_class_label(info["reg_class"])
        else:
            name, reg_class = snap_name_by_id.get(p["member_id"], ""), "미상"
        cell = p["cell"]
        out.append({"name": name, "phone_masked": _mid_mask(phone), "reg_class": reg_class, "kind": _kind_of(cell),
                     "team": team_names.get(cell, "") if cell and cell >= 8 else "",
                     "product": p.get("product_name") or p.get("ptype") or "", "amount": p["amt"],
                     "paid_at": p.get("paid_at") or ""})
    return out


def _loss_list(mem_rows, ref_date):
    """lists.loss — members.loss_date == 기준일."""
    return [{"name": m["name"] or "", "phone_masked": _mid_mask(m["phone"]), "kind": m["kind"] or "",
             "product": m["program"] or ""} for m in mem_rows if str(m["loss_date"] or "")[:10] == ref_date]


def _contact_list(mem_rows, ref_date):
    """lists.contact — members.reg_consult_date == 기준일 또는 재등록예약목록(reg_reservation) 안의 날짜 항목.
    한 회원당 먼저 걸리는 것 하나만(3칸 미러가 이미 재등록예약목록 첫 항목을 담아 이중집계를 막는다)."""
    out = []
    for m in mem_rows:
        if str(m["reg_consult_date"] or "")[:10] == ref_date:
            out.append({"name": m["name"] or "", "phone_masked": _mid_mask(m["phone"]),
                        "consult_date": m["reg_consult_date"], "consult_time": m["reg_consult_time"] or "",
                        "note": m["reg_consult_note"] or ""})
            continue
        try:
            arr = json.loads(str(m["reg_reservation"] or "").strip() or "[]")
        except Exception:
            arr = []
        if not isinstance(arr, list):
            continue
        for it in arr:
            if isinstance(it, dict) and str(it.get("date") or "")[:10] == ref_date:
                out.append({"name": m["name"] or "", "phone_masked": _mid_mask(m["phone"]),
                            "consult_date": it.get("date") or "", "consult_time": it.get("time") or "",
                            "note": it.get("note") or ""})
                break
    return out


LESSON_BASIS = ("ERP 강습 명단(roster) 전화 일치=재등록 · 없으면 브로제이 이력(9/1~기준일 · 같은 회원·같은 팀 "
                "이전 결제 있으면 재등록) · 전화도 회원번호도 못 이으면 미상")


def _classify_lesson(phone, member_id, cell, paid_at, roster_phones, hist_first_paid):
    """전화가 ERP 강습 명단(roster)에 있으면 재등록 · 없으면 브로제이 결제 이력(그 전 결제 유무) · 전화도
    회원번호도 없으면 미상(지어내지 않는다)."""
    if not phone and not member_id:
        return "미상"
    if phone and phone in roster_phones:
        return "재등록"
    first = hist_first_paid.get((member_id, cell))
    return "재등록" if (first and first < _kst_day(paid_at)) else "신규"


def _lesson_lists(lesson_pays, roster_phones, hist_first_paid, team_names):
    """lists.lesson — 강습 8팀 신규/재등록/미상(건수·금액) day(기준일)·month(그달 1일~기준일)."""
    day, month = {}, {}
    for p in lesson_pays:
        cell = p["cell"]
        team = team_names.get(cell, "행%d" % cell)
        cls = _classify_lesson(p["phone"], p["member_id"], cell, p.get("paid_at"), roster_phones, hist_first_paid)
        key = {"신규": "new", "재등록": "re", "미상": "unknown"}[cls]
        for scope, cond in ((month, True), (day, p["is_day"])):
            if not cond:
                continue
            b = scope.setdefault(team, {"new": 0, "re": 0, "unknown": 0, "new_amt": 0, "re_amt": 0, "unknown_amt": 0})
            b[key] += 1
            b[key + "_amt"] += p["amt"]
    return {"day": day, "month": month, "basis": LESSON_BASIS}


def _lesson_roster_class(conn, tenant):
    """{전화} — lesson_records kind=roster(성인강습·유소년강습) 의 ERP 강습 명단(화면 membership.html 이 읽는
    바로 그 데이터 · 행 모양 sport/name/phone/status/regCount). 전화가 여기 있으면 그 강습에 이미 다니는
    회원(재등록 후보). DB 조회 — compute() 전용, selftest 대상 아님."""
    out = set()
    for t in ("성인강습", "유소년강습"):
        r = conn.execute("SELECT data FROM lesson_records WHERE tenant_id=%s AND kind='roster' AND key=%s",
                          (tenant, t)).fetchone()
        if not r:
            continue
        d = json.loads(r["data"])
        for row in (d.get("roster") or []):
            if isinstance(row, dict):
                phone = _digits(row.get("phone"))
                if phone:
                    out.add(phone)
    return out


def _lesson_first_paid(conn, ref_date, tags, tenant):
    """{(member_id, 행): 가장 이른 결제일(KST)} — 브로제이 결제 이력(REG_START~기준일 · 환불 제외). roster 로
    못 가른 나머지를 「그 전 결제가 있었나」로 가른다. DB 조회 — compute() 전용, selftest 대상 아님."""
    rows = conn.execute(
        "SELECT data FROM brojay_records WHERE tenant_id=%s AND kind='sales' AND key BETWEEN %s AND %s",
        (tenant, REG_START, ref_date)).fetchall()
    out = {}
    for r in rows:
        d = json.loads(r["data"])
        lst = d.get("data") if isinstance(d, dict) else d
        if isinstance(lst, dict):
            lst = lst.get("data")
        for p in (lst or []):
            if not isinstance(p, dict) or str(p.get("history_type") or "") == "REFUND":
                continue
            cell = _cell_of(str(p.get("sales_tag_name") or ""), str(p.get("product_type") or ""),
                             p.get("product_name"), tags)
            if not cell or cell < 8:
                continue
            key = (str(p.get("member_id") or ""), cell)
            paid_d = _kst_day(p.get("paid_at"))
            if paid_d and (key not in out or paid_d < out[key]):
                out[key] = paid_d
    return out


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
        days_loaded = sorted(str(r["key"])[:10] for r in rows)
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
            "SELECT phone, reg_class, loss_date, name, kind, program, reg_consult_date, reg_consult_time,"
            " reg_consult_note, reg_reservation FROM members WHERE tenant_id=%s AND scope IN ('valid','ended')",
            (db.TENANT,)).fetchall()
        members_by_phone = {_digits(m["phone"]): str(m["reg_class"] or "") for m in mem if _digits(m["phone"])}
        loss_count = sum(1 for m in mem if str(m["loss_date"] or "")[:10] == ref_date)
        snap = conn.execute(
            "SELECT data FROM brojay_records WHERE tenant_id=%s AND kind='members' ORDER BY key DESC LIMIT 1",
            (db.TENANT,)).fetchone()
        phone_of_member, snap_name_by_id = {}, {}
        if snap:
            d = json.loads(snap["data"])
            lst = d.get("data") if isinstance(d, dict) else d
            if isinstance(lst, dict):
                lst = lst.get("data")
            for m in (lst or []):
                if isinstance(m, dict) and m.get("member_id"):
                    mid = str(m["member_id"])
                    phone_of_member[mid] = _digits(m.get("phone_number"))
                    snap_name_by_id[mid] = m.get("name") or ""
        tags = tag_rows()
        roster_phones = _lesson_roster_class(conn, db.TENANT)
        hist_first_paid = _lesson_first_paid(conn, ref_date, tags, db.TENANT)
    finally:
        conn.close()
    out = aggregate(payments, ref_date, tags, members_by_phone, phone_of_member, loss_count)
    out["raw"]["days_loaded"] = days_loaded
    out.update({"ref_date": ref_date, "_source": "brojay+erp", "members_joined": bool(phone_of_member)})
    try:
        member_info_by_phone = {}
        for m in mem:
            pd = _digits(m["phone"])
            if pd:
                member_info_by_phone.setdefault(pd, {"name": m["name"] or "", "reg_class": str(m["reg_class"] or "")})
        team_names = _team_names()
        out["lists"] = {
            "ref_date": ref_date,
            "registered": _registered_list(out["raw"]["day_pays"], team_names, member_info_by_phone,
                                            phone_of_member, snap_name_by_id),
            "loss": _loss_list(mem, ref_date),
            "contact": _contact_list(mem, ref_date),
            "lesson": _lesson_lists(out["raw"]["lesson_pays"], roster_phones, hist_first_paid, team_names),
        }
    except Exception:
        out["lists"] = {"ref_date": ref_date, "registered": [], "loss": [], "contact": [],
                         "lesson": {"day": {}, "month": {}, "basis": ""}}
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
        # 2026-09-17 추가 — 9/16 실사례: 플래티넘+골프(FACILITY_TICKET) 신규(등록분류 「대기」) · 재등록 FACILITY_TICKET · 강습 예약권 환불
        {"paid_at": "2026-09-15T15:00:00+09:00", "history_type": "PAYMENT", "product_type": "FACILITY_TICKET",
         "sales_tag_name": "운영부", "member_id": "G", "total_payment_price": 3400000},
        {"paid_at": "2026-09-15T15:10:00+09:00", "history_type": "PAYMENT", "product_type": "FACILITY_TICKET",
         "sales_tag_name": "운영부", "member_id": "H", "total_payment_price": 3230000},
        {"paid_at": "2026-09-15T20:00:00+09:00", "history_type": "REFUND", "product_type": "RESERVATION_TICKET",
         "sales_tag_name": "체조&트램폴린", "member_id": "I", "total_payment_price": -209000},
        {"paid_at": "2026-09-15T16:00:00+09:00", "history_type": "PAYMENT", "product_type": "RESERVATION_TICKET",
         "sales_tag_name": "", "member_id": "J", "total_payment_price": 242000, "product_name": "(준)수영강습 아쿠아로빅 8회"},   # 분류 없음 → 상품명으로 수영
    ]
    o = aggregate(pays, "2026-09-15", tags, {"01011112222": "신규", "01033334444": "대기", "01055556666": "재등록"},
                  {"A": "01011112222", "G": "01033334444", "H": "01055556666"}, loss_count=2)
    c = o["cells"]
    assert c["I4"] == "8,251,000", c["I4"]          # 회원권 100만+340만+323만 + 락커 12만 + 수영 20.9만+24.2만 + 요가 5만(분류 없음도 총액엔 포함)
    assert c["I6"] == "7,630,000" and c["I7"] == "120,000" and c["I8"] == "451,000" and c["I10"] == "0"   # 아쿠아로빅 242,000 이 수영 행으로
    assert c["J10"] == "330,000" and c["J4"] == "8,581,000"
    assert c["N7"] == "4,400,000" and c["N8"] == "2명", (c["N7"], c["N8"])     # 신규 100만 + 대기(신규) 340만
    assert c["N9"] == "3,230,000" and c["N10"] == "1명", (c["N9"], c["N10"])   # 재등록 FACILITY_TICKET 도 센다
    assert c["N11"] == "300,000" and c["N12"] == "2명"                          # 강습 예약권 환불(-209,000)은 N11 에 안 실린다
    assert o["unmapped"] == {"요가": 50000} and o["unmatched_membership"] == 0
    assert o["raw"]["daily"] == {"2026-09-15": 8251000, "2026-09-14": 330000}, o["raw"]["daily"]   # 환불·기준일 뒤는 빠진다
    o2 = aggregate(pays, "2026-09-15", tags, {}, {"A": "01011112222"})
    assert o2["unmatched_membership"] == 3 and o2["cells"]["N8"] == "0명"   # 원장에 없으면 지어내지 않는다(회원권 3건 전부 unmatched)
    assert tag_rows("/nonexistent") == TAG_TEAM

    # ── lists 4종(배 12523 2단계) — 작은 함수 단위로 가짜 행만 넣고 DB 없이 검사 ──
    assert _mid_mask("01012345678") == "010-****-5678" and _mid_mask("1234") == "1234"
    assert _reg_class_label("") == "미상" and _reg_class_label("재등록") == "재등록" and _reg_class_label("대기") == "신규"
    assert _kind_of(6) == "회원권" and _kind_of(7) == "옵션" and _kind_of(10) == "강습" and _kind_of(None) == "기타"
    assert _team_names("/nonexistent") == dict(ROW_TAG)

    team_names = {8: "수영팀", 10: "골프팀"}
    snap_names = {"B": "나비", "D": "다래", "J": "제이"}
    member_info = {"01011112222": {"name": "에이", "reg_class": "신규"}}
    reg_list = _registered_list(o["raw"]["day_pays"], team_names, member_info,
                                {"A": "01011112222", "G": "01033334444", "H": "01055556666"}, snap_names)
    assert len(reg_list) == 7, len(reg_list)
    a_rows = [r for r in reg_list if r["phone_masked"] == _mid_mask("01011112222")]
    assert len(a_rows) == 2 and a_rows[0]["name"] == "에이" and a_rows[0]["reg_class"] == "신규" and a_rows[0]["kind"] == "회원권"
    assert a_rows[1]["kind"] == "옵션"
    b_row = [r for r in reg_list if r["amount"] == 209000][0]
    assert b_row["name"] == "나비" and b_row["reg_class"] == "미상" and b_row["team"] == "수영팀"   # 원장에 없으면 미상
    d_row = [r for r in reg_list if r["amount"] == 50000][0]
    assert d_row["kind"] == "기타" and d_row["team"] == ""   # 분류 못 지은 결제도 빠뜨리지 않는다

    lp = [
        {"cell": 8, "member_id": "X", "phone": "01099998888", "amt": 100000, "is_day": True, "paid_at": "2026-09-15T10:00:00+09:00"},
        {"cell": 8, "member_id": "Y", "phone": "01000000000", "amt": 200000, "is_day": True, "paid_at": "2026-09-15T10:00:00+09:00"},
        {"cell": 8, "member_id": "Y", "phone": "01000000000", "amt": 150000, "is_day": False, "paid_at": "2026-09-10T10:00:00+09:00"},
        {"cell": 8, "member_id": "", "phone": "", "amt": 50000, "is_day": True, "paid_at": "2026-09-15T09:00:00+09:00"},   # 전화·회원번호 둘 다 없음
    ]
    lesson = _lesson_lists(lp, {"01099998888"}, {("Y", 8): "2026-09-10"}, {8: "수영팀"})
    assert lesson["basis"] == LESSON_BASIS
    assert lesson["day"]["수영팀"] == {"new": 0, "re": 2, "unknown": 1, "new_amt": 0, "re_amt": 300000, "unknown_amt": 50000}, lesson["day"]
    assert lesson["month"]["수영팀"] == {"new": 1, "re": 2, "unknown": 1, "new_amt": 150000, "re_amt": 300000,
                                        "unknown_amt": 50000}, lesson["month"]
    # _kst_day — +09:00 은 앞10자 그대로, UTC(+00:00·Z)는 KST 로 밀려 날짜가 바뀔 수 있다
    assert _kst_day("2026-09-17T10:00:00+09:00") == "2026-09-17"
    assert _kst_day("2026-09-16T21:30:00+00:00") == "2026-09-17"   # UTC 21:30 = KST 06:30(다음날)
    assert _kst_day("2026-09-16T21:30:00Z") == "2026-09-17"
    assert _kst_day("") == "" and _kst_day("이상값") == "이상값"[:10]

    mem_rows = [
        {"name": "김로스", "phone": "01011112222", "loss_date": "2026-09-15", "kind": "MEMBERSHIP", "program": "요가",
         "reg_consult_date": None, "reg_consult_time": None, "reg_consult_note": None, "reg_reservation": None},
        {"name": "박컨택", "phone": "01022223333", "loss_date": None, "kind": "", "program": "",
         "reg_consult_date": "2026-09-15", "reg_consult_time": "14:00", "reg_consult_note": "메모", "reg_reservation": None},
        {"name": "최예약", "phone": "01033334444", "loss_date": None, "kind": "", "program": "",
         "reg_consult_date": None, "reg_consult_time": None, "reg_consult_note": None,
         "reg_reservation": json.dumps([{"date": "2026-09-10", "time": "10:00", "note": "옛날"},
                                        {"date": "2026-09-15", "time": "11:00", "note": "다음달"}], ensure_ascii=False)},
    ]
    assert _loss_list(mem_rows, "2026-09-15") == [
        {"name": "김로스", "phone_masked": _mid_mask("01011112222"), "kind": "MEMBERSHIP", "product": "요가"}]
    contact = _contact_list(mem_rows, "2026-09-15")
    assert len(contact) == 2, contact
    assert contact[0]["name"] == "박컨택" and contact[0]["consult_date"] == "2026-09-15" and contact[0]["consult_time"] == "14:00"
    assert contact[1]["name"] == "최예약" and contact[1]["consult_date"] == "2026-09-15" and contact[1]["note"] == "다음달"
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    arg = next((a for a in sys.argv[1:] if re.match(r"^\d{4}-\d{2}-\d{2}$", a)), None)
    res = compute(arg)
    print(json.dumps(res, ensure_ascii=False, indent=1) if res else "결제 적재 없음")
