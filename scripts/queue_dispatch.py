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
    # cbo=시보 — 2026-09-02 GM 신설(비즈니스 확대·업체간 진행 C레벨 권한).
    "cbo": "시보",
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
#
# ★2026-08-21 GM 재확정 — 다시 막는다. GM 원문: "나우열M 관할 배편은 삭제해 시로+시뽀".
# 위 2026-08-05 해제를 오늘 GM 이 뒤집었다. 그날 열려 있던 시로 배 3척(1241·9433·10307)은
# status="EXCLUDED" 로 status/_queue_archive.json 에 옮겼다 — 기록은 남기고 항로·큐에서만
# 내린다. "무엇이 밀렸는지 안 보인다"는 2026-08-05 의 우려는 GM 이 감수하기로 한 것이다
# (그 도메인은 나우열M 이 자기 방식으로 관리하며, AI 항로에 섞이면 GM 이 매번 걸러야 한다).
EXCLUDED_ROLES = {"chro", "cfo"}  # 정본 — 복사 금지·import 해서 쓴다.
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
    # 이미 쓰는 번호면 비켜 간다. max+1 만으로는 보관함에서 되살린 배·다른 경로가 복사해 넣은
    # 번호와 부딪힐 수 있다 — 2026-08-11 실측: 배39(진행중)와 배535(대기)가 같은 9640 을 써서
    # 상태줄이 진행중 자리에 대기 배를 찍었고, GM 이 "535 진행 중이야?"라고 되물었다.
    used = {x.get("ship_no") for x in queue if isinstance(x, dict)}
    while ship_no in used:
        ship_no += 1
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
        # 내가 내 배로 올리는 경우 — 전달 마커는 뜻이 없다. 대신 누가 기다리는지를 남긴다
        # (배가 되려면 사람이 기다리고 있어야 한다 · 약속 L20 · GM 확정 2026-08-19).
        waiting = (getattr(args, "waiting", "") or "").strip()
        note = ("[%s %s · 기다리는 쪽: %s] " % (nick, today, waiting)) + note
    elif sender:
        note = ("[%s → %s 전달 %s] " % (sender, nick, today)) + note

    # ★2026-08-26 시토 — task_id 는 배마다 달라야 한다(배798 감사에서 실제 충돌 발견).
    #   슬러그는 제목 앞부분만 잘라 쓰므로, 같은 날 같은 역할에 앞머리가 같은 제목이 두 번 오면
    #   (예: "★중간관리자 방 호출 — 이경연 실장님: …" 두 건) task_id 가 똑같이 만들어진다.
    #   hangro_board 는 task_id 로 중복을 거르므로 뒤에 온 배를 **조용히 버렸다** —
    #   실측: 큐에 33척인데 아침 보고는 32척이었다(손소독제 회신 배가 사라짐).
    #   같은 id 가 이미 있으면 배 번호를 붙여 가른다. 배 번호는 배마다 고정·불변이라 안전하다.
    _tid = "%s-%s-%s" % (role.upper(), today, _slug(title))
    if any(isinstance(t, dict) and str(t.get("task_id")) == _tid for t in queue):
        _tid = "%s-%s" % (_tid, ship_no)

    return {
        "task_id": _tid,
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
        # 실무진(사람) 방으로 나가는 한 줄. send_ops_digest 가 이 칸만 읽어 카톡에 싣고,
        # 비어 있으면 그 배는 아예 안 싣는다(잘린 배 제목을 보내던 것을 2026-08-06 배423 에서
        # 끊었다). 즉 이 칸이 비면 그 일은 사람에게 영원히 안 알려진다 — 아래 경고가 그 자리다.
        "staff_message": args.staff_message or "",
        # 🎯 오늘 반드시 끝낼 것(GM 2026-08-10) — YYYY-MM-DD, 미지정이면 빈 문자열(일반 배).
        "must_finish_on": args.must_finish or "",
    }


# 이 역할 앞으로 띄운 배는 아침 카톡으로 사람 방에 중계된다(send_ops_digest).
# 시우→★운영부(최준용M) · 시로·시뽀→★중간관리자(나우열M).
RELAYED_ROLES = {"coo", "chro", "cfo"}


def _warn_missing_staff_message(ship: dict) -> None:
    """사람 방으로 중계되는 역할인데 전달문이 비면 크게 알린다(막지는 않는다).

    막지 않는 이유: 여기서 배 생성을 거부하면 일 자체가 기록되지 않아 더 나쁘다.
    경고인 이유: 배423 이후 전달문 없는 배는 카톡에 안 실린다 — 즉 이 칸을 비우면
    그 일은 사람에게 영영 안 알려지고, 아무도 그 사실을 모른다(조용한 실패).
    """
    if ship.get("clevel") in RELAYED_ROLES and not str(ship.get("staff_message") or "").strip():
        print("  ⚠ 실무진 전달문(--staff-message)이 비었습니다 — 이 배는 아침 카톡으로 "
              "사람 방에 나가지 않습니다.")
        print("    사람이 받아야 하는 일이면 --staff-message 에 '무엇을·왜·무엇을 해주면 "
              "되는지' 한 줄을 넣어 다시 띄우거나, 큐에서 이 배의 staff_message 칸을 채우세요.")


