#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""업무 시스템 한 장 — 빌더 (GM 지시 2026-09-17).

네 원천(GM 카드 · 중간관리자 원장 · 업무&결재 SSOT · 전사일정)을 읽어
status/work_system.json 을 사람별로 합쳐 쓴다. 읽기 전용 — 어느 원천에도 쓰지 않는다.
새 원장을 만들지 않는다(약속 L01·L21) — 정규화·상수는 기존 모듈(gm_surfaces_sync·send_ops_digest·
gm_handoff·collectors.ops_shared·schedule_ssot)을 그대로 가져다 쓴다.

실행: C:/Python314/python.exe scripts/work_system_build.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import gm_surfaces_sync as sync            # noqa: E402  norm_title · similar (약속 L01 재사용)
import gm_handoff                          # noqa: E402  GM_KEY
from send_ops_digest import MGR_LEDGER     # noqa: E402  중간관리자 원장 정본 경로
from collectors.ops_shared import gas_get, SSOT_API_URL  # noqa: E402

PEOPLE_PATH = ROOT / "status" / "work_system_people.json"
OUT_PATH = ROOT / "status" / "work_system.json"
PLAN_PATH = ROOT / "status" / "monthly_ops_plan.json"

# 체크 줄 표기 정규식 — gm_aide_scan.py 와 같은 계약(약속 L01, 복제 아님 · 값만 옮김)
DUE_MARK = re.compile(r"\(~\s*(\d{1,2})/(\d{1,2})\s*\)")
DUE_MARK_PLAIN = re.compile(r"기한\s*[:：]\s*(?:\d{4}-)?(\d{1,2})[-/](\d{1,2})")

CARD_DONE = {"완료", "취소"}
SSOT_DONE = {"완료", "종결", "취소"}

# 전사일정 노이즈 제거(GM 지시 2026-09-17 2차) — 반복 청소·점검·법정 점검이 GM 밀림을 덮었다.
# cycle·repeat 가 있으면(매주/월 1회/1회 등 값 자체가 있으면) 반복·정기 취급 · 법정/점검 계열
# 카테고리(schedule_ssot.json categories 정의 그대로 — 새 분류 안 만듦)는 통째로 뺀다.
SCHEDULE_DENY_CATEGORIES = {"fire", "elec", "lift", "hyg", "water", "edu", "safe", "gas", "safety"}

# 표식·태그 청소(GM 지시 2026-09-17 2차) — 업무 SSOT 내용 칸에 위키형 HTML·"===PLAN===" 같은
# 구조 표식이 그대로 박혀 있어 걷어낸다. 정본 텍스트(SSOT·카드)는 안 바꾼다 — 화면에 보여줄 때만.
_TAG_RE = re.compile(r"<[^>]+>")
_MARKER_RE = re.compile(r"={2,}[^=\n]{0,40}={2,}")


def clean_text(s) -> str:
    s = _TAG_RE.sub(" ", str(s or ""))
    s = _MARKER_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _kst_today() -> date:
    return datetime.now(timezone(timedelta(hours=9))).date()


def _read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _norm_owner(s) -> str:
    return re.sub(r"\s+", "", str(s or "")).lower()


def _due_from_check_line(line: str, today: date) -> "str | None":
    """체크 줄의 「(~9/5)」·「기한: 9/5」 표기 → YYYY-MM-DD(올해 기준). 없으면 None — 지어내지 않음."""
    m = DUE_MARK.search(line) or DUE_MARK_PLAIN.search(line)
    if not m:
        return None
    try:
        return date(today.year, int(m.group(1)), int(m.group(2))).isoformat()
    except ValueError:
        return None


# ── 원천 4종 — 읽기만 한다 ──────────────────────────────────────────────

def collect_cards(today: date):
    """GM 카드 = status/monthly_ops_plan.json months[*].objectives, status 완료·취소 제외."""
    items, failed = [], False
    plan = _read_json(PLAN_PATH, {})
    try:
        for month in (plan.get("months") or {}).values():
            for o in month.get("objectives") or []:
                if o.get("status") in CARD_DONE:
                    continue
                title = clean_text(o.get("title"))
                if not title:
                    continue
                next_step, due = "", None
                for ln in str(o.get("progress_note") or "").splitlines():
                    t = ln.strip()
                    if not t.startswith("□"):
                        continue
                    next_step = clean_text(t[1:])
                    due = _due_from_check_line(t, today)
                    break
                if not next_step:
                    next_step = clean_text(o.get("target"))[:80]
                items.append({
                    "title": title, "owner": str(o.get("owner") or "").strip(),
                    "dept": str(o.get("dept") or "").strip(), "due": due,
                    "next": next_step, "hold": False,
                    "src": "card", "ref": str(o.get("id") or ""),
                })
    except Exception:
        failed = True
    return items, failed


