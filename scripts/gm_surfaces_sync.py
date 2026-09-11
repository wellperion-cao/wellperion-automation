# -*- coding: utf-8 -*-
"""GM업무 · 전사일정 · 업무&결재 SSOT · 중간관리자 아침 통을 한 줄기로 잇는다 (GM 지시 2026-09-09).

GM 원문: "GM업무 + 중간관리자업무 + 전사일정 + 업무&결재SSOT 잘 연동해줘 이거 정말 중요한거야."

네 화면이 각각 무엇을 맡는지는 이미 정해져 있다(약속 L23) — 전사일정 = 담당·날짜 / 월간운영계획(GM업무)
= 진척 / 업무·결재 SSOT = 실행·결재 / 아침 통 = 그날 사람에게 나가는 말. 문제는 손으로 맞추다 보니
한쪽만 바뀌는 것이었다. 이 파일이 그 대조를 한 곳에서 한다.

  python scripts/gm_surfaces_sync.py            # 대조만 (아무것도 안 고침)
  python scripts/gm_surfaces_sync.py --apply    # 전사일정 짝을 카드에 맞춰 만들고·고치고·지운다
  python scripts/gm_surfaces_sync.py --selftest # 자가검사

무엇을 맞추나
  ① 카드 → 전사일정 : 열린 GM 직접 카드(기한 있음·10월 말 이내)마다 `gmwork-<카드id>` 항목 하나.
     날짜·담당이 다르면 카드 쪽을 정본으로 고친다. 카드가 닫히거나 사라지면 그 항목을 지운다.
  ② 카드 ↔ 업무·결재 SSOT : 제목이 닮은 GM 행이 있는지 본다. 없으면 「SSOT 행 없음」으로만 알린다 —
     ★행을 만들지 않는다(2026-08-18 GM 규칙: AI 는 남의 SSOT 행을 만들지 않는다. GM 행도 gm_handoff 로만).
  ③ 결재 대기(대표싸인 PENDING) 행이 어느 카드에도 안 붙어 있으면 알린다 — 결재가 진척과 따로 도는 자리.
  ④ 담당 빈칸 : 담당이 비면 아침 통에 실리지 않는다(그 사람 통이 조용해진다) — 그래서 대조 대상이다.

고치는 것은 ①뿐이다. 나머지는 사람이 판단할 자리라 표로만 올린다.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

PLAN_FILE = ROOT / "status" / "monthly_ops_plan.json"
GM_TAG = "(GM 직접)"
HORIZON_DAYS = 60          # 전사일정에 짝을 두는 범위 — 이보다 먼 기한은 일정에 올리지 않는다(달력이 흐려진다)
OWNER_BOARD_KEY = "GM_TASK_OWNERS"
OWNER_BOARD_URL = ("https://script.google.com/macros/s/"
                   "AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec")


def _today() -> _dt.date:
    return _dt.date.today()


def _date(v) -> "_dt.date | None":
    try:
        return _dt.date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def norm_title(s) -> str:
    """제목 대조용 — 공백·기호·괄호 안 설명을 걷어낸 뼈대만."""
    s = re.sub(r"\(.*?\)", " ", str(s or ""))
    s = s.replace(GM_TAG, " ")
    return re.sub(r"[\s·\-—~/,.\[\]]+", "", s)


def similar(a: str, b: str) -> bool:
    """한쪽이 다른 쪽에 들어가거나 앞 8글자가 같으면 같은 건으로 본다(제목이 조금씩 늘어나는 걸 흡수)."""
    a, b = norm_title(a), norm_title(b)
    if not a or not b:
        return False
    return a in b or b in a or a[:8] == b[:8]


CLOSED_HINTS = ("완료", "종결", "취소", "폐기")
TRANSFER_RE = re.compile(r"▶\[[^\]]*이관[^\]]*\]")  # 이관 표시 — 태그가 빠진 게 아니라 이관돼서 뗀 것


def closed_statuses(plan: dict) -> set:
    """완료·종결 계열 상태값 — 지어내지 않고 계획 파일의 status_enum 에서 고른다."""
    return {s for s in (str(x) for x in (plan.get("status_enum") or []))
            if any(h in s for h in CLOSED_HINTS)} or {"완료"}


def find_objective(plan: dict, cid: str) -> "dict | None":
    for month in (plan.get("months") or {}).values():
        for o in month.get("objectives") or []:
            if str(o.get("id")) == cid:
                return o
    return None


def open_gm_cards(plan: dict) -> list:
    out = []
    for month in (plan.get("months") or {}).values():
        for o in month.get("objectives") or []:
            if GM_TAG in str(o.get("title") or "") and o.get("status") != "완료":
                # schedule_hidden — 카드는 열려 있지만 전사일정에는 줄을 두지 않는다.
                #   GM 이 지운 줄을 이 동기화가 다음 회차에 되살려 이틀 연속 같은 삭제 지시를 받았다
                #   (CCTV 전체 교체 · 2026-09-09, 2026-09-10). 지우는 자리와 되살리는 자리가 달라
                #   손으로 지우는 한 영원히 반복된다 — 카드 한 곳에서 끈다.
                if o.get("schedule_hidden"):
                    continue
                out.append(o)
    return out


def fetch_owners() -> dict:
    import urllib.request
    try:
        url = f"{OWNER_BOARD_URL}?action=board&key={OWNER_BOARD_KEY}"
        with urllib.request.urlopen(url, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d.get("board") or {} if d.get("ok") else {}
    except Exception:
        return {}


def fetch_todo_rows() -> list:
    """업무·결재 SSOT 행 — GM 행까지 보려면 gmkey 가 필요하다(2026-09-07 실측)."""
    try:
        import ops_daily_digest as o
        res = o._gas_get(o.SSOT_API_URL, params={"action": "todo_list", "include_gm": "1", "gmkey": "1531"},
                         timeout=60, label="surfaces_sync")
        return (res.json().get("data") or []) if res else []
    except Exception:
        return []


def plan_event(card: dict, who: str) -> dict:
    name = str(card.get("title") or "").replace(GM_TAG, "").strip()
    return {
        "type": "이벤트", "category": "gm", "cycle": "", "cycle_confirmed": False,
        "period_months": None, "last_done": "", "evidence": "", "applies": "있음",
        "legal_basis": "", "vendor_id": "", "source": "GM업무 카드 " + str(card.get("id")),
        "id": "gmwork-" + str(card.get("id")), "name": "[GM업무] " + name,
        "dept": str(card.get("dept") or "").strip(), "assignee": who,
        "next_due": str(card.get("due") or "")[:10], "time": "", "repeat": "",
        "note": ("GM업무 카드와 짝(gm_surfaces_sync.py 가 맞춘다). 진척·체크는 카드에서 보고 여기는 담당과 날짜만 든다. "
                 "카드 = 월간운영계획 " + str(card.get("id")) + "."),
    }


def diff(plan: dict, items: list, owners: dict, todo_rows: list, today=None) -> dict:
    """네 화면 대조 결과. 고칠 것(전사일정)과 알릴 것(사람 판단)을 갈라 돌려준다."""
    today = today or _today()
    limit = today + _dt.timedelta(days=HORIZON_DAYS)
    cards = open_gm_cards(plan)
    by_sid = {str(it.get("id")): it for it in items if str(it.get("id", "")).startswith("gmwork-")}
    want, add, fix, drop, notes = {}, [], [], [], []

    for c in cards:
        cid = str(c.get("id"))
        who = str(owners.get(cid, "") or "").strip()
        due = _date(c.get("due"))
        title = str(c.get("title") or "").replace(GM_TAG, "").strip()
        if not who:
            notes.append(("담당없음", cid, title))
        if not due:
            notes.append(("기한없음", cid, title))
            continue
        if due > limit:
            continue                      # 먼 기한은 일정에 안 올린다(카드에서 본다)
        sid = "gmwork-" + cid
        want[sid] = plan_event(c, who)
        cur = by_sid.get(sid)
        if cur is None:
            add.append(sid)
        else:
            if str(cur.get("next_due") or "")[:10] != str(c.get("due") or "")[:10]:
                fix.append((sid, "날짜", cur.get("next_due"), c.get("due")))
            if who and str(cur.get("assignee") or "").strip() != who:
                fix.append((sid, "담당", cur.get("assignee"), who))
        if todo_rows and not any(similar(title, r.get("업무명")) for r in todo_rows):
            notes.append(("SSOT행없음", cid, title))

    # 지우기 전에 카드를 직접 열어 본다 — 제목에 (GM 직접) 태그가 빠진 카드가 cards 에 안 들어와
    # 「닫혔다」로 판정돼 살아 있는 GM업무 3건이 전사일정에서 사라졌다(2026-09-11). 상태를 보고 가른다.
    closed = closed_statuses(plan)
    card_ids = {str(c.get("id")) for c in cards}
    for sid in by_sid:
        if sid in want:
            continue
        cid = sid[len("gmwork-"):]
        if cid in card_ids:
            drop.append(sid)              # 카드는 봤다 — 기한이 없거나 멀어 일정에서 뺀다
            continue
        o = find_objective(plan, cid)
        if o and str(o.get("status") or "") not in closed and not o.get("schedule_hidden"):
            if TRANSFER_RE.search(str(o.get("progress_note") or "")):
                notes.append(("이관됨", cid, str(o.get("title") or "")))     # 정상 이관 — 경고 아님
            else:
                notes.append(("태그빠짐", cid, str(o.get("title") or "")))   # 살아 있다 — 안 지운다
            continue
        drop.append(sid)                  # 카드가 없거나 닫혔다 — 일정에서 뺀다

    # 같은 카드가 mop-* · gmwork-* 두 줄로 오른 건 (고치는 건 시우 배1190 — 여기선 세기만 한다)
    sched_ids = {str(it.get("id")) for it in items}
    for sid in sched_ids:
        cid = sid[len("gmwork-"):] if sid.startswith("gmwork-") else None
        if cid and "mop-" + cid in sched_ids:
            o = find_objective(plan, cid)
            notes.append(("중복두줄", cid, str((o or {}).get("title") or "")))

    # 결재 대기(대표싸인 PENDING)인데 카드에 안 붙은 행
    for r in todo_rows:
        if str(r.get("대표싸인") or "").strip().upper() != "PENDING":
            continue
        t = str(r.get("업무명") or "")
        if not any(similar(t, str(c.get("title") or "")) for c in cards):
            notes.append(("결재만있음", str(r.get("id")), t[:40]))
    return {"add": add, "fix": fix, "drop": drop, "notes": notes, "want": want}


def apply_to_schedule(want: dict, add: list, fix: list, drop: list) -> dict:
    """전사일정(GAS)까지 맞춘다 — 화면이 원천이라 pull → 고침 → push 순서를 지킨다."""
    import schedule_ssot as S
    S.pull_from_live()
    cal = S.load()
    items = [it for it in cal.get("items", []) if str(it.get("id")) not in set(drop)]
    by_sid = {str(it.get("id")): it for it in items}
    for sid in add:
        items.append(want[sid])
    for sid, what, _old, new in fix:
        it = by_sid.get(sid)
        if not it:
            continue
        it["next_due" if what == "날짜" else "assignee"] = new
    cal["items"] = items
    (ROOT / "status" / "schedule_ssot.json").write_text(
        json.dumps(cal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return S.push_to_live(cal, force=bool(drop))


def render(res: dict) -> str:
    lines = [f"🔗 네 화면 대조 — 일정 추가 {len(res['add'])} · 고침 {len(res['fix'])} · 삭제 {len(res['drop'])}"]
    for kind in ("담당없음", "기한없음", "SSOT행없음", "결재만있음", "태그빠짐", "이관됨", "중복두줄"):
        hit = [n for n in res["notes"] if n[0] == kind]
        if hit:
            lines.append(f"· {kind} {len(hit)}건 — " + " / ".join(x[2][:22] for x in hit[:4])
                         + (f" 외 {len(hit) - 4}건" if len(hit) > 4 else ""))
    return "\n".join(lines)


def _selftest() -> None:
    today = _dt.date(2026, 9, 9)
    plan = {"status_enum": ["계획", "진행", "완료", "이월"], "months": {"2026-09": {"objectives": [
        {"id": "A", "title": "가 카드 (GM 직접)", "status": "진행", "due": "2026-09-30", "dept": "운영부"},
        {"id": "B", "title": "나 카드 (GM 직접)", "status": "진행", "due": ""},
        {"id": "C", "title": "다 카드 (GM 직접)", "status": "완료", "due": "2026-09-30"},
        {"id": "D", "title": "라 카드", "status": "진행", "due": "2026-09-30"},   # 태그만 빠진 살아 있는 카드
        {"id": "E", "title": "마 카드", "status": "진행", "due": "2026-09-30",
         "progress_note": "▶[이관 2026-09-10 · GM 지시] 중간관리자 업무로 이관."},  # 이관돼 태그를 뗀 카드
    ]}}}
    items = [{"id": "gmwork-A", "next_due": "2026-09-20", "assignee": ""},
             {"id": "mop-A", "next_due": "2026-09-30", "assignee": ""},
             {"id": "gmwork-D", "next_due": "2026-09-30", "assignee": ""},
             {"id": "gmwork-E", "next_due": "2026-09-30", "assignee": ""},
             {"id": "gmwork-C", "next_due": "2026-09-30", "assignee": "이경연 실장"}]
    owners = {"A": "이경연 실장"}
    rows = [{"업무명": "가 카드", "id": "T1", "대표싸인": ""},
            {"업무명": "혼자 도는 결재 건", "id": "T2", "대표싸인": "PENDING"}]
    r = diff(plan, items, owners, rows, today=today)
    assert r["add"] == [], r["add"]                                   # A 는 이미 있다
    assert ("gmwork-A", "날짜", "2026-09-20", "2026-09-30") in r["fix"], r["fix"]
    assert ("gmwork-A", "담당", "", "이경연 실장") in r["fix"], r["fix"]
    assert r["drop"] == ["gmwork-C"], r["drop"]                       # 완료 카드의 짝만 뺀다
    assert "gmwork-D" not in r["drop"], r["drop"]                     # 태그만 빠진 살아 있는 카드는 안 지운다
    assert ("태그빠짐", "D", "라 카드") in r["notes"], r["notes"]
    assert "gmwork-E" not in r["drop"], r["drop"]                     # 이관된 카드도 안 지운다
    assert ("이관됨", "E", "마 카드") in r["notes"], r["notes"]
    assert ("태그빠짐", "E", "마 카드") not in r["notes"], r["notes"]
    assert ("중복두줄", "A", "가 카드 (GM 직접)") in r["notes"], r["notes"]
    kinds = {n[0] for n in r["notes"]}
    assert "기한없음" in kinds and "결재만있음" in kinds, r["notes"]
    assert "SSOT행없음" not in {n[0] for n in r["notes"] if n[1] == "A"}, r["notes"]
    assert similar("CCTV 전체 교체 — 93대 계약·설치", "CCTV 전체 교체")
    assert not similar("가", "")
    print("[selftest] gm_surfaces_sync OK")


def main() -> int:
    ap = argparse.ArgumentParser(description="GM업무·전사일정·업무SSOT·아침 통 대조")
    ap.add_argument("--apply", action="store_true", help="전사일정 짝을 카드에 맞춰 실제로 고친다")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
        return 0
    import schedule_ssot as S
    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    S.pull_from_live()
    res = diff(plan, S.load().get("items") or [], fetch_owners(), fetch_todo_rows())
    print(render(res))
    if a.apply and (res["add"] or res["fix"] or res["drop"]):
        print("전사일정 반영:", apply_to_schedule(res["want"], res["add"], res["fix"], res["drop"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
