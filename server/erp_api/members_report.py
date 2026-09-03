# -*- coding: utf-8 -*-
"""매출회원현황보고 2페이지용 집계 라우트 (읽기 전용 · 배 943).

members·inquiries 미러(sqlite)에서 GAS 액션 4개와 같은 모양으로 센다:
  /api/report/member_active_summary · cpo_today_stats · cpo_churn_stats · member_registered_list
판정 규칙은 GAS 원본(.deploy-funnel-v2/Survey.js)을 그대로 옮겼고, 함수마다 원본 위치를 적어 둔다.
stage_funnel · lesson_stats 는 강습 시트·폼 시트가 미러에 없어 화면이 GAS 를 그대로 부른다.
app.py 가 맨 끝에서 include_router 로 붙인다 — app.py 본문은 건드리지 않는다.

자체점검: python3 members_report.py --selftest (임시 DB · 네트워크 없음)
"""
import json
import os
import re
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

DB_PATH = os.environ.get("ERP_DB", "/srv/erp/erp.db")
SOURCE = "sheet-mirror"
KST = timezone(timedelta(hours=9))
LOSS_TAGS = {"LOSS", "환불", "양도LOSS"}          # Survey.js:136 MEMBER_LOSS_TAGS_
MEMBER_SHEET_SCOPES = ("valid", "ended")           # 유효회원 탭 = 두 scope 의 합
TYPE_KNOWN = ("멤버십", "입주민", "중단기", "보증금", "FAN VIP", "법인")   # Survey.js member_active_summary MA_KNOWN
TYPE_TYPO = {"맴버십": "멤버십", "멥버십": "멤버십"}
DUP_DELETED_STATUS = "중복(삭제)"                  # Survey.js:2147 MI_DUP_DELETED_STATUS

router = APIRouter(prefix="/api/report")


def _today():
    return datetime.now(KST).strftime("%Y-%m-%d")


def _s(v):
    return str(v if v is not None else "").strip()


def _iso(v):
    """Survey.js:2234 _miToISO_ — 날짜 문자열을 YYYY-MM-DD 로. 못 읽으면 원문 그대로(GAS 와 같음)."""
    s = _s(v)
    m = re.search(r"(\d{4})[.\-/]?\s*(\d{1,2})[.\-/]?\s*(\d{1,2})", s)
    return "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3))) if m else s


def _parse_int(v):
    m = re.match(r"\s*[-+]?\d+", str(v if v is not None else ""))
    return int(m.group()) if m else None


def _rem(v):
    """Survey.js:147 _memberIsValid_ 의 잔여일 파싱 — 숫자·'-' 만 남기고 parseInt. 빈값·'-' 는 NaN(None)."""
    raw = re.sub(r"[^0-9\-]", "", str(v if v is not None else ""))
    return None if raw in ("", "-") else _parse_int(raw)


def is_new_registration(reg_class, reg_class2, reg_seq):
    """Survey.js:4665 _isNewRegistration_ — 신규 등록 판정의 단 하나의 자리를 그대로 옮김."""
    if "재등록" in _s(reg_class2):
        return False
    m = re.search(r"\d+", _s(reg_seq))
    if m and int(m.group()) >= 2:
        return False
    c = _s(reg_class)
    if c:
        return c == "신규"
    n = _parse_int(reg_seq)
    return not (n is not None and n > 1)


def _col(row, *wants):
    """GAS _maIdx/_crIdx/_rlIdx 관례 — 공백 지운 머리글에 부분일치하는 첫 칸. 후보를 순서대로 시도."""
    for w in wants:
        w = re.sub(r"\s+", "", w)
        for k in row:
            if w in k:
                return k
    return None


def _get(row, *wants):
    k = _col(row, *wants)
    return _s(row[k]) if k else ""