def collect_ledger(today: date):
    """중간관리자 원장 = _digest_ledger.json 각 날 issues[] 중 status=open 만."""
    items, failed = [], False
    try:
        for day in _read_json(MGR_LEDGER, []):
            for iss in day.get("issues") or []:
                if iss.get("status") != "open":
                    continue
                title = str(iss.get("issue") or "").strip()
                if not title:
                    continue
                items.append({
                    "title": title, "owner": str(iss.get("owner") or "").strip(),
                    "dept": "", "due": (str(iss.get("due") or "").strip() or None),
                    "next": str(iss.get("note") or "").strip(), "hold": False,
                    "src": "ledger", "ref": str(iss.get("no") or ""),
                })
    except Exception:
        failed = True
    return items, failed


def collect_ssot(today: date):
    """업무&결재 SSOT = todo_list(GM 행 포함), 상태 완료·종결·취소 제외. 60초·1회 재시도."""
    items, failed = [], False
    try:
        resp = gas_get(SSOT_API_URL,
                        params={"action": "todo_list", "include_gm": "1", "gmkey": gm_handoff.GM_KEY},
                        timeout=60, attempts=2, label="work_system_ssot")
        if resp is None:
            return items, True
        rows = resp.json().get("data") or []
        for r in rows:
            if str(r.get("상태") or "") in SSOT_DONE:
                continue
            title = clean_text(r.get("업무명"))
            if not title:
                continue
            items.append({
                "title": title, "owner": str(r.get("담당자") or "").strip(),
                "dept": "", "due": (str(r.get("종료일") or "")[:10] or None),
                "next": clean_text(r.get("내용"))[:80],
                "hold": str(r.get("상태") or "") == "보류",
                "src": "ssot", "ref": str(r.get("id") or ""),
            })
    except Exception:
        failed = True
    return items, failed


def collect_schedule(today: date):
    """전사일정 = schedule_ssot items 중 next_due 오늘±14일 · 해당없음 제외 ·
    반복 청소·점검·법정 점검 제외(cycle·repeat 값이 있거나 법정/점검 계열 category 면 뺀다 —
    GM 지시 2026-09-17 2차, 「D-73 수영장 화장실 청소」 등 반복 항목이 밀림을 덮었다)."""
    items, failed = [], False
    try:
        import schedule_ssot as sch
        cal = sch.load()
        for it in cal.get("items") or []:
            if it.get("applies") == "해당없음":
                continue
            if it.get("cycle") or it.get("repeat"):
                continue
            if it.get("category") in SCHEDULE_DENY_CATEGORIES:
                continue
            due = sch._parse_due(it.get("next_due"))
            if due is None or abs((due - today).days) > 14:
                continue
            title = clean_text(it.get("name"))
            if not title:
                continue
            items.append({
                "title": title, "owner": str(it.get("assignee") or "").strip(),
                "dept": str(it.get("dept") or "").strip(), "due": due.isoformat(),
                "next": clean_text(it.get("note")), "hold": False,
                "src": "schedule", "ref": str(it.get("id") or ""),
            })
    except Exception:
        failed = True
    return items, failed


# ── 합치기·판정 ──────────────────────────────────────────────────────

def merge(items: list) -> list:
    """제목 유사(gm_surfaces_sync.similar) 항목을 한 줄로 — srcs 를 늘린다. 빈칸은 채우지 않는다(지어내지 않음)."""
    merged: list = []
    for it in items:
        hit = next((m for m in merged if sync.similar(m["title"], it["title"])), None)
        if hit is None:
            it["srcs"] = [{"src": it["src"], "ref": it["ref"]}]
            merged.append(it)
            continue
        hit["srcs"].append({"src": it["src"], "ref": it["ref"]})
        if not hit.get("due") and it.get("due"):
            hit["due"] = it["due"]
        if not hit.get("next") and it.get("next"):
            hit["next"] = it["next"]
        if not hit.get("owner") and it.get("owner"):
            hit["owner"] = it["owner"]
        hit["hold"] = hit.get("hold") or it.get("hold")
    return merged


