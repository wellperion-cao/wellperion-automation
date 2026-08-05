#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★운영부 아침 다이제스트 발송 — send_ops_digest.py (2026-07-14 CTO, 배906 · GM go 발효)

ops_daily_digest.py가 만든 _pending_digest.json 메시지를 카톡 ★운영부 방에 발송한다.
아침 파이프라인 마지막 단계(내보내기→다이제스트 생성→[이 단계]발송).

킬스위치(역롤백): status/ops_digest_send.json {"enabled": true/false}.
  enabled != true 이면 아무 것도 안 하고 로그만 남기고 exit 0(무인 발송 중단).
중복방지: _pending_digest.json 의 sent==false 이고 generated_at 이 '오늘'일 때만 발송.
  발송 성공 시 sent=true 로 마킹(같은 회차 재발송 방지). 생성 실패로 옛 다이제스트가
  남아있으면(generated_at 이 오늘 아님) 발송하지 않는다(어제분 재발송 사고 방지).

발송=kakao_report_sender.py --message --only-room '★ 운영부' 재사용(밤 점검공유와 동일 경로).
★개인정보: 다이제스트 원문은 gitignore된 아카이브에만. 이 스크립트·산출물 커밋 안 함.

[2026-08-05 추가] 같은 실행에서 '사람이 처리할 배 전달'도 한다(send_relays) —
AI가 실행하지 않는 시우·시로·시뽀의 배를 담당자 이름과 함께 해당 방에 넘긴다.
시우→★운영부(최준용M) · 시로·시뽀→★중간관리자(나우열M). 목록이 지난번과 같으면
보내지 않는다. 자세한 이유는 아래 '사람에게 넘기는 배 전달' 주석 블록 참조.

사용:
  python scripts/send_ops_digest.py            # 킬스위치 ON이면 발송
  python scripts/send_ops_digest.py --force    # 킬스위치·오늘조건 무시(수동 검증 발송)
  python scripts/send_ops_digest.py --dry-run  # 미발송(렌더·판정만)
  python scripts/send_ops_digest.py --relay-preview  # 배 전달 본문만 렌더(방에 손 안 댐)
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SENDER = ROOT / "scripts" / "kakao_report_sender.py"
PENDING = ROOT / "1. AI자료_아카이브" / "11_카카오톡" / "★운영부" / "_pending_digest.json"
KILL_SWITCH = ROOT / "status" / "ops_digest_send.json"
TARGET_ROOM = "★운영부"  # 2026-08-04 시토: SSOT(kakao_rooms.json)와 표기 일치(공백 제거) —
# 발송 자체는 _title_key 정규화로 공백 무관하게 동작하지만, 등록부 드리프트 체커가
# SSOT 표기와 다르면 CODE_ROOM_NOT_IN_SSOT로 매번 걸린다(발송 실패 아님 — 표기만 정합화).


ROOMS_CONFIG = ROOT / "scripts" / "kakao_rooms.json"

