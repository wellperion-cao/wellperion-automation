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

# ── AI 큐에서 배제하는 역할 (2026-07-28 GM 확정 → 2026-08-05 GM 재확정으로 해제) ──
# 2026-07-28: 인사(시로)·재무(시뽀) 앞으로는 배 생성 자체를 막았다(나우열M 직접 운영
# 영역이라 AI 항로에 섞이면 GM이 매번 걸러야 했다).
#
# 2026-08-05 GM 재확정 — "실무 처리 시로 시뽀도 배(업무) 유지하고, 실무 처리를
# ★중간관리자 방 전달 → 사람이 처리하게 해줘." 배 생성 차단(EXCLUDED_ROLES)은 이 배
# 자체를 없애 "무엇이 밀렸는지 아무도 못 보는" 부작용이 있었다 — 그래서 이 관문의
# 차단은 해제하고, 대신 **다른 두 층**으로 같은 의도(AI가 실무를 대신 하지 않음)를 지킨다:
#   1) 자율 러너(welly_auto_runner.DEFAULT_CLEVELS)가 chro·cfo·coo 앞 배를 절대 집지 않는다
#      (에이전트 미가동 — 무인 실행 대상에서 항상 제외).
#   2) 그 도메인 파일의 "직접 수정"은 scripts/safe_commit.py 의 DOMAIN_MODIFY_RULES 가
#      커밋 관문에서 차단한다(발견 시 ★중간관리자 방으로 전달만).
# 상세·GM 원문 = ssot/kpi.json _라인분담_2026_08_05_chro_cfo.
#
# 예외: 사람(GM·나우열M)이 손으로 큐를 고치는 것은 막지 않는다 — 여기 있던 차단도
# AI 가 자동으로 배를 만드는 경로에만 걸리는 것이었다.
EXCLUDED_ROLES = set()  # 2026-08-05부로 비움(정본 — 위 결정 참조). 복사 금지·import.
EXCLUDED_OWNER = "나우열M"


def excluded_role_notice(role: str) -> str:
    """배제 역할로 배를 띄우려 할 때 사람에게 보이는 한 줄. 문구 정본(복사 금지)."""
    return (
        "배를 만들지 않았습니다 — %s(%s)는 %s 관할이라 AI 큐에서 배제합니다"
        "(GM 확정 2026-07-28). 알릴 일이면 GM께 한 줄로 알리고 끝냅니다."
        % (ROLES.get(role, role), role, EXCLUDED_OWNER)
    )


def _slug(title: str) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣]+", "-", title).strip("-")
    return (s[:28] or "TASK").upper()


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "").lower()


def _strip_role_tag(s: str) -> str:
    """제목 맨 앞 '[시우]' 같은 역할 머리표를 뗀다. 중복 비교는 양쪽 다 떼고 한다."""
    return re.sub(r"^\[[^\]]*\]\s*", "", s or "")


