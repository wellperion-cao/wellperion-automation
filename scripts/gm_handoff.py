# -*- coding: utf-8 -*-
"""gm_handoff.py — GM 이 웰리에게 넘긴 한 건을 전사일정·월간계획 카드에 한 번에 올린다.

이 관문이 실제로 닿는 면(약속 L23·L26 · 2026-09-10 진단 카드 6 으로 이름을 GM 어휘에 맞춰 다시 씀)
  ① 전사일정 — 담당·날짜 (동작)
  ② 월간계획 카드 — 진척률 (--plan 이 있을 때만 동작)
  ③ 업무&결재SSOT — **막혀 있다**(아래 TODO_UPLOAD_BLOCKED). GM업무와 결재는 두 면이 아니라
     같은 업무 SSOT 한 행의 두 칸이다. 등록은 지시받은 실무진이 직접 한다.
  ④ 중간관리자 통 — **이 관문에 없다.** GM 전달건이 실장·소장·나우열M 에게 닿는 경로는
     send_ops_digest 쪽이고 여기서 부르지 않는다. 있는 척하지 않고 「없음」으로 찍는다.

배경(GM 2026-09-04): "웰리한테 전달하면 웰리는 전사일정·GM업무·결재SSOT까지 서포트가 절실해."
  그동안은 세 화면을 건마다 손으로 따로 올려 하나씩 빠졌다(딜라이브 = 일정만, 테크노짐 = 결재만).
  이 한 줄이 관문이다 — GM 전달건은 이 명령으로만 올린다(약속 L21 · 새 저장소 없음, 기존 세 길 재사용).

쓰는 법
  등록:  python scripts/gm_handoff.py --title "…" --content "…" [--date 2026-09-09 --time 14:00]
             [--approval "GM,대표님"] [--category "[7] IT·시스템·자동화"] [--due 2026-09-11]
             [--plan 2026-08-24 --check "□ 로 추가할 체크 한 줄"] [--assignee "김남욱 GM"] [--dry-run]
             [--source 회장님|대표님]  ← 회장님·대표님 지시면 제목 앞에 「[회장님 지시] 」를 붙이고 카드 첫 줄에 남긴다(GM업무 배지 👑/🤵 · GM 지시 2026-09-15)
             [--todo-id TODO-…]  ← 실무진이 이미 올린 업무 SSOT 행이 있으면 같이 준다. --todo-id·--plan 은
             전사일정 item 의 todo_id·plan_id 칸이 되어, 전사일정 카드에 「업무」·「GM업무」 링크로 뜬다.
  완료:  python scripts/gm_handoff.py --done --todo-id TODO-… [--event-id evt-…] [--plan 2026-08-24 --check "☑ 로 바꿀 체크 원문"] [--dry-run]
  결과 마지막 줄 = 🧭 4면 표기(전사일정 · 월간계획 카드 · 업무&결재SSOT(막힘) · 중간관리자 통(없음))
             — GM 보고 표 기록위치 줄에 그대로 붙인다.

# ponytail: 면들을 순서대로 부르는 얇은 묶음 — 실패한 면은 그대로 알리고 나머지는 계속 간다(반쪽 성공을 숨기지 않는다).
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

try:  # 안전 커밋터 신선도 가드(monthly_ops_sync.py·gm_task_autocheck.py 와 동일 재사용 — 약속 L01)
    from safe_commit import refuse_if_older_than_head as _refuse_if_stale
except Exception:
    def _refuse_if_stale(*a, **k):
        return True  # 가드 모듈 로드 실패 — 막지는 않되(기존 동작 유지) 가드는 없는 셈


def _save_plan(plan: dict) -> dict | None:
    """PLAN_PATH 를 통째로 되쓰기 전 HEAD 대비 신선도 확인 — 거부 시 None 이 아닌 사유를 돌려준다."""
    new_text = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    if not _refuse_if_stale(PLAN_PATH, new_text):
        return {"ok": False, "reason": "디스크가 HEAD 보다 낡음 — 저장 거부(refuse_if_older_than_head)"}
    PLAN_PATH.write_text(new_text, encoding="utf-8")
    return None
# ★배12675 웰리 실측(2026-09-16) — 표기가 둘로 갈렸던 자리. GM_OWNER(띄어쓰기)는 전사일정
#   표시 정본(2026-09-03 통일 · kakao_report_sender.py) 이자 GM업무 카드 owner 값으로,
#   gm_surfaces_sync.card_owner() 가 어차피 화면에 띄울 때 다시 이 모양으로 편다 — 그대로 둔다.
#   GM_CREATOR(안 띄움)는 GAS 업무 SSOT(todo_list) 가림 규칙이 실제로 매칭하는 표기다 —
#   GAS 로 쓰는 자리(add_todo 의 owner 기본값)는 이 값을 써야 한다.
GM_OWNER = "김남욱 GM"
GM_CREATOR = "김남욱GM"


def _today() -> _dt.date:
    return _dt.date.today()


# ── 전사일정 ────────────────────────────────────────────────────────────────
def add_schedule(title: str, date: str, time: str, assignee: str, note: str, dry: bool,
                 todo_id: str = "", plan_id: str = "") -> dict:
    import schedule_ssot as S
    import ops_daily_digest as o
    slug = "".join(ch for ch in title if ch.isalnum())[:24]
    item = {"id": f"evt-{date.replace('-', '')}-gm-{slug}", "type": "이벤트", "name": title,
            "category": "meeting", "dept": "경영지원부", "cycle": "", "cycle_confirmed": False,
            "period_months": None, "legal_basis": "", "assignee": assignee, "last_done": "",
            "next_due": date, "time": time or "", "evidence": "", "applies": "있음", "vendor_id": "",
            "repeat": "", "source": f"GM 지시 {_today().isoformat()} (gm_handoff)", "note": note,
            # 열쇠 두 칸 — 전사일정 카드에서 업무 SSOT 행·GM업무 카드로 바로 건너가는 링크의 재료다.
            # GAS saveSchedule_ 은 item 을 JSON 통째로 속성창에 넣고(전사_일정.js:211 propSet_),
            # 화면도 읽어 온 객체를 그 자리에서 고쳐 통째로 되돌려 보낸다(전사_일정.html:701,831).
            # 그래서 모르는 칸도 왕복에서 안 지워진다 — source·note 에 끼워 넣는 우회가 필요 없다.
            "todo_id": todo_id or "", "plan_id": plan_id or ""}
    # GM 지시 2026-09-07 "전사일정에 중복되는 것들이 보이는데 한번씩 정리해줘"(오늘 9쌍 손 병합 실측)
    # — 카톡 다리(_schedule_is_dup)에만 있던 중복 관문을 사람 경로에도 재사용해 건다. --dry 도 같은 판정.
    items = S.load().get("items") or []
    dup_name = o._schedule_is_dup(title, date, items)
    if dup_name:
        hit = next((it for it in items if it.get("name") == dup_name), None)
        print(f"[일정] 중복 — 기존 '{dup_name}' 그대로 씀")
        return {"ok": True, "dup": True, "id": (hit or {}).get("id"), "name": dup_name}
    if dry:
        print("[일정·미리보기] " + json.dumps(item, ensure_ascii=False))
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
# ★GM 지시 2026-09-09 — "GM업무가 업무SSOT에 업로드하는건 절대 안되. 내가 지시를 하면 그 업무를
#   중간관리자+실무진들이 업무 SSOT에 올려서 결재SSOT 나까지 오게해야해."
#   그래서 이 도구는 더 이상 업무 SSOT 행을 만들지 않는다. 등록은 지시를 받은 사람이 직접 한다 —
#   AI 가 대신 올리면 주인 없는 행이 쌓이고(2026-08-18 규칙과 같은 줄기), 결재가 GM 에게 올라오는
#   길도 사람 손을 안 거친 채 열린다. 전사일정·월간운영계획(GM업무 카드)·진척 덧붙이기는 그대로 둔다.
#   되돌리려면 GM 채팅 지시 한 줄이 있어야 한다(이 상수를 코드에서 임의로 바꾸지 않는다).
TODO_UPLOAD_BLOCKED = True


def add_todo(title: str, content: str, category: str, due: str, approval: str, dry: bool,
             owner: str = GM_CREATOR) -> dict:
    """owner 기본 = 김남욱GM(안 띄움 · GAS 가림 기준 표기 — 배12675). ★2026-09-09 부터 이 길은
    막혀 있다(위 TODO_UPLOAD_BLOCKED 주석). 막힌 이유를 그대로 돌려주어 호출부가 사람에게 보여 준다."""
    if TODO_UPLOAD_BLOCKED:
        return {"ok": False, "blocked": True,
                "reason": "업무 SSOT 등록은 AI 가 하지 않는다(GM 지시 2026-09-09) — 지시를 받은 실무진이 직접 올린다"}
    import ops_daily_digest as o
    params = {"action": "todo_add", "title": title, "category": category, "owner": owner or GM_CREATOR,
              "startDate": _today().isoformat(), "endDate": due, "content": content,
              "link": "", "approval": approval, "difficulty": "중", "creator": GM_CREATOR}
    if dry:
        return {"ok": True, "dry": True, "id": "TODO-(미리보기)"}
    return o._todo_post(params) or {"ok": False, "reason": "응답 없음"}


GM_KEY = "1531"  # GM 행(결재 SSOT)은 gmkey 없이는 조회에 안 나온다 — 중복 검사는 반드시 이 키로


GM_TAG = "(GM 직접)"   # _gm_direct_tasks.js GM_TAG 와 같은 값 — GM업무 화면 편입 판정


def _title_head(title: str) -> str:
    head = str(title or "").split(" — ")[0].split("(")[0]
    return "".join(ch for ch in head if ch.isalnum()).lower()


def find_open_duplicate(title: str) -> dict | None:
    """열린 행 중 제목 머리가 닮은 것(difflib ≥ 0.75). 2026-09-07 같은 날 두 번 중복 등록한 뒤 박은 가드."""
    import difflib
    import ops_daily_digest as o
    rows = o._gas_get(o.SSOT_API_URL, params={"action": "todo_list", "include_gm": "1", "gmkey": GM_KEY},
                      timeout=40, label="gm_handoff dup").json().get("data") or []
    key = _title_head(title)
    if not key:
        return None
    for r in rows:
        if r.get("상태") == "완료":
            continue
        t = _title_head(r.get("업무명"))
        if t and difflib.SequenceMatcher(None, key, t).ratio() >= 0.75:
            return r
    return None


def append_todo(todo_id: str, line: str, dry: bool) -> dict:
    """GM업무 한 행의 내용 끝에 진척 한 줄을 덧붙인다(GM 2026-09-05 "G1에 계속 업데이트").
    todo_update 는 전 칸을 다시 보내야 하므로 현재 행을 읽어 내용만 늘린다. 행이 없으면 실패를 그대로 돌려준다."""
    import ops_daily_digest as o
    # gmkey 없이 부르면 GM 행이 목록에서 빠져 "행 없음"이 된다(2026-09-07 실측 — 결재 SSOT 유리문 건).
    rows = o._gas_get(o.SSOT_API_URL, params={"action": "todo_list", "include_gm": "1", "gmkey": GM_KEY},
                      timeout=40, label="gm_handoff append").json().get("data") or []
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
    fail = _save_plan(plan)
    if fail:
        return fail
    return {"ok": True}


def new_card(title: str, content: str, due: str, dry: bool, category: str = "", source: str = "") -> dict:
    """GM업무 카드(월간운영계획 이번 달 objectives · 담당 김남욱 GM) 새로 만들기 — GM 본인 건이 --plan 없이
    들어오면 이 카드가 「GM업무」 면이다(GM 지시 2026-09-14 「GM업무/전사일정/중간관리자/업무&결재SSOT 연동 놓치지 말고
    셋업」). 업무 SSOT 행은 여전히 안 만든다(TODO_UPLOAD_BLOCKED) — GM업무 = 이 카드, 결재 = 사람이 SSOT 에.
    같은 제목의 카드가 이번 달에 이미 있으면 새로 만들지 않고 그 id 를 돌려준다."""
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    ym = _today().strftime("%Y-%m")
    month = plan.setdefault("months", {}).setdefault(ym, {})
    objs = month.setdefault("objectives", [])
    key = "".join(title.split())[:24]
    for o in objs:
        if "".join(str(o.get("title") or "").split())[:24] == key and "김남욱" in str(o.get("owner") or ""):
            return {"ok": True, "id": o.get("id"), "existing": True}
    nums = [int(str(o.get("id") or "").rsplit("-", 1)[-1]) for o in objs
            if str(o.get("id") or "").startswith(ym + "-") and str(o.get("id") or "").rsplit("-", 1)[-1].isdigit()]
    cid = f"{ym}-{(max(nums) + 1) if nums else 1:02d}"
    today = _today().isoformat()
    # 제목 태그 「(GM 직접)」— GM업무 화면(_gm_direct_tasks.js isGmDirect)은 이 태그가 있는 카드만 싣는다.
    #   태그 없이 만들면 카드는 있는데 GM업무엔 안 보인다(2026-09-15 실측 · 09-32). 화면은 태그를 떼고 그린다.
    if GM_TAG not in title:
        title = f"{title} {GM_TAG}"
    src_line = f"▶[{source} 지시 · GM 전달 {today}]\n" if source else ""
    card = {
        "id": cid, "initiative_id": "", "owner": GM_OWNER, "dept": "경영지원부", "title": title,
        "target": content[:300], "metric": "", "status": "진행", "progress": 0, "northstar": "",
        "progress_note": f"{src_line}■ 할 일\n□ [GM 지시 {today}] {content[:200]} — 담당: {GM_CREATOR} · 기한: {due or '(미정)'}",
        "honesty": {"level": "manual", "label": "📝 사람값", "basis": "GM 지시 · gm_handoff 생성", "at": today},
        "due": due or "",
    }
    if category:
        card["category"] = category
    if dry:
        return {"ok": True, "dry": True, "id": cid}
    objs.append(card)
    fail = _save_plan(plan)
    if fail:
        return fail
    return {"ok": True, "id": cid}


def _mark(res: dict) -> str:
    if not res:
        return "—"
    return ("✔" if res.get("ok") else "✖ " + str(res.get("reason") or res.get("error") or "")) + (" (미리보기)" if res.get("dry") else "")


def main() -> int:
    ap = argparse.ArgumentParser(description="GM 전달건 → 전사일정·월간계획 카드 한 번에 (업무&결재SSOT 는 막힘 · 중간관리자 통은 이 관문에 없음)")
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
    ap.add_argument("--done", action="store_true", help="완료 모드 — 전사일정·월간계획 카드·업무&결재SSOT 를 같이 닫는다")
    ap.add_argument("--append", metavar="LINE", help="GM업무 --todo-id 행 내용 끝에 진척 한 줄 덧붙임(날짜 자동)")
    ap.add_argument("--todo-id", help="업무 SSOT 행 id — 등록 때 주면 전사일정 카드에서 그 행으로 가는 링크가 생긴다")
    ap.add_argument("--event-id")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="닮은 열린 행이 있어도 새로 등록(정말 다른 건일 때만)")
    ap.add_argument("--source", choices=["회장님", "대표님"],
                    help="지시 출처 — 제목 앞에 「[회장님 지시] 」/「[대표님 지시] 」를 붙이고 GM업무 카드 첫 줄에 남긴다(👑/🤵 배지)")
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
        print(f"🧭 4면(완료) — 전사일정 {_mark(r_evt)} · 월간계획 카드 {_mark(r_plan)}"
              f" · 업무&결재SSOT {_mark(r_todo)} · 중간관리자 통 —(이 관문에 없음)")
        return 0

    if not a.title:
        ap.error("--title 필요")
    if a.source and not a.title.startswith(f"[{a.source} 지시]"):
        a.title = f"[{a.source} 지시] {a.title}"
    if not a.force:
        dup = find_open_duplicate(a.title)
        if dup:
            print(f"✖ 같은 건이 이미 있습니다 — {dup.get('id')} 「{dup.get('업무명')}」 (상태 {dup.get('상태')})."
                  f" 갱신은 --append LINE --todo-id {dup.get('id')}, 정말 다른 건이면 --force")
            return 2
    due = a.due or a.date or (_today() + _dt.timedelta(days=7)).isoformat()
    r_evt = add_schedule(a.title, a.date, a.time, a.assignee, a.content[:300], dry,
                         todo_id=a.todo_id or "", plan_id=a.plan or "") if a.date else None
    r_todo = add_todo(a.title, a.content, a.category, due, a.approval, dry, owner=a.assignee)
    if r_todo.get("blocked"):
        # 막힌 것은 실패가 아니라 규칙이다 — 사람이 무엇을 해야 하는지 한 줄로 알린다.
        print("🚫 업무 SSOT 등록은 하지 않았습니다 — 지시를 받은 실무진이 직접 올립니다(GM 지시 2026-09-09).")
    if a.plan:
        r_plan = touch_plan(a.plan, f"{a.title} — GM업무 {r_todo.get('id', '')}" + (f" · 전사일정 {r_evt.get('id')}" if r_evt else ""),
                            a.check, False, dry)
    elif (a.assignee or GM_OWNER) == GM_OWNER:
        # GM 본인 건인데 카드가 없으면 GM업무 카드를 새로 낸다 — 전사일정만 남고 GM업무 면이 비던 것을 막는다(2026-09-14).
        r_plan = new_card(a.title, a.content, due, dry, a.category, a.source or "")
        a.plan = r_plan.get("id", "")
    else:
        r_plan = None
    # GM업무·결재는 두 면이 아니라 업무 SSOT 한 행의 두 칸이라 한 칸으로 찍는다(진단 카드 6).
    ssot = ("🚫 막힘 — 실무진 직접 등록" + (f"(결재 {a.approval} 미기재)" if a.approval else "")
            if r_todo.get("blocked")
            else f"{_mark(r_todo)} {r_todo.get('id', '')}"
                 + (f" · 결재 {a.approval}" if a.approval else ""))
    print(f"🧭 4면 — 전사일정 {_mark(r_evt)}{(' ' + r_evt.get('id', '')) if r_evt and r_evt.get('ok') else ''}"
          f" · 월간계획 카드 {_mark(r_plan)}{(' ' + a.plan) if a.plan else ''}"
          f" · 업무&결재SSOT {ssot}"
          f" · 중간관리자 통 —(이 관문에 없음)")
    return 0 if (r_todo.get("ok") or r_todo.get("blocked")) else 1


if __name__ == "__main__":
    sys.exit(main())
