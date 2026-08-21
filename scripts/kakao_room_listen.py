# -*- coding: utf-8 -*-
"""★중간관리자 방에서 「웰리야」 호출만 뽑아 배로 올린다 (GM 승인 2026-08-21 · 배 신설).

왜 이 모양인가
  카카오톡 PC 대화창은 글자가 아니라 그림으로 그려진다 — 창을 뜯어봐도 텍스트가 0이다
  (2026-08-21 실측: EVA_VH_ListControl 에 LB_GETCOUNT·LVM_GETITEMCOUNT·WM_GETTEXTLENGTH 전부 0).
  그래서 실시간 감지는 불가능하고, 카톡 자체 「대화 내용 저장」이 뽑아 준 txt 를 읽는 수밖에 없다.
  GM 선택(2026-08-21) = 1시간마다 · 대화 저장 방식.

토큰
  이 스크립트는 AI 를 부르지 않는다. 파일을 읽고 「웰리야」로 시작하는 줄만 골라 큐에 넣는다.
  호출이 0건이면 토큰 0. 실제 호출이 있을 때만 그 줄이 배 하나로 올라간다.

개인정보
  ★중간관리자 방 외의 방은 절대 건드리지 않는다(GM PC 에는 개인 대화방도 함께 열려 있다).
  뽑아낸 원본 txt 는 「웰리야」 줄만 남기고 그 자리에서 지운다 — 실무진 일상 대화는 보관하지 않는다.

사용
  python scripts/kakao_room_listen.py --file <내보낸.txt>   # 파일에서 읽기(현재 동작 경로)
  python scripts/kakao_room_listen.py --file <...> --dry-run  # 배 안 만들고 뽑히는 것만 보기
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "status" / "kakao_listen_state.json"
ROOM = "★중간관리자"
WAKE = "웰리야"

# 카톡 내보내기 한 줄 형식: [보낸사람] [오전 11:56] 내용
LINE = re.compile(r"^\[(?P<who>[^\]]+)\]\s*\[(?P<when>[^\]]+)\]\s*(?P<text>.*)$")


def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"seen": []}


def _save(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    st["seen"] = st.get("seen", [])[-500:]   # 지문만 보관 — 대화 원문은 남기지 않는다
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract(text: str) -> list[dict]:
    """내보낸 대화에서 「웰리야」 호출만 뽑는다. 나머지 줄은 버린다."""
    out, cur = [], None
    for raw in text.splitlines():
        m = LINE.match(raw.strip())
        if m:
            body = m.group("text").strip()
            if body.startswith(WAKE):
                cur = {"who": m.group("who").strip(), "when": m.group("when").strip(),
                       "text": body[len(WAKE):].lstrip(" ,·:-").strip()}
                out.append(cur)
            else:
                cur = None          # 다른 사람 말 — 이어붙이지 않는다
        elif cur is not None and raw.strip():
            cur["text"] = (cur["text"] + "\n" + raw.strip()).strip()   # 여러 줄 호출
    return [c for c in out if c["text"]]


def fingerprint(c: dict) -> str:
    return f"{c['who']}|{c['when']}|{c['text'][:40]}"


def to_ship(c: dict, dry: bool) -> bool:
    title = f"[웰리] ★중간관리자 방 호출 — {c['who']}: {c['text'][:60]}"
    note = (f"[카톡 호출 자동 접수] ★중간관리자 방 · {c['when']} · {c['who']}\n\n"
            f"{c['text']}\n\n"
            "▸이 방 발신은 웰리만 한다(약속 L24). 사실 안내는 바로 답하고, 판단·약속·숫자가 들어가면 "
            "GM 승인을 먼저 받는다(GM 확정 2026-08-21).")
    cmd = [sys.executable, str(ROOT / "scripts" / "queue_dispatch.py"),
           "--to", "ceo", "--sender", "cto", "--priority", "⛴️여객선",
           "--audience", "office", "--reversible", "yes", "--work-type", "update",
           "--title", title, "--note", note,
           "--next", "내용 확인 → 간단한 답은 바로 회신, 판단이 들어가면 GM 승인 후 회신"]
    if dry:
        cmd.append("--dry-run")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT))
    print((r.stdout or r.stderr or "").strip().splitlines()[0] if (r.stdout or r.stderr) else "")
    return r.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser(description=f"{ROOM} 방 「{WAKE}」 호출 접수")
    ap.add_argument("--file", required=True, help="카톡에서 내보낸 대화 txt")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    p = Path(a.file)
    if not p.exists():
        print(f"[FAIL] 파일 없음: {p}")
        return 2
    calls = extract(p.read_text(encoding="utf-8", errors="replace"))
    st = _state()
    seen = set(st.get("seen", []))
    fresh = [c for c in calls if fingerprint(c) not in seen]
    print(f"호출 {len(calls)}건 · 새 것 {len(fresh)}건")
    for c in fresh:
        if to_ship(c, a.dry_run) and not a.dry_run:
            seen.add(fingerprint(c))
    if not a.dry_run:
        st["seen"] = sorted(seen)
        _save(st)
    return 0


def demo() -> None:
    """자체 점검 — 「웰리야」 줄만 뽑고 남의 대화는 안 가져오는지."""
    sample = (
        "[이경연] [오전 9:10] 오늘 청소 시간 조정합니다\n"
        "[이정헌] [오전 9:12] 웰리야 정화조 공사 일정 언제였지?\n"
        "확인 부탁해\n"
        "[나우열] [오전 9:20] 네 확인했습니다\n"
        "[임정은] [오전 9:31] 웰리야, 회원 명단 링크 좀\n"
    )
    got = extract(sample)
    assert len(got) == 2, got
    assert got[0]["who"] == "이정헌" and "정화조" in got[0]["text"]
    assert "확인 부탁해" in got[0]["text"], "여러 줄 호출이 이어붙지 않았다"
    assert "네 확인했습니다" not in got[0]["text"], "남의 대화가 딸려 들어왔다"
    assert got[1]["who"] == "임정은" and got[1]["text"].startswith("회원 명단")
    assert extract("[A] [오전 1:00] 웰리야") == [], "본문 없는 호출은 버려야 한다"
    print("[OK] 자체 점검 통과 — 호출 2건만 추출, 남의 대화 미포함")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--selfcheck":
        demo()
    else:
        raise SystemExit(main())
