# -*- coding: utf-8 -*-
"""schedule_backfill_keys.py — 이미 올라가 있는 전사일정 항목에 열쇠 두 칸(todo_id·plan_id)을 소급해 채운다.

왜: 2026-09-14 부터 gm_handoff 로 **새로** 올리는 일정에는 todo_id·plan_id 가 들어가 화면 카드에
  「▸업무」·「▸GM업무」 링크가 뜬다(전사_일정.html renderList keyTxt). 그런데 그 전에 쌓인 242건에는
  그 칸이 없어 영영 링크가 안 뜬다. GM 승인 2026-09-14 「소급 진행」.

짝짓기 규칙(제목 정규화 = 공백·괄호·기호 제거)
  확신     — 한쪽 제목이 다른 쪽을 통째로 품고, 날짜가 30일 안. 후보가 정확히 1개.
  판정필요 — 닮았는데(유사도 0.72+) 날짜가 멀거나, 확신 후보가 2개 이상.
  없음     — 그 외.
확신만 라이브에 쓴다. 판정필요는 보고서에만 남긴다 — 사람이 보고 정하는 몫이다.

쓰는 법
  python scripts/schedule_backfill_keys.py            # 백업 + 짝짓기 + 보고서만 (라이브 쓰기 없음)
  python scripts/schedule_backfill_keys.py --apply    # 위에 더해 확신 건을 라이브에 저장하고 되읽어 확인

# ponytail: 한 번 쓰고 마는 소급 도구 — 일반화하지 않는다. 저장은 전사일정이 원래 쓰는 save_schedule 그대로.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import sys
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

BACKUP = ROOT / "status" / "backups" / "schedule_before_backfill_20260914.json"
REPORT = ROOT / "status" / "schedule_backfill_report.md"
PLAN_PATH = ROOT / "status" / "monthly_ops_plan.json"
GM_KEY = "1531"          # GM 행은 이 키 없이는 todo_list 에 안 나온다(gm_handoff 와 같은 값)
NEAR_DAYS = 30
SIM_SOFT = 0.72          # 「판정필요」로 올릴 최소 닮음
MIN_KEY = 4              # 정규화 제목이 이보다 짧으면 포함 판정을 믿지 않는다("교육" 같은 토막)


# ── 읽기 ──────────────────────────────────────────────────────────────────
def _open(req_or_url, tries: int = 3) -> dict:
    """GAS 한 번 호출 + 재시도. 2026-09-14 실측: /exec 의 302 목적지가 이따금 404 로 답한다
    (읽기 GET 조차 · 5초 뒤 같은 주소가 정상). 한 번 튕겼다고 소급을 멈추지 않는다.

    POST 재시도가 두 번 쓰는 사고를 내지 않는 이유: 저장은 baseRev 를 실어 보내고, 앞 POST 가
    실제로 들어갔다면 서버 rev 가 바뀌어 두 번째가 stale-rev 로 **거부**된다(그 답이 곧 신호다).
    """
    import time
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(req_or_url, timeout=90) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e
            print("  … GAS 호출 실패 %d/%d: %s %s" % (i + 1, tries, type(e).__name__, e))
            if i < tries - 1:
                time.sleep(5 * (i + 1))
    raise last


def fetch_live() -> dict:
    from collectors.ops_shared import SCHEDULE_GAS_URL
    return _open(SCHEDULE_GAS_URL + "?action=load_schedule")


def fetch_todos() -> list:
    import ops_daily_digest as o
    res = o._gas_get(o.SSOT_API_URL, params={"action": "todo_list", "include_gm": "1", "gmkey": GM_KEY},
                     timeout=60, label="전사일정 소급 짝짓기").json()
    return res.get("data") or []


def load_objectives() -> list:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    out = []
    for mkey, mval in (plan.get("months") or {}).items():
        for ob in (mval.get("objectives") or []):
            if ob.get("id") and ob.get("title"):
                out.append({"id": ob["id"], "title": ob["title"], "month": mkey, "due": ob.get("due") or ""})
    return out


# ── 이름·날짜 ─────────────────────────────────────────────────────────────
def norm(s) -> str:
    """제목 정규화 — 공백·괄호·기호·구분자를 걷어낸 한글/영문/숫자만."""
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", str(s or ""))


def as_date(v):
    s = str(v or "")[:10]
    try:
        return _dt.date.fromisoformat(s)
    except ValueError:
        return None


def month_span(mkey: str):
    """'2026-09' → (9/1, 9/30). due 가 없는 목표는 그 달 전체를 기간으로 본다."""
    try:
        y, m = (int(x) for x in mkey.split("-")[:2])
    except ValueError:
        return None
    first = _dt.date(y, m, 1)
    last = _dt.date(y + (m == 12), (m % 12) + 1, 1) - _dt.timedelta(days=1)
    return first, last


def gap_days(d, span):
    """일정 날짜와 상대 기간 사이의 거리(일). 기간 안이면 0. 잴 수 없으면 None."""
    if d is None or span is None:
        return None
    lo, hi = span
    if lo <= d <= hi:
        return 0
    return (lo - d).days if d < lo else (d - hi).days


# ── 짝짓기 ────────────────────────────────────────────────────────────────
def candidates(item_name: str, item_date, pool: list):
    """(확신 후보, 닮음 후보). pool 원소 = {"key","title","title_norm","span"}"""
    a = norm(item_name)
    sure, soft = [], []
    if len(a) < MIN_KEY:
        return sure, soft
    for c in pool:
        b = c["title_norm"]
        if len(b) < MIN_KEY:
            continue
        g = gap_days(item_date, c["span"])
        contains = (a in b) or (b in a)
        ratio = SequenceMatcher(None, a, b).ratio()
        if contains and g is not None and g <= NEAR_DAYS:
            sure.append(dict(c, gap=g, ratio=ratio))
        elif contains or ratio >= SIM_SOFT:
            soft.append(dict(c, gap=g, ratio=ratio))
    return sure, soft


def build_pools(todos: list, objectives: list):
    tpool = []
    for r in todos:
        s, e = as_date(r.get("시작일")), as_date(r.get("종료일"))
        have = [x for x in (s, e) if x]
        span = (min(have), max(have)) if have else None
        tpool.append({"key": r.get("id"), "title": r.get("업무명") or "",
                      "title_norm": norm(r.get("업무명")), "span": span})
    opool = []
    for ob in objectives:
        d = as_date(ob["due"])
        span = (d, d) if d else month_span(ob["month"])
        opool.append({"key": ob["id"], "title": ob["title"],
                      "title_norm": norm(ob["title"]), "span": span})
    return tpool, opool


def decide(item: dict, tpool: list, opool: list) -> dict:
    """한 일정 항목의 판정. verdict = sure | review | none"""
    name, d = item.get("name") or "", as_date(item.get("next_due"))
    ts, tsoft = candidates(name, d, tpool)
    os_, osoft = candidates(name, d, opool)
    todo = ts[0] if len(ts) == 1 else None
    plan = os_[0] if len(os_) == 1 else None
    if todo or plan:
        return {"verdict": "sure", "todo": todo, "plan": plan,
                "why": " · ".join(x for x in [
                    ("업무 제목 포함·%d일차" % todo["gap"]) if todo else "",
                    ("목표 제목 포함·%d일차" % plan["gap"]) if plan else ""] if x)}
    amb = [("업무", c) for c in (ts or tsoft)] + [("목표", c) for c in (os_ or osoft)]
    if amb:
        why = "확신 후보 여럿" if (len(ts) > 1 or len(os_) > 1) else "닮았으나 날짜가 멀거나 포함 아님"
        return {"verdict": "review", "cands": amb[:4], "why": why}
    return {"verdict": "none", "why": "닮은 행·목표 없음"}


# ── 저장 ──────────────────────────────────────────────────────────────────
def save_live(cal: dict, base_rev: str) -> dict:
    """전사일정이 원래 쓰는 save_schedule 그대로. baseRev 를 실어 동시편집 충돌을 GAS 가 막게 둔다."""
    from collectors.ops_shared import SCHEDULE_GAS_URL
    body = json.dumps({"action": "save_schedule", "data": cal, "baseRev": base_rev}).encode("utf-8")
    req = urllib.request.Request(SCHEDULE_GAS_URL, data=body,
                                 headers={"Content-Type": "text/plain"}, method="POST")
    return _open(req)


# ── 보고서 ────────────────────────────────────────────────────────────────
def cut(s, n=34) -> str:
    s = str(s or "").replace("|", "/").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def write_report(rows: list, counts: dict, applied: str) -> None:
    total = sum(counts.values())
    L = ["# 전사일정 열쇠 소급 보고 — " + _dt.date.today().isoformat(), "",
         "대상 %d건 · 확신 %d · 판정필요 %d · 없음 %d" % (total, counts["sure"], counts["review"], counts["none"]),
         "라이브 반영: " + applied, "",
         "확신 건만 라이브에 썼다. 판정필요는 사람이 보고 정한다 — 짝을 고르면 그 항목을 화면에서 열어 저장하거나,",
         "gm_handoff 로 다시 올릴 때 --todo-id·--plan 을 주면 된다.", "",
         "## 확신 (반영함)", "",
         "|일정 제목|날짜|업무 id|업무 제목|목표 id|근거|", "|---|---|---|---|---|---|"]
    for r in rows:
        if r["d"]["verdict"] != "sure":
            continue
        t, p = r["d"].get("todo") or {}, r["d"].get("plan") or {}
        L.append("|%s|%s|%s|%s|%s|%s|" % (cut(r["it"].get("name")), r["it"].get("next_due") or "—",
                                          t.get("key") or "—", cut(t.get("title"), 26),
                                          p.get("key") or "—", r["d"]["why"]))
    L += ["", "## 판정 필요 (안 씀)", "", "|일정 제목|날짜|후보|사유|", "|---|---|---|---|"]
    for r in rows:
        if r["d"]["verdict"] != "review":
            continue
        cands = " / ".join("%s:%s" % (k, cut(c["title"], 20)) for k, c in r["d"]["cands"])
        L.append("|%s|%s|%s|%s|" % (cut(r["it"].get("name")), r["it"].get("next_due") or "—",
                                    cut(cands, 60), r["d"]["why"]))
    L += ["", "## 없음 — %d건" % counts["none"], "",
          "제목이 닮은 업무 행·월간목표가 없다. 일정에만 있는 일(방문·점검·행사)이 대부분이다.", ""]
    REPORT.write_text("\n".join(L), encoding="utf-8")


# ── 본체 ──────────────────────────────────────────────────────────────────
def main() -> int:
    apply = "--apply" in sys.argv

    live = fetch_live()
    if not (isinstance(live, dict) and live.get("ok") and isinstance((live.get("data") or {}).get("items"), list)):
        print("✖ 라이브 조회 실패 — 아무것도 하지 않는다:", str(live)[:200])
        return 1
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    BACKUP.write_text(json.dumps(live, ensure_ascii=False, indent=2), encoding="utf-8")
    cal, rev = live["data"], str(live.get("rev") or "")
    print("[백업] %s · %d bytes · 항목 %d건 · rev %s"
          % (BACKUP, BACKUP.stat().st_size, len(cal["items"]), rev or "(없음)"))

    tpool, opool = build_pools(fetch_todos(), load_objectives())
    print("[짝 후보] 업무 %d행 · 월간목표 %d개" % (len(tpool), len(opool)))

    rows, counts = [], {"sure": 0, "review": 0, "none": 0}
    for it in cal["items"]:
        if not isinstance(it, dict):
            continue
        # 이미 채워진 항목은 건드리지 않는다(gm_handoff 로 새로 올린 건).
        if it.get("todo_id") or it.get("plan_id"):
            continue
        d = decide(it, tpool, opool)
        counts[d["verdict"]] += 1
        rows.append({"it": it, "d": d})

    applied = "안 함(--apply 없음)"
    if apply and counts["sure"]:
        for r in rows:
            if r["d"]["verdict"] != "sure":
                continue
            t, p = r["d"].get("todo") or {}, r["d"].get("plan") or {}
            r["it"]["todo_id"] = t.get("key") or ""
            r["it"]["plan_id"] = p.get("key") or ""
        res = save_live(cal, rev)
        if not (isinstance(res, dict) and res.get("ok")):
            print("✖ 저장 거부 — 라이브 그대로:", str(res)[:300])
            write_report(rows, counts, "저장 거부 — " + str(res)[:120])
            return 1
        back = fetch_live()
        items_back = (back.get("data") or {}).get("items") or []
        got = [x for x in items_back if isinstance(x, dict) and (x.get("todo_id") or x.get("plan_id"))]
        applied = "저장 ✔ · 되읽기에서 열쇠 있는 항목 %d건 (총 %d건)" % (len(got), len(items_back))
        print("[되읽기] 열쇠 살아 있는 항목 %d건 / 총 %d건" % (len(got), len(items_back)))
    elif apply:
        applied = "확신 0건 — 쓸 것이 없다"

    write_report(rows, counts, applied)
    print("[판정] 확신 %d · 판정필요 %d · 없음 %d → %s"
          % (counts["sure"], counts["review"], counts["none"], REPORT))
    return 0


def _demo() -> None:
    """자체 점검 — 짝짓기 규칙이 확신/판정필요/없음 셋을 제대로 가르는지."""
    pool = [{"key": "TODO-1", "title": "요가 프로그램 개편", "title_norm": norm("요가 프로그램 개편"),
             "span": (_dt.date(2026, 9, 1), _dt.date(2026, 9, 30))},
            {"key": "TODO-2", "title": "주차 요금 인상", "title_norm": norm("주차 요금 인상"),
             "span": (_dt.date(2026, 3, 1), _dt.date(2026, 3, 31))}]
    sure, soft = candidates("요가 프로그램 개편 (2차)", _dt.date(2026, 9, 15), pool)
    assert [c["key"] for c in sure] == ["TODO-1"], (sure, soft)
    sure, soft = candidates("주차 요금 인상", _dt.date(2026, 9, 15), pool)   # 제목은 맞는데 6개월 차이
    assert not sure and [c["key"] for c in soft] == ["TODO-2"], (sure, soft)
    sure, soft = candidates("승강기 정기점검", _dt.date(2026, 9, 15), pool)
    assert not sure and not soft, (sure, soft)
    assert gap_days(_dt.date(2026, 9, 15), (_dt.date(2026, 9, 1), _dt.date(2026, 9, 30))) == 0
    assert gap_days(_dt.date(2026, 10, 5), (_dt.date(2026, 9, 1), _dt.date(2026, 9, 30))) == 5
    assert month_span("2026-02") == (_dt.date(2026, 2, 1), _dt.date(2026, 2, 28))
    assert month_span("2026-12") == (_dt.date(2026, 12, 1), _dt.date(2026, 12, 31))
    print("짝짓기 규칙 자체 점검 통과 ✓")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _demo()
        raise SystemExit(0)
    raise SystemExit(main())