def _conn():
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % DB_PATH, uri=True)
    except sqlite3.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(conn, scopes):
    """scope 별 미러 행을 시트 행 순서로. 머리글은 공백을 지워 GAS 의 부분일치 규칙과 맞춘다."""
    out = []
    for scope in scopes:
        for r in conn.execute("SELECT data FROM members WHERE scope=? ORDER BY json_extract(data,'$.rowIndex')", (scope,)):
            d = json.loads(r["data"])
            out.append((scope, {re.sub(r"\s+", "", str(k)): v for k, v in d.items()}))
    return out


def _archive_count(conn):
    """Survey.js:139 _lossArchiveCount_ — LOSS보관 탭 행수. 미러에선 scope=archive 건수."""
    return conn.execute("SELECT COUNT(*) FROM members WHERE scope='archive'").fetchone()[0]


def _loss_date(row):
    # LOSS일자→이탈일→해지일→종료일 (Survey.js member_active_summary maLossI 체인)
    return _iso(_get(row, "LOSS일자", "이탈일", "해지일", "종료일"))


# ── 라우트 ────────────────────────────────────────────────────────────────

@router.get("/member_active_summary")
def member_active_summary():
    """Survey.js:10421 member_active_summary."""
    today = _today()
    month_start, year_start = today[:8] + "01", today[:4] + "-01-01"
    res = {"ok": True, "action": "member_active_summary", "date": today,
           "validTotal": 0, "endedTotal": 0, "waitingCount": 0,
           "typeCounts": {t: 0 for t in TYPE_KNOWN + ("기타",)},
           "lossPeriods": {"day": 0, "month": 0, "year": 0, "total": 0},
           "waitPeriods": {"day": 0, "month": 0, "year": 0, "total": 0}, "_source": SOURCE}

    def bump(bucket, iso):
        bucket["total"] += 1
        if not iso:
            return
        if iso == today:
            bucket["day"] += 1
        if month_start <= iso <= today:
            bucket["month"] += 1
        if year_start <= iso <= today:
            bucket["year"] += 1

    conn = _conn()
    with closing(conn):
        for scope, row in _rows(conn, MEMBER_SHEET_SCOPES):
            if scope == "ended":
                res["endedTotal"] += 1
                bump(res["lossPeriods"], _loss_date(row))
                continue
            res["validTotal"] += 1
            t = _get(row, "회원구분")
            t = TYPE_TYPO.get(t, t)
            res["typeCounts"][t if t in TYPE_KNOWN else "기타"] += 1
            start = _get(row, "시작일자")
            started = bool(re.match(r"\d{4}-\d{2}-\d{2}", start))
            wait_col = next((k for k in row if k == "대기"), None)
            if wait_col and _s(row[wait_col]):
                is_wait = (not started) or start[:10] > today
            else:
                is_wait = any(_get(row, k) in ("대기", "재등록대기") for k in ("등록분류", "재등록분류") if _col(row, k))
            if is_wait:
                res["waitingCount"] += 1
                bump(res["waitPeriods"], start[:10] if started else "")
        res["endedTotal"] += _archive_count(conn)
    return res