# ══════════════════════════════════════════════════════════════════════════
# 사람에게 넘기는 배 전달 (2026-08-05 GM 편제 확정)
#
# 왜 필요한가. AI 로 도는 C-Level 은 웰리·시토·시모·시포 넷뿐이고, 시우·시로·시뽀의
# 배는 추적용으로 큐에 살아 있되 AI 가 실행하지 않는다. 그런데 그 배들이 사람에게
# 닿는 경로가 없었다 — safe_commit.py 의 방 안내는 "AI 가 그 도메인 파일을 고치려다
# 막혔을 때"만 뜨는 일회성 문구이고, ★운영부 아침 다이제스트의 업무 블록은 업무현황
# SSOT 시트(action=todo_list)를 읽지 status/_queue.json 을 읽지 않는다. 그래서 시우
# 12건·시로 3건이 아무에게도 전달되지 않은 채 큐에만 쌓였다.
#
# 왜 여기(send_ops_digest.py)인가. ops_daily_digest.py 는 ★운영부 한 방의 '본문을
# 만드는' 곳이라 ★중간관리자에는 애초에 닿지 못한다. 실제 배달은 이 스크립트가 하고,
# 이미 유일한 카톡 관문(kakao_report_sender.py --only-room)을 부르고 있어 방 하나를
# 더 도는 데 새 발신기·새 스크립트가 필요 없다. 발송이 확정된 뒤에만 중복방지 지문을
# 적을 수 있는 것도 여기뿐이다(본문 생성 시점에 적으면 GM 이 보류한 회차가 '보냄'으로
# 남아 다음 회차가 막힌다).
#
# 누구에게 어느 방인가 = safe_commit.DOMAIN_MODIFY_RULES 가 이미 정본이라 그대로
# 읽어 쓴다(같은 값을 두 곳에 두지 않는다 — 약속 L01).
# ══════════════════════════════════════════════════════════════════════════
QUEUE_PATH = ROOT / "status" / "_queue.json"
RELAY_OPEN_STATUSES = {"PENDING", "IN_PROGRESS"}
RELAY_SHOW_N = 5            # 본문에 줄로 싣는 건수 — 나머지는 "외 N건"으로 접는다
RELAY_TITLE_CAP = 34        # 제목 길이 상한(카톡 한 줄)
RELAY_HEARTBEAT_ID = "clevel-queue-human-relay"  # 중복방지 지문 보관 = 상설 하트비트 1파일
# 실무진이 받는 글에는 누가 보내는지가 드러나야 한다(unassigned_nudge.AI_SIGNOFF 와 같은 형식).
# 전달 주체는 웰리 — GM 원문 "각기 담당자 이름 적어서 웰리가 전달".
RELAY_SIGNOFF = "웰페리온 AI 총괄 담당 웰리 드림"
# 무게 순서(🛳️크루즈 → ⛴️여객선 → ⛵돛단배). 모르는 값은 맨 뒤.
_RELAY_WEIGHT = {"🛳️크루즈": 0, "⛴️여객선": 1, "⛵돛단배": 2}
_ROLE_TAG_RE = re.compile(r"^\s*\[[^\]]*\]\s*")


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def _title_key(s: str) -> str:
    """방 이름 대조 — kakao_report_sender._title_key 와 같은 규칙(공백만 지운다)."""
    return "".join(str(s or "").split())


def _known_rooms() -> set:
    """kakao_rooms.json all_rooms 에 실재하는 방 이름 집합. 여기 없는 방으로는 안 보낸다
    (오타 한 글자로 엉뚱한 방을 열거나 매번 실패하는 일을 막는다 — 새 방 생성 금지)."""
    try:
        cfg = json.loads(ROOMS_CONFIG.read_text(encoding="utf-8"))
        return {_title_key(r.get("name", "")) for r in (cfg.get("all_rooms") or [])}
    except Exception as exc:
        log(f"[relay] 방 목록 읽기 실패 — 전달 생략: {exc}")
        return set()


def relay_routes() -> "list[tuple[str, dict]]":
    """[(방 이름, {clevel: 담당자})] — 방 배정 정본은 safe_commit.DOMAIN_MODIFY_RULES 하나."""
    from safe_commit import DOMAIN_MODIFY_RULES  # 함수 안에서 import — 실패해도 다이제스트는 산다

    routes: dict = {}
    for role_label, contact, _paths, room, _note in DOMAIN_MODIFY_RULES:
        clevel = role_label.split("(")[0].strip().lower()  # "COO(시우)" → "coo"
        routes.setdefault(room, {})[clevel] = contact
    return list(routes.items())


def _short_title(title: str) -> str:
    """카톡 한 줄용 제목 — 역할 머리표([시우])만 떼고 길이로 자른다.

    ' — ' 앞만 남기는 방식도 써 봤으나 "전사 일정 SSOT"처럼 정작 부탁 내용이 대시
    뒤에 있는 배가 많아 뜻이 사라졌다. 길이로 자르고 …를 붙인다(종합접수 블록과 동일)."""
    t = _ROLE_TAG_RE.sub("", str(title or "")).strip()
    t = re.sub(r"\s+", " ", t)
    if len(t) <= RELAY_TITLE_CAP:
        return t
    # ★낱말 한가운데서 자르지 않는다(GM 상시 지시 — 어색한 중간 잘림 금지).
    #   상한 안에서 마지막 띄어쓰기까지만 남긴다. 띄어쓰기가 아예 없으면(붙여 쓴 긴 제목)
    #   어쩔 수 없이 길이로 자른다 — 그때는 잘린 티가 나는 게 뜻이 끊기는 것보다 낫다.
    head = t[:RELAY_TITLE_CAP]
    cut = head.rfind(" ")
    if cut >= RELAY_TITLE_CAP // 2:
        head = head[:cut]
    return head.rstrip(" ·—-(→,") + "…"