def main() -> int:
    ap = argparse.ArgumentParser(description="다른 C-Level에게 배를 띄워 일을 넘긴다")
    ap.add_argument("--to", required=True, choices=sorted(ROLES), help="받는 역할")
    ap.add_argument("--title", required=True, help="일의 제목(한 줄)")
    ap.add_argument("--note", default="", help="맥락·재현 방법·근거")
    ap.add_argument("--next", default="", help="받는 쪽이 할 다음 한 걸음")
    ap.add_argument("--sender", default="ceo", help="보내는 역할 (기본 ceo)")
    ap.add_argument("--mine", action="store_true",
                    help="내가 찾은 문제를 내 배로 올린다. --to 와 --sender 가 같아도 허용. "
                         "★자가점검에서 그냥 발견한 것은 배로 만들지 않는다 — --waiting 필요(약속 L20)")
    ap.add_argument("--waiting", default="",
                    help="누가 이 일을 기다리는지 한 줄(실무진 이름·GM·장애 내용). "
                         "--mine 으로 내 배를 만들 때 필수 — 기다리는 사람이 없으면 배가 아니라 아침 점검 표에 적는다")
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
    ap.add_argument("--staff-message", dest="staff_message", default="",
                    help="실무진(사람)에게 카톡으로 나갈 한 줄 — 무엇을·왜·무엇을 해주면 되는지. "
                         "비우면 이 배는 사람 방에 안 실린다(배423).")
    ap.add_argument("--work-type", dest="work_type", choices=("update", "new"), default=None,
                     help="update=기존 수정 / new=신규 생성(미지정=선별기 기존 동작 유지)")
    # 🎯 오늘 반드시 끝낼 것(GM 2026-08-10 지시 — "무조건 진척을 마무리 해야하는 건도 1~2개씩
    # 기록해서 내가 계속 놓치지 않게끔"). 새 스크립트·새 원장 없이 이 관문(배 생성·중복흡수
    # 단일 지점)에 얹는다 — 이미 배를 다루는 유일한 곳이라(약속 L21).
    ap.add_argument("--must-finish", dest="must_finish", nargs="?", const="TODAY", default="",
                     metavar="YYYY-MM-DD",
                     help="오늘 반드시 끝낼 배로 지목. 값 생략=오늘 날짜, 날짜를 직접 주면 그 날짜로 "
                          "지목(예: 못 지킨 걸 소급 기록). hangro_board 맨 위·자율현황·08시 보고에 뜬다 — "
                          "다음날까지 안 끝나면 status=DONE 될 때까지 조용히 안 사라진다.")
    args = ap.parse_args()
    args.reversible = {"yes": True, "no": False, None: None}[args.reversible]
    if args.must_finish == "TODAY":
        args.must_finish = _dt.date.today().isoformat()

    if args.to.lower() in EXCLUDED_ROLES:
        print(excluded_role_notice(args.to.lower()))
        print("  제목: %s" % args.title)
        return 0

    if args.to.lower() == (args.sender or "").lower() and not args.mine:
        print("! 받는 역할과 보내는 역할이 같습니다.")
        print("  내가 찾은 문제를 내 배로 올리는 거라면 --mine 을 붙이세요(약속 L20 아침 자가점검).")
        return 2

    # ★자가점검 발견은 배가 되지 않는다 (GM 확정 2026-08-19 · 약속 L20).
    #   배가 되는 것은 사람이 답을 기다릴 때뿐이다 — 실무진 신고 / GM 지시 / 실제 장애.
    #   그냥 "고치면 더 좋겠다" 는 아침 점검 표에 적고 GM 이 전달해 주시면 그때 배가 된다.
    #   문서로만 두면 안 지켜져서 관문에 박는다(약속 L02).
    if args.mine and not args.waiting.strip():
        print("! 자가점검에서 찾은 것은 배로 만들지 않습니다 (GM 확정 2026-08-19 · 약속 L20).")
        print("  아침 점검 표에 한 줄로 적고, GM 이 보시고 전달해 주시면 그때 배로 만드세요.")
        print('  사람이 답을 기다리는 건이면 누가 기다리는지 적으세요: --waiting "임정은M 회신 대기"')
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
                    if (args.must_finish or "").strip():
                        it["must_finish_on"] = args.must_finish
                        made["must_finish_absorbed"] = True
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
                  "audience", "reversible", "work_type", "must_finish_on"):
            print("  %-10s %s" % (k, ship[k]))
        print("  note       %s" % (ship["note"][:160] or "(없음)"))
        _warn_missing_staff_message(ship)
        return 0

    mutate_queue(mutator, holder="queue_dispatch")

    if "dup" in made:
        d = made["dup"]
        disp = d.get("short_no") if d.get("short_no") is not None else d.get("ship_no")
        print("이미 같은 배가 떠 있습니다 — 새로 만들지 않았습니다.")
        print("  배 %s · %s · %s" % (disp, d.get("status"), d.get("title")))
        if made.get("absorbed"):
            print("  보낸 내용(맥락·다음)은 그 배 설명에 붙였습니다 — 유실 없음.")
        if made.get("must_finish_absorbed"):
            print("  🎯 반드시 끝낼 것으로 지목: %s" % d.get("must_finish_on"))
        return 0

    s = made["ship"]
    disp = s.get("short_no") if s.get("short_no") is not None else s.get("ship_no")
    print("배를 띄웠습니다 → %s(%s)" % (ROLES[s["clevel"]], s["clevel"]))
    _warn_missing_staff_message(s)
    print("  배 번호 : %s" % disp)
    print("  제목    : %s" % s["title"])
    print("  다음    : %s" % s["next"])
    if s.get("must_finish_on"):
        print("  🎯 반드시 끝낼 것 : %s" % s["must_finish_on"])
    print("  기록    : status/_queue.json  (커밋·푸시하면 받는 쪽 항로에 뜹니다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