@router.get("/cpo_today_stats")
def cpo_today_stats():
    """Survey.js:10810 cpo_today_stats."""
    today = _today()
    month = today[:7]
    r = {"ok": True, "date": today, "todayInquiry": 0, "monthInquiry": 0, "todayReg": 0, "monthReg": 0,
         "memberActive": 0, "memberCorp": 0, "memberEnded": 0, "todayLoss": 0, "monthLoss": 0,
         "lossDated": True, "_source": SOURCE}
    conn = _conn()
    with closing(conn):
        # 문의: 26년 신규문의 — 멤버십(플래티넘·노블레스·미기재)만, 소프트 삭제 제외
        for q in conn.execute("SELECT data FROM inquiries WHERE type='멤버십'"):
            d = json.loads(q["data"])
            if _s(d.get("status")) == DUP_DELETED_STATUS:
                continue
            pg = _s(d.get("program"))
            if pg and "플래티넘" not in pg and "노블레스" not in pg:
                continue
            iso = _iso(d.get("timestamp"))
            if iso == today:
                r["todayInquiry"] += 1
            if iso[:7] == month:
                r["monthInquiry"] += 1
        for scope, row in _rows(conn, MEMBER_SHEET_SCOPES):
            reg = _iso(_get(row, "등록일자"))
            if is_new_registration(_get(row, "등록분류"), _get(row, "재등록분류"), _get(row, "등록회차")):
                if reg == today:
                    r["todayReg"] += 1
                if reg[:7] == month:
                    r["monthReg"] += 1
            if scope == "valid":
                r["memberActive"] += 1
                continue
            r["memberEnded"] += 1
            ld = _loss_date(row)
            if ld == today:
                r["todayLoss"] += 1
            if ld[:7] == month:
                r["monthLoss"] += 1
        # 법인: LOSS일자 없고 종료일자가 안 지난 행만 (2026-08-13 GM)
        for _, row in _rows(conn, ("corp",)):
            if _get(row, "LOSS일자")[:10]:
                continue
            end = _get(row, "종료일자")[:10]
            if end and end < today:
                continue
            r["memberCorp"] += 1
        r["memberEnded"] += _archive_count(conn)
    return r


@router.get("/cpo_churn_stats")
def cpo_churn_stats():
    """Survey.js:10943 cpo_churn_stats — LOSS 판정(태그 또는 잔여일<0)은 _memberIsValid_ 의 반대와 같아 scope 로 가른다."""
    month = _today()[:7]
    active, loss, month_loss, renew = 0, 0, 0, []
    conn = _conn()
    with closing(conn):
        for scope, row in _rows(conn, MEMBER_SHEET_SCOPES):
            if scope == "ended":
                loss += 1
                if _loss_date(row)[:7] == month:
                    month_loss += 1
                continue
            active += 1
            rem = _rem(_get(row, "잔여일"))
            if rem is not None and 0 <= rem <= 30:
                renew.append({"name": _get(row, "회원명"), "rem": rem, "program": _get(row, "등급", "상품", "프로그램")})
        loss += _archive_count(conn)
    renew.sort(key=lambda x: x["rem"])
    total, mtotal = active + loss, active + month_loss
    return {"ok": True, "activeCount": active, "lossCount": loss,
            "lossRate": round(loss / total * 100, 1) if total else 0,
            "monthLossCount": month_loss,
            "monthLossRate": round(month_loss / mtotal * 100, 1) if mtotal else 0,
            "renewCount": len(renew), "renewSoon": renew[:200], "_source": SOURCE}


@router.get("/member_registered_list")
def member_registered_list(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    newOnly: Optional[str] = None,
):
    """Survey.js:8918 member_registered_list — 등록일자 기간 목록. newOnly=1 이면 is_new_registration 으로 거른다."""
    new_only = str(newOnly or "") == "1"
    out = []
    conn = _conn()
    with closing(conn):
        for _, row in _rows(conn, MEMBER_SHEET_SCOPES):
            reg = _iso(_get(row, "등록일자"))
            if not reg or (from_ and reg < from_) or (to and reg > to):
                continue
            item = {
                "rowIndex": row.get("rowIndex"),
                "name": _get(row, "회원명"),
                "phone": _get(row, "휴대폰", "연락처", "전화"),
                "program": _get(row, "수강반종목", "종목명", "회원권", "상품", "프로그램"),
                "regDate": reg,
                "regClass": _get(row, "등록분류"),
                "regClass2": _get(row, "재등록분류"),
                "regSeq": _get(row, "등록회차"),
            }
            if new_only and not is_new_registration(item["regClass"], item["regClass2"], item["regSeq"]):
                continue
            out.append(item)
    out.sort(key=lambda x: x["regDate"], reverse=True)
    return {"ok": True, "count": len(out), "data": out, "newOnly": new_only, "_source": SOURCE}


# ── 자체점검 ──────────────────────────────────────────────────────────────

