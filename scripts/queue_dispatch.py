#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
queue_dispatch.py — 내 역할이 아닌 일을 담당 C-Level에게 '배'로 띄워 넘긴다.

왜 있나 (2026-07-23 GM 지시)
  "제 역할이 아닌 다른 C레벨 역할은 항상 배편을 띄워서 전달 시킬 수 있게 셋업해줘"
  말로 넘기면 사라진다. 넘기는 행위 자체를 큐(status/_queue.json)에 배로 남겨야
  받는 쪽이 부팅할 때 자기 항로에서 본다(약속 L15 — 큐에 없으면 항로에도 없다).

쓰는 법
  python scripts/queue_dispatch.py --to cto --title "텔레그램 링크 깨짐 수리" \
      --note "S0 진입 버튼에서 404. 재현: ..." --next "수리 후 라이브 확인 회신"
  python scripts/queue_dispatch.py --to cmo --title "..." --priority 🛳️크루즈 --dry-run

안전
  - status/_queue.json 동시 쓰기는 queue_lock.mutate_queue 로 직렬화(INC-008 대비)
  - 같은 제목의 열린 배가 이미 있으면 중복 생성하지 않는다(배 중복 방지)
"""
from __future__ import annotations
import argparse
import datetime as _dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from queue_lock import mutate_queue  # noqa: E402
from assign_short_no import next_short_no  # noqa: E402  (배10012 — 표시용 짧은 번호)

ROLES = {
    "ceo": "웰리", "cfo": "시뽀", "chro": "시로", "cmo": "시모",
    "coo": "시우", "cpo": "시포", "cto": "시토",
}
OPEN_STATUS = ("PENDING", "IN_PROGRESS")


def _slug(title: str) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣]+", "-", title).strip("-")
    return (s[:28] or "TASK").upper()


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "").lower()


def build_ship(args, queue):
    today = args.date or _dt.date.today().isoformat()
    role = args.to.lower()
    nick = ROLES[role]
    nos = [x.get("ship_no") or 0 for x in queue if isinstance(x, dict)]
    ship_no = (max(nos) + 1) if nos else 1
    # 배10012(2단계) — 화면표시 전용 짧은 번호. ship_no는 절대 안 건드림(내부 키·조인은
    # 여전히 ship_no). 재사용 방지 로직은 assign_short_no.next_short_no() 단일 소스.
    short_no = next_short_no(queue)

    sender = ROLES.get((args.sender or "").lower(), args.sender or "")
    note = args.note or ""
    if sender:
        note = ("[%s → %s 전달 %s] " % (sender, nick, today)) + note

    return {
        "task_id": "%s-%s-%s" % (role.upper(), today, _slug(args.title)),
        "clevel": role,
        "title": "[%s] %s" % (nick, args.title),
        "status": "PENDING",
        "priority": args.priority,
        "enqueued_at": today,
        "from": (args.sender or "").lower(),
        "note": note,
        "next": args.next or "담당 확인 후 진행 · 완료 시 전달자에게 1줄 회신",
        "depends_on": args.depends_on or "",
        "ship_no": ship_no,
        "short_no": short_no,
        "module": args.module,
        "surface": args.surface,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="다른 C-Level에게 배를 띄워 일을 넘긴다")
    ap.add_argument("--to", required=True, choices=sorted(ROLES), help="받는 역할")
    ap.add_argument("--title", required=True, help="일의 제목(한 줄)")
    ap.add_argument("--note", default="", help="맥락·재현 방법·근거")
    ap.add_argument("--next", default="", help="받는 쪽이 할 다음 한 걸음")
    ap.add_argument("--sender", default="ceo", help="보내는 역할 (기본 ceo)")
    ap.add_argument("--priority", default="⛴️여객선", help="🛳️크루즈 / ⛴️여객선 / ⛵돛단배")
    ap.add_argument("--module", default="home")
    ap.add_argument("--surface", default="autonomy")
    ap.add_argument("--depends-on", dest="depends_on", default="")
    ap.add_argument("--date", default="", help="YYYY-MM-DD (기본 오늘)")
    ap.add_argument("--dry-run", action="store_true", help="큐에 쓰지 않고 미리보기만")
    args = ap.parse_args()

    if args.to.lower() == (args.sender or "").lower():
        print("! 받는 역할과 보내는 역할이 같습니다. 남에게 넘기는 배만 이 도구로 만듭니다.")
        return 2

    made = {}

    def mutator(queue):
        # 중복 방지 — 같은 역할에 같은 제목의 열린 배가 있으면 그대로 둔다
        want = _norm(args.title)
        for it in queue:
            if not isinstance(it, dict):
                continue
            if it.get("clevel") == args.to.lower() and it.get("status") in OPEN_STATUS:
                if _norm(re.sub(r"^\[[^\]]*\]\s*", "", it.get("title") or "")) == want:
                    made["dup"] = it
                    return queue
        ship = build_ship(args, queue)
        made["ship"] = ship
        queue.append(ship)
        return queue

    if args.dry_run:
        from queue_lock import load_queue
        q = load_queue()
        ship = build_ship(args, q)
        print("[미리보기 — 큐에 쓰지 않음]")
        for k in ("task_id", "clevel", "title", "status", "priority", "ship_no", "short_no", "next"):
            print("  %-10s %s" % (k, ship[k]))
        print("  note       %s" % (ship["note"][:160] or "(없음)"))
        return 0

    mutate_queue(mutator, holder="queue_dispatch")

    if "dup" in made:
        d = made["dup"]
        disp = d.get("short_no") if d.get("short_no") is not None else d.get("ship_no")
        print("이미 같은 배가 떠 있습니다 — 새로 만들지 않았습니다.")
        print("  배 %s · %s · %s" % (disp, d.get("status"), d.get("title")))
        return 0

    s = made["ship"]
    disp = s.get("short_no") if s.get("short_no") is not None else s.get("ship_no")
    print("배를 띄웠습니다 → %s(%s)" % (ROLES[s["clevel"]], s["clevel"]))
    print("  배 번호 : %s" % disp)
    print("  제목    : %s" % s["title"])
    print("  다음    : %s" % s["next"])
    print("  기록    : status/_queue.json  (커밋·푸시하면 받는 쪽 항로에 뜹니다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
