"""월간 운영 보고 원장 갱신 — 그 달 수치를 원장에서 직접 세어 status/monthly_report_ledger.json 에 쌓는다.

왜 있나
    회장님 월간 보고(현황·계획 A3 2장)의 숫자를 매달 사람이 손으로 옮겨 적고 있었다. 옮겨 적는 순간
    ①지난달 값이 화면 갱신과 함께 사라지고 ②다음 달에 같은 일을 또 한다. 원장에 한 줄씩 쌓아 두면
    그 달에 무엇이었는지가 남고(기록), 달을 바꿔 견줄 수 있으며(추적), 해가 지나도 지워지지 않는다(누적).
    GM 지시 2026-08-28 — "이런건 매월마다 누적하고 추적하고 기록하는게 맞다".

무엇을 채우나 / 무엇을 안 채우나
    채운다  = 매출 · 회원 · 문의 · 접수 · 점검 · 과제·로드맵 진척  (전부 원장 직접 카운트)
    안 채운다 = narrative(본질 한 줄·좋아진 것·손대야 할 것) · decision · watchlist
                → 그건 판단이라 기계가 쓸 수 없다. 그 달 담당이 쓴다. 이 스크립트는 절대 덮어쓰지 않는다.

원칙
    · 못 잰 항목은 None 으로 두고 unmeasured 에 사유를 남긴다 — 0 으로 채우지 않는다(약속 L25).
    · closed=true 로 닫힌 달은 건드리지 않는다(--force 로만 열림).
    · 새 조회를 만들지 않는다 — 이미 도는 스냅샷·수집기를 그대로 읽는다(약속 L21).

쓰는 법
    python scripts/monthly_report_snapshot.py                 # 이번 달, 드라이런(원장 안 씀)
    python scripts/monthly_report_snapshot.py --write         # 이번 달 확정 반영
    python scripts/monthly_report_snapshot.py --month 2026-08 --write --close   # 마감 후 닫기
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

LEDGER = os.path.join(REPO, "status", "monthly_report_ledger.json")
KPI_SNAP = os.path.join(REPO, "status", "home_kpi_snapshot.json")
MEMBER_SNAP = os.path.join(REPO, "status", "member_active_snapshot.json")
MEMBER_ENDED = os.path.join(REPO, "status", "member_ended_snapshot.json")
LESSON_SNAP = os.path.join(REPO, "status", "inquiry_snapshot_lesson.json")
OPS_PLAN = os.path.join(REPO, "status", "monthly_ops_plan.json")

# 점검 집계 GAS — coo_registry.CHECK_API 와 같은 곳(주소를 여기 복제하지 않고 그 모듈에서 가져온다)
KST = timezone(timedelta(hours=9))


def _now():
    return datetime.now(KST)


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[경고] {os.path.basename(path)} 읽기 실패 — {e}")
        return None


def _month_of(v) -> str:
    return str(v or "")[:7]


# ─── 매출 ────────────────────────────────────────────────────────────────────
def collect_sales(month: str) -> dict:
    """당월 매출은 매출 원장 라이브(sales_month), 연 누계·부문별은 home 스냅샷에서.
    두 소스의 조회 시각이 달라 값이 몇십만 원 어긋날 수 있다 — 어긋난 채로 두고 보고서 각주가 그 사실을 적는다."""
    out = {"month": None, "year_cum": None, "by_segment": {}}
    snap = _load(KPI_SNAP) or {}
    s = ((snap.get("data") or {}).get("sales")) or {}
    if _month_of(snap.get("generated_at_kst")) == month:
        out["year_cum"] = s.get("year")
        out["year_target"] = s.get("yearTarget")
        out["year_rate_pct"] = s.get("yearRate")
        for b in (s.get("breakdown") or []):
            if b.get("name") is not None and b.get("month") is not None:
                out["by_segment"][b["name"]] = b["month"]
        out["month"] = s.get("month")

    # 당월분은 원장 라이브가 더 최신 — 실패하면 스냅샷 값을 그대로 둔다(지어내지 않음)
    if month == _now().strftime("%Y-%m"):
        try:
            import erp_status_publisher as E

            live = E.fetch_sales_month_in_progress()
            if live and live.get("value"):
                out["month_ledger_sheet"] = int(live["value"])   # 말일탭 값(주차 제외) — 대조용으로만 남긴다
                out["asOf"] = live.get("asOf")
        except Exception as e:
            print(f"[경고] 당월 매출 라이브 조회 실패 — {e} (스냅샷 값 유지)")

    # ★매출의 정의 = 부문 전부의 합(주차·뮤지컬 포함) — GM 확정 2026-08-28.
    #   같은 8월이 5.23억(주차·뮤지컬 뺀 값)·5.451억(말일탭·주차 뺀 값)·5.476억(전부 합)으로
    #   세 값이던 것을 여기 한 줄로 못박는다. 무엇을 넣는지는 공식값이라 코드가 정하지 않고 GM 이 정한다.
    if out["by_segment"]:
        out["month"] = sum(out["by_segment"].values())
        out["month_basis"] = "부문 전부 합(주차·뮤지컬 포함) · GM 확정 2026-08-28"
    return out


# ─── 회원 ────────────────────────────────────────────────────────────────────
def _reg_class(row) -> str:
    """등록 분류를 신규/재등록/그 밖으로 접는다. L재등록은 재등록에 포함(회원 입장에서 같은 갱신)."""
    v = str(row.get("등록 분류") or "").strip()
    if v == "신규":
        return "신규"
    if v in ("재등록", "L재등록"):
        return "재등록"
    return v or "(빈칸)"


def collect_member(month: str) -> dict:
    d = _load(MEMBER_SNAP) or {}
    rows = d.get("rows") or []
    if not rows:
        return {}
    nxt = (datetime.strptime(month + "-01", "%Y-%m-%d") + timedelta(days=32)).strftime("%Y-%m")

    reg = [r for r in rows if _month_of(r.get("등록\n일자")) == month]
    exp = [r for r in rows if _month_of(r.get("종료\n일자")) == nxt]
    contact_cols = [c for c in rows[0] if "재등록" in c]
    contacted = [r for r in exp if any(str(r.get(c) or "").strip() for c in contact_cols)]

    # 이탈(LOSS)은 유효회원 스냅샷에 없다 — 종료 스냅샷을 따로 읽는다. LOSS 일자가 비었으면 종료 일자로 떨어진다.
    prev = (datetime.strptime(month + "-01", "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m")
    loss = loss_prev = None
    price = None
    ended = (_load(MEMBER_ENDED) or {}).get("rows") or []
    if ended:
        lc = collections.Counter(
            _month_of(r.get("LOSS\n일자") or r.get("종료\n일자")) for r in ended)
        loss, loss_prev = lc.get(month, 0), lc.get(prev, 0)
        # 가격을 이유로 한 이탈 — 요금 인상 판단의 근거라 매월 다시 센다.
        # 사유 칸이 셋(미등록사유·종료사유·메모)이라 어디에 적혀 있어도 잡히게 셋 다 본다.
        cols = [c for c in ended[0] if "사유" in c]
        n = sum(1 for r in ended
                if any(w in str(r.get(c) or "") for c in cols for w in ("가격", "금액", "비용")))
        price = {"count": n, "of_total_ended": len(ended),
                 "pct": round(n / len(ended) * 100, 1) if ended else None}

    return {
        "active": len(rows),
        "by_type": dict(collections.Counter(str(r.get("회원\n구분") or "미상") for r in rows)),
        "registered": len(reg),
        "registered_by_class": dict(collections.Counter(_reg_class(r) for r in reg)),
        "loss": loss,
        "loss_prev_month": loss_prev,
        "ended_total": len(ended) or None,
        "price_reason_loss": price,
        "next_month_expiry": {
            "month": nxt,
            "count": len(exp),
            "contacted": len(contacted),
            "by_type": dict(collections.Counter(str(r.get("회원\n구분") or "미상") for r in exp)),
        },
    }


# ─── 문의(강습) ──────────────────────────────────────────────────────────────
def collect_inquiry(month: str) -> dict:
    d = _load(LESSON_SNAP) or {}
    out = {}
    prev = (datetime.strptime(month + "-01", "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m")
    prev2 = (datetime.strptime(prev + "-01", "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m")
    for grp, key in (("adult", "adult_lesson"), ("youth", "youth_lesson")):
        rows = ((d.get(grp) or {}).get("year") or {}).get("rows") or []
        c = collections.Counter(_month_of(r.get("timestamp")) for r in rows)
        if c:
            out[key] = {"count": c.get(month, 0), "prev": c.get(prev, 0), "prev2": c.get(prev2, 0)}
    # 멤버십 문의는 스냅샷에 접수일 칸이 없어 월별로 셀 수 없다 — 넣지 않는다(0 으로 위장 금지)
    return out


# ─── 종합접수처 ──────────────────────────────────────────────────────────────
def collect_reception(month: str) -> dict:
    try:
        import report_stream_2b_reception as R

        rows = R._fetch_rows()
    except Exception as e:
        print(f"[경고] 접수 원장 조회 실패 — {e}")
        return {}
    cur = [r for r in rows if _month_of(r.get("createdAt")) == month]
    if not cur:
        return {}
    prev = (datetime.strptime(month + "-01", "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m")
    prev_n = len([r for r in rows if _month_of(r.get("createdAt")) == prev])
    open_ = [r for r in cur if str(r.get("status")) not in ("완료", "처리완료", "종결")]

    today = _now().date()
    ages = []
    for r in open_:
        try:
            y, m, dd = map(int, str(r["createdAt"])[:10].split("-"))
            ages.append((today - datetime(y, m, dd, tzinfo=KST).date()).days)
        except Exception:
            pass
    return {
        "total": len(cur),
        "prev_month": prev_n,
        "by_category": dict(collections.Counter(str(r.get("category") or "미상") for r in cur)),
        "done": len(cur) - len(open_),
        "open": len(open_),
        "over_7d": sum(1 for a in ages if a > 7),
        "oldest_days": max(ages) if ages else 0,
    }


# ─── 점검(4부서) ─────────────────────────────────────────────────────────────
def collect_check() -> dict:
    """오늘 기준 부서별 완료율. 못 읽거나 항목이 0인 부서는 None — '실적 0'과 '못 잼'을 가른다."""
    try:
        from coo_registry import CHECK_API
    except Exception as e:
        print(f"[경고] 점검 API 주소 로드 실패 — {e}")
        return {}
    out = {}
    for dept, key in (("facility", "facility_pct"), ("support", "support_pct"),
                      ("ops", "ops_pct"), ("parking", "parking_pct")):
        try:
            url = CHECK_API + "?" + urllib.parse.urlencode({"action": "weekly", "dept": dept})
            data = json.loads(urllib.request.urlopen(url, timeout=90).read().decode("utf-8"))
            days = [x for x in (data.get("data") or []) if x.get("total")]
            out[key] = days[-1]["pct"] if days else None
        except Exception as e:
            print(f"[경고] 점검 조회 실패({dept}) — {e}")
            out[key] = None
    return out


# ─── 과제·로드맵 ─────────────────────────────────────────────────────────────
def collect_objectives(month: str) -> tuple[dict, dict]:
    d = _load(OPS_PLAN) or {}
    m = ((d.get("months") or {}).get(month)) or {}
    objs = m.get("objectives") or []
    last_day = (datetime.strptime(month + "-01", "%Y-%m-%d") + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    due_str = last_day.strftime("%Y-%m-%d")

    def due(o):
        return o.get("due") or o.get("deadline") or ""

    obj = {
        "total": len(objs),
        "done": sum(1 for o in objs if o.get("status") == "완료"),
        "due_this_month_open": sum(1 for o in objs if due(o) == due_str and o.get("status") != "완료"),
        "no_due": sum(1 for o in objs if not due(o)),
        "top_progress": [
            {"title": str(o.get("title") or "")[:60], "pct": o.get("progress") or 0}
            for o in sorted(objs, key=lambda x: -(x.get("progress") or 0))[:7]
        ],
    }
    sr = (d.get("strategy_roadmap") or {})
    items = sr.get("items") or sr.get("stages") or []
    road = {"stages": [
        {"no": i + 1, "name": str(s.get("name") or s.get("title") or ""), "pct": s.get("progress") or 0}
        for i, s in enumerate(items)
    ]}
    return obj, road


# ─── 원장 갱신 ───────────────────────────────────────────────────────────────
def build(month: str) -> dict:
    obj, road = collect_objectives(month)
    return {
        "asOf": _now().strftime("%Y-%m-%d %H:%M"),
        "sales": collect_sales(month),
        "member": collect_member(month),
        "inquiry": collect_inquiry(month),
        "reception": collect_reception(month),
        "check": collect_check(),
        "objectives": obj,
        "roadmap": road,
    }


# 기계가 덮어써도 되는 칸만 나열한다. 여기 없는 칸(narrative·decision·watchlist·unmeasured·note)은
# 사람이 쓴 판단이라 손대지 않는다 — 자동 갱신이 판단을 지우면 그 달 보고가 통째로 비어 버린다.
MACHINE_KEYS = ("asOf", "sales", "member", "inquiry", "reception", "check", "objectives", "roadmap")


def _derive(cur: dict) -> None:
    """목표 대비·전월 대비처럼 다른 칸에서 바로 나오는 값은 매번 다시 센다.
    목표치(month_target)는 사람이 넣은 공식값이라 여기서 만들지 않는다 — 없으면 비율도 내지 않는다."""
    s = cur.get("sales") or {}
    tgt, mon = s.get("month_target"), s.get("month")
    if tgt and mon:
        s["month_rate_pct"] = round(mon / tgt * 100, 1)
    prev = s.get("prev_month")
    if prev and mon:
        s["vs_prev_pct"] = round(mon / prev * 100, 1)
    pace, ycum = s.get("pace_target"), s.get("year_cum")
    if pace and ycum:
        s["pace_rate_pct"] = round(ycum / pace * 100, 1)


def main() -> int:
    ap = argparse.ArgumentParser(description="월간 운영 보고 원장 갱신")
    ap.add_argument("--month", default=_now().strftime("%Y-%m"), help="대상 월(YYYY-MM · 기본=이번 달)")
    ap.add_argument("--write", action="store_true", help="원장에 실제로 쓴다(기본은 드라이런)")
    ap.add_argument("--close", action="store_true", help="이 달을 마감 확정(closed=true)")
    ap.add_argument("--force", action="store_true", help="이미 닫힌 달도 갱신")
    a = ap.parse_args()

    led = _load(LEDGER)
    if not led:
        print("[실패] 원장을 읽지 못했습니다.")
        return 1
    months = led.setdefault("months", {})
    cur = months.get(a.month)
    if cur and cur.get("closed") and not a.force:
        print(f"[중단] {a.month} 은 이미 마감된 달입니다 — 고치려면 --force (그리고 correction 에 사유를 남기세요).")
        return 2

    fresh = build(a.month)
    cur = cur if cur else months.setdefault(a.month, {"kind": "현황", "closed": False})
    for k in MACHINE_KEYS:
        v = fresh.get(k)
        if not v:                  # 조회 실패로 빈 값이면 기존 값을 지우지 않는다
            continue
        old = cur.get(k)
        # ★통째 교체가 아니라 얕은 병합이다. 목표치·전월 대비처럼 사람이 넣어 둔 칸이 이 블록 안에
        #   섞여 있는데(예 sales.month_target), 통째로 갈아끼우면 그 값이 조용히 사라진다.
        if isinstance(old, dict) and isinstance(v, dict):
            old.update(v)
        else:
            cur[k] = v
    _derive(cur)
    if a.close:
        cur["closed"] = True
    led["updated_at"] = _now().strftime("%Y-%m-%d")

    line = (f"{a.month} · 매출 {fresh['sales'].get('month')} · 회원 {fresh['member'].get('active')} "
            f"· 등록 {fresh['member'].get('registered')} · 접수 {fresh['reception'].get('total')} "
            f"· 점검 시설 {fresh['check'].get('facility_pct')} 지원 {fresh['check'].get('support_pct')}")
    if not a.write:
        print("[드라이런] 원장에 쓰지 않았습니다.")
        print(line)
        return 0

    with open(LEDGER, "w", encoding="utf-8") as f:
        json.dump(led, f, ensure_ascii=False, indent=2)
    print("[기록] status/monthly_report_ledger.json 갱신" + (" · 마감 확정" if a.close else ""))
    print(line)
    return 0


def _selftest():
    """조회 없이 도는 최소 검사 — 갱신이 사람이 쓴 판단을 지우지 않는지만 본다(이게 이 도구의 유일한 위험)."""
    assert "narrative" not in MACHINE_KEYS and "decision" not in MACHINE_KEYS, "판단 칸이 기계 갱신 대상에 섞였다"
    assert _reg_class({"등록 분류": "L재등록"}) == "재등록"
    assert _reg_class({"등록 분류": "신규"}) == "신규"
    assert _reg_class({}) == "(빈칸)"
    assert _month_of("2026-08-28 16:55") == "2026-08"
    print("자체검사 통과")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        raise SystemExit(main())
