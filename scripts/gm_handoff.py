# -*- coding: utf-8 -*-
"""gm_handoff.py — GM 이 웰리에게 넘긴 한 건을 세 화면(전사일정·GM업무·결재 SSOT)에 한 번에 올린다.

배경(GM 2026-09-04): "웰리한테 전달하면 웰리는 전사일정·GM업무·결재SSOT까지 서포트가 절실해."
  그동안은 세 화면을 건마다 손으로 따로 올려 하나씩 빠졌다(딜라이브 = 일정만, 테크노짐 = 결재만).
  이 한 줄이 관문이다 — GM 전달건은 이 명령으로만 올린다(약속 L21 · 새 저장소 없음, 기존 세 길 재사용).

세 화면의 역할(약속 L23·L26) — 전사일정 = 담당·날짜 / GM업무(업무 SSOT) = 실행·체크리스트 /
결재 SSOT = 같은 업무 SSOT 행에 결재요청 칸이 채워진 것 / 월간운영계획 = 진척률(카드가 있을 때만 연결).

쓰는 법
  등록:  python scripts/gm_handoff.py --title "…" --content "…" [--date 2026-09-09 --time 14:00]
             [--approval "GM,대표님"] [--category "[7] IT·시스템·자동화"] [--due 2026-09-11]
             [--plan 2026-08-24 --check "□ 로 추가할 체크 한 줄"] [--assignee "김남욱 GM"] [--dry-run]
  완료:  python scripts/gm_handoff.py --done --todo-id TODO-… [--event-id evt-…] [--plan 2026-08-24 --check "☑ 로 바꿀 체크 원문"] [--dry-run]
  결과 마지막 줄 = 🧭 4면 표기(전사일정 · GM업무 · 결재 · 월간계획) — GM 보고 표 기록위치 줄에 그대로 붙인다.

# ponytail: 세 화면을 순서대로 부르는 얇은 묶음 — 실패한 면은 그대로 알리고 나머지는 계속 간다(반쪽 성공을 숨기지 않는다).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

PLAN_PATH = ROOT / "status" / "monthly_ops_plan.json"
GM_OWNER = "김남욱 GM"
GM_CREATOR = "김남욱GM"


def _today() -> _dt.date:
    return _dt.date.today()


# ── 전사일정 ────────────────────────────────────────────────────────────────
def add_schedule(title: str, date: str, time: str, assignee: str, note: str, dry: bool) -> dict:
    import schedule_ssot as S
    import ops_daily_digest as o
    slug = "".join(ch for ch in title if ch.isalnum())[:24]
    item = {"id": f"evt-{date.replace('-', '')}-gm-{slug}", "type": "이벤트", "name": title,
            "category": "meeting", "dept": "경영지원부", "cycle": "", "cycle_confirmed": False,
            "period_months": None, "legal_basis": "", "assignee": assignee, "last_done": "",
            "next_due": date, "time": time or "", "evidence": "", "applies": "있음", "vendor_id": "",
            "repeat": "", "source": f"GM 지시 {_today().isoformat()} (gm_handoff)", "note": note}
    # GM 지시 2026-09-07 "전사일정에 중복되는 것들이 보이는데 한번씩 정리해줘"(오늘 9쌍 손 병합 실측)
    # — 카톡 다리(_schedule_is_dup)에만 있던 중복 관문을 사람 경로에도 재사용해 건다. --dry 도 같은 판정.
    items = S.load().get("items") or []
    dup_name = o._schedule_is_dup(title, date, items)
    if dup_name:
        hit = next((it for it in items if it.get("name") == dup_name), None)
        print(f"[일정] 중복 — 기존 '{dup_name}' 그대로 씀")
        return {"ok": True, "dup": True, "id": (hit or {}).get("id"), "name": dup_name}
    if dry:
        return {"ok": True, "dry": True, "id": item["id"]}
    S.pull_from_live()
    res = S.add_event(item)
    res["id"] = item["id"]
    return res


def close_schedule(event_id: str, dry: bool) -> dict:
    import schedule_ssot as S
    S.pull_from_live()
    cal = S.load()
    hit = next((x for x in cal.get("items", []) if x.get("id") == event_id), None)
    if not hit:
        return {"ok": False, "reason": "일정 없음"}
    if dry:
        return {"ok": True, "dry": True}
    hit["last_done"] = _today().isoformat()
    hit["note"] = (hit.get("note") or "") + f" / [완료 {_today().isoformat()} · gm_handoff]"
    res = S.push_to_live(cal)
    if res.get("ok"):
        S.CAL_PATH.write_text(json.dumps(cal, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


# ── GM업무 · 결재 SSOT (같은 업무 SSOT 행) ───────────────────────────────────
def add_todo(title: str, content: str, category: str, due: str, approval: str, dry: bool,
             owner: str = GM_OWNER) -> dict:
    """owner 기본 = 김남욱 GM. ★실무진이 실행하는 건은 --assignee 로 그 사람을 담당에 넣는다 — 담당이 GM 이면
    GM업무 화면에 GM 이 할 일로 뜬다(GM 지적 2026-09-05 "다 김남욱GM 이라고 해놓으면 내가 해야하는거 아냐?")."""
    import ops_daily_digest as o
    params = {"action": "todo_add", "title": title, "category": category, "owner": owner or GM_OWNER,
              "startDate": _today().isoformat(), "endDate": due, "content": content,
              "link": "", "approval": approval, "difficulty": "중", "creator": GM_CREATOR}
    if dry:
        return {"ok": True, "dry": True, "id": "TODO-(미리보기)"}
    return o._todo_post(params) or {"ok": False, "reason": "응답 없음"}


def append_todo(todo_id: str, line: str, dry: bool) -> dict:
    """GM업무 한 행의 내용 끝에 진척 한 줄을 덧붙인다(GM 2026-09-05 "G1에 계속 업데이트").
    todo_update 는 전 칸을 다시 보내야 하므로 현재 행을 읽어 내용만 늘린다. 행이 없으면 실패를 그대로 돌려준다."""
    import ops_daily_digest as o
    rows = o._gas_get(o.SSOT_API_URL, params={"action": "todo_list", "include_gm": "1"}, timeout=40,
                      label="gm_handoff append").json().get("data") or []
    row = next((r for r in rows if str(r.get("id")) == todo_id), None)
    if not row:
        return {"ok": False, "reason": f"행 없음 {todo_id}"}
    content = (row.get("내용") or "").rstrip() + f"\n[{_today().isoformat()}] {line}"
    params = {"action": "todo_update", "id": todo_id, "title": row.get("업무명", ""), "category": row.get("카테고리", ""),
              "owner": row.get("담당자", ""), "startDate": str(row.get("시작일", ""))[:10], "endDate": str(row.get("종료일", ""))[:10],
              "content": content, "approval": row.get("결재요청", "")}
    if dry:
        return {"ok": True, "dry": True, "content": content}
    return o._todo_post(params) or {"ok": False, "reason": "응답 없음"}


def close_todo(todo_id: str, dry: bool) -> dict:
    import ops_daily_digest as o
    if dry:
        return {"ok": True, "dry": True}
    return o._todo_post({"action": "todo_done", "id": todo_id}) or {"ok": False, "reason": "응답 없음"}


# ── 월간운영계획 (카드가 있을 때만) ───────────────────────────────────────────
def _find_card(obj, card_id: str):
    if isinstance(obj, dict):
        if obj.get("id") == card_id and "progress_note" in obj:
            return obj
        for v in obj.values():
            r = _find_card(v, card_id)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_card(v, card_id)
            if r:
                return r
    return None


def touch_plan(card_id: str, line: str, check: str, mark_done: bool, dry: bool) -> dict:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    card = _find_card(plan, card_id)
    if not card:
        return {"ok": False, "reason": f"카드 {card_id} 없음"}
    pn = card.get("progress_note") or ""
    if check:
        if mark_done:
            src = check if check.startswith("□") else "□ " + check
            if src not in pn:
                return {"ok": False, "reason": "체크 원문을 못 찾음"}
            pn = pn.replace(src, "☑ " + src[2:].rstrip() + f" (완료 {_today().isoformat()})", 1)
        else:
            pn += "\n" + (check if check.startswith(("□", "☑")) else "□ " + check)
    if line:
        pn += f"\n[{_today().isoformat()} gm_handoff] {line}"
    if dry:
        return {"ok": True, "dry": True}
    card["progress_note"] = pn
    PLAN_PATH.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True}


def _mark(res: dict) -> str:
    if not res:
        return "—"
    return ("✔" if res.get("ok") else "✖ " + str(res.get("reason") or res.get("error") or "")) + (" (미리보기)" if res.get("dry") else "")


def main() -> int:
    ap = argparse.ArgumentParser(description="GM 전달건 → 전사일정·GM업무·결재 SSOT 한 번에")
    ap.add_argument("--title")
    ap.add_argument("--content", default="")
    ap.add_argument("--date", help="있으면 전사일정에도 올린다 (YYYY-MM-DD)")
    ap.add_argument("--time", default="")
    ap.add_argument("--assignee", default=GM_OWNER)
    ap.add_argument("--category", default="[9] 회의")
    ap.add_argument("--due", help="GM업무 기한 (기본 = --date 또는 오늘+7)")
    ap.add_argument("--approval", default="", help="결재 라인. 금액·계약·발주면 'GM,대표님'")
    ap.add_argument("--plan", help="월간운영계획 카드 id (있을 때만)")
    ap.add_argument("--check", default="", help="카드에 얹을 체크 한 줄(등록) / ☑ 로 바꿀 체크 원문(--done)")
    ap.add_argument("--done", action="store_true", help="완료 모드 — 세 면을 같이 닫는다")
    ap.add_argument("--append", metavar="LINE", help="GM업무 --todo-id 행 내용 끝에 진척 한 줄 덧붙임(날짜 자동)")
    ap.add_argument("--todo-id")
    ap.add_argument("--event-id")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    dry = a.dry_run

    if a.append:
        if not a.todo_id:
            ap.error("--append 는 --todo-id 필요")
        r = append_todo(a.todo_id, a.append, dry)
        print(f"🧭 GM업무 {_mark(r)} {a.todo_id}" + (f"\n{r.get('content')}" if dry else "") + ("" if r.get("ok") else f" — {r.get('reason')}"))
        return 0 if r.get("ok") else 1

    if a.done:
        r_todo = close_todo(a.todo_id, dry) if a.todo_id else None
        r_evt = close_schedule(a.event_id, dry) if a.event_id else None
        r_plan = touch_plan(a.plan, f"완료 — GM업무 {a.todo_id or ''}", a.check, True, dry) if a.plan else None
        print(f"🧭 4면(완료) — 전사일정 {_mark(r_evt)} · GM업무 {_mark(r_todo)} · 월간계획 {_mark(r_plan)}")
        return 0

    if not a.title:
        ap.error("--title 필요")
    due = a.due or a.date or (_today() + _dt.timedelta(days=7)).isoformat()
    r_evt = add_schedule(a.title, a.date, a.time, a.assignee, a.content[:300], dry) if a.date else None
    r_todo = add_todo(a.title, a.content, a.category, due, a.approval, dry, owner=a.assignee)
    r_plan = touch_plan(a.plan, f"{a.title} — GM업무 {r_todo.get('id', '')}" + (f" · 전사일정 {r_evt.get('id')}" if r_evt else ""),
                        a.check, False, dry) if a.plan else None
    print(f"🧭 4면 — 전사일정 {_mark(r_evt)}{(' ' + r_evt.get('id', '')) if r_evt and r_evt.get('ok') else ''}"
          f" · GM업무 {_mark(r_todo)} {r_todo.get('id', '')}"
          f" · 결재 {'✔ ' + a.approval if a.approval else '—'}"
          f" · 월간계획 {_mark(r_plan)}{(' ' + a.plan) if a.plan else ''}")
    return 0 if r_todo.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