def build_relay_message(contacts: dict) -> str:
    """열려 있는(PENDING·IN_PROGRESS) 배를 한 배 한 줄로. 없으면 빈 문자열.

    한 줄 = 짧은 제목(+담당자가 여럿인 방이면 이름). 배 번호·상태값·task_id 같은 내부
    코드는 싣지 않는다 — 실무진이 그 번호를 찾아볼 곳이 없다.

    ★audience 가 'office' 인 배만 싣는다(GM 2026-08-05 "원래 하던 일인데, 배편에 있는
    내용인거야?"). 큐에는 AI 내부 살림(audience='ai')도 섞여 있는데, 그걸 사람 방에
    보내면 AI 를 돌보는 일이 실무진 업무로 둔갑한다 — GM 이 반복해 경계하신 구조다.
    실측: 시로 배 3척 중 1척(상시 자율 체계 운영)이 정확히 그 부류였다."""
    try:
        queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        log(f"[relay] 큐 읽기 실패 — 전달 생략: {exc}")
        return ""

    ships = [x for x in queue if isinstance(x, dict)
             and x.get("clevel") in contacts
             and str(x.get("status", "")) in RELAY_OPEN_STATUSES
             and str(x.get("audience", "")) == "office"]   # ★AI 내부 살림(audience="ai")은 사람 방에 보내지 않는다
    if not ships:
        return ""
    ships.sort(key=lambda x: (_RELAY_WEIGHT.get(x.get("priority"), 9),
                              str(x.get("enqueued_at", ""))))

    # 담당자가 한 사람뿐이면 이름을 머리줄에 한 번만 적는다 — 줄마다 같은 이름이 반복되면
    # 정작 읽어야 할 제목이 묻힌다(카톡은 짧고 핵심만 · GM 2026-08-05).
    # 배 번호도 싣지 않는다 — 실무진이 그 번호를 찾아볼 곳이 없다(내부 코드 노출 금지).
    who = {contacts[s["clevel"]] for s in ships}
    solo = who.pop() if len(who) == 1 else None
    lines = [f"🧾 사람이 처리할 업무 {len(ships)}건" + (f" — {solo}" if solo else "")]
    for s in ships[:RELAY_SHOW_N]:
        tail = "" if solo else f" · {contacts[s['clevel']]}"
        lines.append(f" • {_short_title(s.get('title'))}{tail}")
    if len(ships) > RELAY_SHOW_N:
        lines.append(f" • 외 {len(ships) - RELAY_SHOW_N}건")
    lines.append(RELAY_SIGNOFF)
    return "\n".join(lines)


def _relay_sigs() -> dict:
    from module_heartbeat import last_heartbeat
    rec = last_heartbeat(RELAY_HEARTBEAT_ID) or {}
    sigs = rec.get("sigs")
    return dict(sigs) if isinstance(sigs, dict) else {}


def _save_relay_sigs(sigs: dict) -> None:
    from module_heartbeat import record_heartbeat
    record_heartbeat(RELAY_HEARTBEAT_ID,
                     detail=f"사람 처리 배 전달 — 방 {len(sigs)}곳 지문 갱신",
                     extra={"sigs": sigs})


def send_relays(dry_run: bool = False) -> None:
    """방마다 '사람이 처리할 배' 1통. 내용이 지난번과 같으면 보내지 않는다.

    같은 목록을 매일 다시 보내면 실무진이 읽기를 멈춘다 — 배가 늘거나 줄거나 끝났을
    때만 다시 뜬다. 목록이 빈 방은 지문을 빈 값으로 적어 두어, 나중에 같은 목록이
    다시 생기면 그때는 정상적으로 발신된다. 발신 실패 시 지문을 안 적으므로 다음
    회차에 자동 재시도된다. 전달 실패가 다이제스트 발송을 막지 않는다(fail-soft)."""
    try:
        routes = relay_routes()
    except Exception as exc:
        log(f"[relay] 전달 대상 규칙 로드 실패 — 전달 생략(다이제스트는 계속): {exc}")
        return

    known = _known_rooms()
    sigs = _relay_sigs()
    changed = False
    for room, contacts in routes:
        if _title_key(room) not in known:
            log(f"[relay] '{room}' 는 kakao_rooms.json 에 없는 방 — 건너뜀")
            continue
        message = build_relay_message(contacts)
        sig = hashlib.sha1(message.encode("utf-8")).hexdigest()[:12]
        if sigs.get(room) == sig:
            log(f"[relay] {room} — 지난번과 같은 목록, 발신 생략")
            continue
        if not message:
            log(f"[relay] {room} — 넘길 배 없음(지문만 갱신)")
            sigs[room], changed = sig, True
            continue

        cmd = [sys.executable, str(SENDER), "--message", message, "--only-room", room]
        if dry_run:
            cmd.append("--dry-run")
        log(f"[relay] {room} 전달 발송({message.count(chr(10)) + 1}줄)")
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        out = (proc.stdout or "").strip()
        if proc.returncode == 0 and "DONE" in out:
            if not dry_run:
                sigs[room], changed = sig, True
            log(f"[relay] {room} 전달 완료")
        else:
            tail = out.splitlines()[-1] if out else "출력 없음"
            log(f"[relay] {room} 전달 실패(rc={proc.returncode}) — {tail} · 다음 회차 재시도")
    if changed:
        _save_relay_sigs(sigs)