def build_ship(args, queue):
    today = args.date or _dt.date.today().isoformat()
    role = args.to.lower()
    nick = ROLES[role]
    nos = [x.get("ship_no") or 0 for x in queue if isinstance(x, dict)]
    ship_no = (max(nos) + 1) if nos else 1
    # 배10012(2단계) — 화면표시 전용 짧은 번호. ship_no는 절대 안 건드림(내부 키·조인은
    # 여전히 ship_no). 재사용 방지 로직은 assign_short_no.next_short_no() 단일 소스.
    short_no = next_short_no(queue)

    # 제목 앞에 닉네임 태그를 붙이는 건 이 함수 몫이다. 부르는 쪽이 관례를 몰라
    # "[시토] ..." 처럼 이미 붙여 보내면 "[시토] [시토] ..." 로 겹쳤다(2026-07-24 시우 실측).
    # 받는 역할의 태그가 이미 맨 앞에 있으면 한 번만 남긴다.
    title = re.sub(r"^\s*\[\s*%s\s*\]\s*" % re.escape(nick), "", args.title)

    sender = ROLES.get((args.sender or "").lower(), args.sender or "")
    note = args.note or ""
    if getattr(args, "mine", False):
        # 내가 내 배로 올리는 경우(약속 L20 아침 자가점검) — 전달 마커는 뜻이 없다.
        note = ("[%s 자가점검 %s] " % (nick, today)) + note
    elif sender:
        note = ("[%s → %s 전달 %s] " % (sender, nick, today)) + note

    return {
        "task_id": "%s-%s-%s" % (role.upper(), today, _slug(title)),
        "clevel": role,
        "title": "[%s] %s" % (nick, title),
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
        # 판정은 설명글이 아니라 배 작성자의 선언을 먼저 믿는다(2026-07-27 GM 지적·오탐 45척 실측).
        # 선언이 없을 때만 낱말 스캔으로 폴백. audience·reversible 둘 다 기본 미선언
        # (audience 미선언=GM 항로에 남음 · reversible 미선언=선별기가 낱말 스캔으로 폴백).
        "audience": args.audience,
        "reversible": args.reversible,
        # 신규 생성 게이트(2026-08-01) — "work_type" is None(미선언)이면 선별기는
        # 기존 동작 그대로(가역만 보고 통과). "new"만 자율 후보에서 제외된다.
        "work_type": args.work_type,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="다른 C-Level에게 배를 띄워 일을 넘긴다")
    ap.add_argument("--to", required=True, choices=sorted(ROLES), help="받는 역할")
    ap.add_argument("--title", required=True, help="일의 제목(한 줄)")
    ap.add_argument("--note", default="", help="맥락·재현 방법·근거")
    ap.add_argument("--next", default="", help="받는 쪽이 할 다음 한 걸음")
    ap.add_argument("--sender", default="ceo", help="보내는 역할 (기본 ceo)")
    ap.add_argument("--mine", action="store_true",
                    help="내가 찾은 문제를 내 배로 올린다(약속 L20 아침 자가점검). --to 와 --sender 가 같아도 허용")
    ap.add_argument("--priority", default="⛴️여객선", help="🛳️크루즈 / ⛴️여객선 / ⛵돛단배")
    ap.add_argument("--module", default="home")
    ap.add_argument("--depends-on", dest="depends_on", default="")
    ap.add_argument("--date", default="", help="YYYY-MM-DD (기본 오늘)")
    ap.add_argument("--dry-run", action="store_true", help="큐에 쓰지 않고 미리보기만")
    # 선별기(welly_orchestrate._is_reversible / welly_auto_runner._is_low_risk)가 낱말 스캔보다
    # 이 선언값을 먼저 믿게 하는 필드. 둘 다 선택(필수 금지) — 06:30·07:30 무인 경로가
    # 이 스크립트를 프로그램으로 호출하므로 필수화하면 무인 가동이 죽는다.
    # ★기본값을 "ai" → 미지정으로 (2026-08-03 시토 · GM 지적 "실무 내용 맞나").
    #   audience 는 이제 **GM 항로(G1)에 보일지**를 가르는 값이다 — ai 면 자율현황으로 빠진다.
    #   기본이 "ai" 이면 분류를 빠뜨린 배가 GM 화면에서 조용히 사라진다. 미지정으로 두면
    #   G1 에 남고(안전측), 아침 보고의 '미표기 배 수'가 그걸 세어 표면화한다(이미 있는 장치).
    ap.add_argument("--audience", choices=("office", "ai"), default=None,
                     help="office=실무진·GM이 볼 일 / ai=AI 내부 살림 (미지정=GM 항로에 남음)")
    ap.add_argument("--reversible", choices=("yes", "no"), default=None,
                     help="yes/no — 미지정이면 선별기가 낱말 스캔으로 폴백")
    # 아침 루틴 4단계 권한 분기(2026-08-01 GM 확정 · 웰리 판단은 doc/wellperion-boot SKILL.md
    # §2-1 참조): update=기존 수정·고도화(가역이면 자율) / new=신규 생성(가역이어도 GM 승인).
    # 미지정(None)이면 선별기가 기존대로 통과시킨다(회귀 0 — 큐의 기존 배는 이 칸이 없다).
    ap.add_argument("--work-type", dest="work_type", choices=("update", "new"), default=None,
                     help="update=기존 수정 / new=신규 생성(미지정=선별기 기존 동작 유지)")
    args = ap.parse_args()
    args.reversible = {"yes": True, "no": False, None: None}[args.reversible]

    if args.to.lower() in EXCLUDED_ROLES:
        print(excluded_role_notice(args.to.lower()))
        print("  제목: %s" % args.title)
        return 0

    if args.to.lower() == (args.sender or "").lower() and not args.mine:
        print("! 받는 역할과 보내는 역할이 같습니다.")
        print("  내가 찾은 문제를 내 배로 올리는 거라면 --mine 을 붙이세요(약속 L20 아침 자가점검).")
        return 2

    made = {}

    def mutator(queue):
        # 중복 방지 — 같은 역할에 같은 제목의 열린 배가 있으면 그대로 둔다.
        # ★양쪽 다 '[시우]' 같은 역할 머리표를 떼고 비교한다 — 기존 배에서만 떼고
        #   들어오는 제목은 안 떼서, 머리표가 붙은 제목이면 중복 감지가 한 번도 못 걸렸다
        #   (2026-07-28 실사고: 같은 배가 2척 생성됨).
        want = _norm(_strip_role_tag(args.title))
        for it in queue:
            if not isinstance(it, dict):
                continue
            if it.get("clevel") == args.to.lower() and it.get("status") in OPEN_STATUS:
                if _norm(_strip_role_tag(it.get("title") or "")) == want:
                    # 중복을 막을 때 함께 보낸 지시(--note·--next)를 버리지 않는다.
                    # 버리면 "이미 같은 배가 있습니다"만 뜨고 지시 내용이 사라져,
                    # 보낸 쪽이 손으로 다시 붙여야 했다(2026-07-28 웰리 실측 · 배10290).
                    today = args.date or _dt.date.today().isoformat()
                    sender_nick = ROLES.get((args.sender or "").lower(), args.sender or "")
                    add = []
                    if (args.note or "").strip():
                        add.append((args.note or "").strip())
                    if (args.next or "").strip():
                        add.append("다음: " + (args.next or "").strip())
                    if add:
                        line = "- [%s%s] %s" % (
                            today, (" " + sender_nick) if sender_nick else "", " / ".join(add))
                        prev = str(it.get("note") or "")
                        if line not in prev:  # 멱등
                            it["note"] = (prev + ("\n" if prev else "") + line).strip()
                            made["absorbed"] = True
                        if (args.next or "").strip():
                            it["next"] = (args.next or "").strip()
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
        for k in ("task_id", "clevel", "title", "status", "priority", "ship_no", "short_no", "next",
                  "audience", "reversible", "work_type"):
            print("  %-10s %s" % (k, ship[k]))
        print("  note       %s" % (ship["note"][:160] or "(없음)"))
        return 0

    mutate_queue(mutator, holder="queue_dispatch")

    if "dup" in made:
        d = made["dup"]
        disp = d.get("short_no") if d.get("short_no") is not None else d.get("ship_no")
        print("이미 같은 배가 떠 있습니다 — 새로 만들지 않았습니다.")
        print("  배 %s · %s · %s" % (disp, d.get("status"), d.get("title")))
        if made.get("absorbed"):
            print("  보낸 내용(맥락·다음)은 그 배 설명에 붙였습니다 — 유실 없음.")
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