def classify(it: dict, today: date) -> str:
    """🔴overdue · 📅today · 🗓week(7일 안) · 🚀progress(기한 없음/먼 미래) · ⏸hold(SSOT 보류) · blank(기한·다음걸음 둘 다 없음)."""
    if it.get("hold"):
        return "hold"
    due, next_step = it.get("due"), it.get("next")
    if not due and not next_step:
        return "blank"
    if not due:
        return "progress"
    try:
        d = date.fromisoformat(str(due)[:10])
    except ValueError:
        return "progress"
    dd = (d - today).days
    if dd < 0:
        return "overdue"
    if dd == 0:
        return "today"
    if dd <= 7:
        return "week"
    return "progress"


def matches_person(it: dict, person: dict) -> bool:
    owner_n = _norm_owner(it.get("owner"))
    aliases = {_norm_owner(a) for a in person.get("aliases") or []}
    if owner_n and owner_n in aliases:
        return True
    scope = person.get("scope")
    if scope == "all":
        return True
    if scope == "dept":
        item_dept = str(it.get("dept") or "")
        return any(d and d in item_dept for d in (person.get("dept") or []))
    return False


def build() -> dict:
    today = _kst_today()
    meta = {"generated_at": datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S"),
            "today": today.isoformat(), "counts": {}, "failed": []}

    all_items: list = []
    for name, fn in (("card", collect_cards), ("ledger", collect_ledger),
                      ("ssot", collect_ssot), ("schedule", collect_schedule)):
        got, failed = fn(today)
        meta["counts"][name] = len(got)
        if failed:
            meta["failed"].append(name)
        all_items.extend(got)

    merged = merge(all_items)
    for it in merged:
        it["state"] = classify(it, today)
    meta["merged_from"] = len(all_items) - len(merged)
    meta["total_items"] = len(merged)

    people = _read_json(PEOPLE_PATH, {})
    people_out = {}
    for who, person in people.items():
        if who.startswith("_"):
            continue
        my_items = [it for it in merged if matches_person(it, person)]
        counts = {
            "밀림": sum(1 for i in my_items if i["state"] == "overdue"),
            "오늘_이번주": sum(1 for i in my_items if i["state"] in ("today", "week")),
            "진행": sum(1 for i in my_items if i["state"] in ("progress", "hold")),
        }
        people_out[who] = {"display": person.get("display", who), "counts": counts, "items": my_items}

    out = {"_doc": "업무 시스템 한 장 — scripts/work_system_build.py 자동 생성. 손으로 고치지 않는다.",
           "meta": meta, "people": people_out}
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def _selftest() -> None:
    """ponytail: 가장 잘 깨지는 판정 갈래만 — assert 기반 최소 점검."""
    today = date(2026, 9, 17)
    assert classify({"due": "2026-09-10", "next": "x", "hold": False}, today) == "overdue"
    assert classify({"due": "2026-09-17", "next": "x", "hold": False}, today) == "today"
    assert classify({"due": "2026-09-20", "next": "x", "hold": False}, today) == "week"
    assert classify({"due": "2026-10-30", "next": "x", "hold": False}, today) == "progress"
    assert classify({"due": None, "next": "x", "hold": False}, today) == "progress"
    assert classify({"due": None, "next": "", "hold": False}, today) == "blank"
    assert classify({"due": None, "next": "", "hold": True}, today) == "hold"
    p_owner = {"scope": "owner", "aliases": ["최준용M", "최준용"], "dept": []}
    assert matches_person({"owner": "최준용", "dept": ""}, p_owner) is True
    assert matches_person({"owner": "임정은M", "dept": ""}, p_owner) is False
    p_dept = {"scope": "dept", "aliases": ["나우열M"], "dept": ["파트너팀", "인사"]}
    assert matches_person({"owner": "", "dept": "운영부·파트너팀"}, p_dept) is True
    assert matches_person({"owner": "", "dept": "시설부"}, p_dept) is False
    print("[work_system_build] 자체점검 통과")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
        sys.exit(0)
    result = build()
    print(f"[work_system_build] 저장 완료 — {OUT_PATH}")
    print(json.dumps(result["meta"], ensure_ascii=False, indent=1))