def preview_relays() -> int:
    """방에 손대지 않고 본문만 렌더해 보여준다(실방 검증용 — 발신·지문기록 없음)."""
    for room, contacts in relay_routes():
        message = build_relay_message(contacts)
        print(f"\n===== {room} ({'내용 없음' if not message else '발신 대상'}) =====")
        print(message or "(넘길 배 없음 — 발신 안 함)")
        if message:
            body = message.splitlines()
            assert body[-1] == RELAY_SIGNOFF, "AI 주체 서명 누락"
            assert len(body) <= RELAY_SHOW_N + 3, f"카톡 한 통이 너무 길다: {len(body)}줄"
            assert "PENDING" not in message and "task_id" not in message, "내부 상태값 노출"
    return 0


def kill_switch_enabled() -> bool:
    try:
        return bool(json.loads(KILL_SWITCH.read_text(encoding="utf-8")).get("enabled", False))
    except Exception:
        return False


def main() -> int:
    if sys.platform != "win32":
        print("FAILED: Windows 전용")
        return 1
    ap = argparse.ArgumentParser(description="★운영부 아침 다이제스트 발송")
    ap.add_argument("--force", action="store_true", help="킬스위치·오늘조건 무시(수동 검증)")
    ap.add_argument("--dry-run", action="store_true", help="미발송")
    ap.add_argument("--relay-preview", action="store_true",
                    help="사람 처리 배 전달 본문만 렌더(방에 손 안 댐 · 발신·지문기록 없음)")
    args = ap.parse_args()

    if args.relay_preview:
        return preview_relays()

    if not args.force and not kill_switch_enabled():
        log(f"킬스위치 OFF({KILL_SWITCH}) — 발송 생략")
        print("SKIPPED: 킬스위치 비활성")
        return 0

    # 사람이 처리할 배 전달은 다이제스트보다 먼저·독립으로 돈다 — 어제 카톡 대화가
    # 없어(휴관 등) 다이제스트가 안 만들어진 날에도 이 전달은 나가야 한다.
    send_relays(dry_run=args.dry_run)

    if not PENDING.exists():
        print(f"FAILED: 대기 다이제스트 없음 — {PENDING}")
        return 1
    data = json.loads(PENDING.read_text(encoding="utf-8"))
    message = (data.get("message") or "").strip()
    if not message:
        print("FAILED: 다이제스트 메시지가 비어 있음")
        return 1

    today = datetime.now().strftime("%Y-%m-%d")
    gen_today = str(data.get("generated_at", "")).startswith(today)
    already = bool(data.get("sent"))
    if not args.force:
        if already:
            log("이미 발송된 회차(sent=true) — 중복 발송 생략")
            print("SKIPPED: 이미 발송됨")
            return 0
        if not gen_today:
            log(f"대기 다이제스트가 오늘 생성분이 아님(generated_at={data.get('generated_at')}) — 옛 회차 재발송 방지, 생략")
            print("SKIPPED: 오늘 생성분 아님")
            return 0

    cmd = [sys.executable, str(SENDER), "--message", message, "--only-room", TARGET_ROOM]
    if args.dry_run:
        cmd.append("--dry-run")
    log(f"[send] 다이제스트 발송(대상 {data.get('date')}) → {TARGET_ROOM}")
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    out = (proc.stdout or "").strip()
    tail = out.splitlines()[-1] if out else "출력 없음"
    log(f"[send] 결과 rc={proc.returncode} · {tail}")
    if proc.returncode == 0 and "DONE" in out:
        if not args.dry_run:
            data["sent"] = True
            data["sent_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            PENDING.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"DONE: 다이제스트 발송 완료 — {TARGET_ROOM}")
        return 0
    print(f"FAILED: 발송 실패(rc={proc.returncode}) — {tail}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