def selftest():
    global DB_PATH
    assert is_new_registration("신규", "", "1") and not is_new_registration("신규", "", "2")
    assert not is_new_registration("", "재등록", "") and not is_new_registration("재등록", "", "1")
    assert is_new_registration("", "", "") and not is_new_registration("", "", "3")
    assert _iso("2026. 9. 3") == "2026-09-03" and _rem("-3일") == -3 and _rem("") is None
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_selftest_report.db")
    if os.path.exists(path):
        os.remove(path)
    c = sqlite3.connect(path)
    c.executescript("CREATE TABLE members(member_no TEXT PRIMARY KEY, scope TEXT, data TEXT);"
                    "CREATE TABLE inquiries(id TEXT PRIMARY KEY, type TEXT, data TEXT);")
    today = _today()
    rows = [
        ("M00001", "valid", {"rowIndex": 2, "회원명": "홍길동", "회원\n구분": "멤버십", "등록 분류": "신규", "등록\n회차": "1",
                             "등록\n일자": today, "시작\n일자": today, "잔여일\n(일)": "10", "LOSS\n일자": "", "대기": ""}),
        ("M00002", "valid", {"rowIndex": 3, "회원명": "김철수", "회원\n구분": "맴버십", "등록 분류": "대기", "등록\n회차": "2",
                             "등록\n일자": today, "시작\n일자": "", "잔여일\n(일)": "", "LOSS\n일자": "", "대기": ""}),
        ("M00003", "ended", {"rowIndex": 4, "회원명": "박영희", "회원\n구분": "입주민", "등록 분류": "재등록", "등록\n회차": "3",
                             "등록\n일자": "2025-01-01", "잔여일\n(일)": "-5", "LOSS\n일자": today}),
        ("M00004", "corp", {"rowIndex": 2, "회원명": "법인A", "종료\n일자": "2099-12-31", "LOSS\n일자": ""}),
        ("M00005", "corp", {"rowIndex": 3, "회원명": "법인B", "종료\n일자": "2020-01-01", "LOSS\n일자": ""}),
        ("M00006", "archive", {"rowIndex": 2, "회원명": "옛회원"}),
    ]
    c.executemany("INSERT INTO members VALUES (?,?,?)", [(n, s, json.dumps(d, ensure_ascii=False)) for n, s, d in rows])
    c.executemany("INSERT INTO inquiries VALUES (?,?,?)", [
        ("a", "멤버십", json.dumps({"timestamp": today + " 10:00:00", "program": "플래티넘", "status": "컨택중"})),
        ("b", "멤버십", json.dumps({"timestamp": today + " 11:00:00", "program": "골프", "status": "컨택중"})),
        ("c", "멤버십", json.dumps({"timestamp": today + " 12:00:00", "program": "", "status": DUP_DELETED_STATUS})),
        ("d", "성인강습", json.dumps({"timestamp": today + " 12:00:00", "program": "플래티넘", "status": ""})),
    ])
    c.commit(); c.close()
    DB_PATH = path
    try:
        a = member_active_summary()
        assert (a["validTotal"], a["endedTotal"], a["waitingCount"]) == (2, 2, 1), a
        assert a["typeCounts"]["멤버십"] == 2 and a["lossPeriods"]["day"] == 1, a
        t = cpo_today_stats()
        assert (t["todayInquiry"], t["todayReg"], t["memberActive"], t["memberCorp"], t["memberEnded"], t["todayLoss"]) == (1, 1, 2, 1, 2, 1), t
        cz = cpo_churn_stats()
        assert (cz["activeCount"], cz["lossCount"], cz["monthLossCount"], cz["renewCount"]) == (2, 2, 1, 1), cz
        rl = member_registered_list(from_=today[:8] + "01", to=today, newOnly="1")
        assert [x["name"] for x in rl["data"]] == ["홍길동"], rl
        assert member_registered_list(from_=today[:8] + "01", to=today)["count"] == 2
    finally:
        os.remove(path)
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else 2)
