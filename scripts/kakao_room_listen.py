# -*- coding: utf-8 -*-
"""★중간관리자 방에서 「웰리」 호출만 뽑아 웰리 배로 올린다 (GM 승인 2026-08-21 · 배733).

왜 이 모양인가
  카카오톡 PC 대화창은 글자가 아니라 그림으로 그려진다 — 창을 뜯어봐도 텍스트가 0이다
  (2026-08-21 실측: EVA_VH_ListControl 에 LB_GETCOUNT·LVM_GETITEMCOUNT·WM_GETTEXTLENGTH 전부 0).
  그래서 실시간 감지는 불가능하고, 카톡 자체 「대화 내용 저장」이 뽑아 준 txt 를 읽는 수밖에 없다.
  GM 선택(2026-08-21) = 1시간마다 · 대화 저장 방식.

토큰
  이 스크립트는 AI 를 부르지 않는다. 파일을 읽고 「웰리」로 시작하는 줄만 골라 큐에 넣는다.
  호출이 0건이면 토큰 0. 실제 호출이 있을 때만 그 줄이 배 하나로 올라간다.

개인정보
  ★중간관리자 방 외의 방은 절대 건드리지 않는다(GM PC 에는 개인 대화방도 함께 열려 있다).
  뽑아낸 원본 txt 는 gitignore 된 아카이브에만 있고 저장소에 커밋되지 않는다(kakao_export_chat 규칙 그대로).
  이 스크립트가 큐에 남기는 것은 「웰리」 호출 줄뿐 — 실무진 일상 대화는 배에 들어가지 않는다.

내보내기 정본
  scripts/kakao_export_chat.py (배906 · 2026-07-14 시토). ★중간관리자 방은 이미 매일 자동으로
  뽑히고 있었다 — 새 내보내기 도구를 만들지 않고 그 도구를 부른다(약속 L21).

사용
  python scripts/kakao_room_listen.py --export             # 지금 뽑고 읽는다(예약이 쓰는 길)
  python scripts/kakao_room_listen.py                      # 아카이브 최신본에서 읽기
  python scripts/kakao_room_listen.py --dry-run            # 배 안 만들고 뽑히는 것만 보기
  python scripts/kakao_room_listen.py --selfcheck          # 자체 점검
  python scripts/kakao_room_listen.py --external --probe   # 로컬DB mtime 판정만(내보내기 안 함)
언제 도나 (2026-08-25 GM 변경)
  아침 07:30 운영부 다이제스트(scripts/ops_morning_digest.bat)가 하루 한 번 부른다.
  ▸전에는 매시 08~20시 전용 예약작업(Wellperion-Kakao-Room-Listen-Hourly)이 돌았다. 실측 결과
    하루 13번 돌아 4일에 새 호출 2건이었고, 매 회차마다 카카오톡 창을 앞으로 띄워 GM 화면을
    가렸다. GM: "오전에만 하고, 어제 중간관리자 정리하는 것처럼만 진행하면 안될까?"
  ▸다이제스트가 바로 앞 줄에서 이미 같은 방을 내보내므로 여기선 --export 를 쓰지 않는다
    (창을 다시 띄우지 않는다). 하루 걸러도 놓치지 않게 --since-days 2 로 부른다.
  ▸되돌리려면 status/_removed_tasks/ 에 보관한 예약작업 정의를 다시 등록한다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "status" / "kakao_listen_state.json"
ROOM = "★중간관리자"
WAKE = "웰리"          # GM 확정 2026-08-21 — "웰리야"가 아니라 "웰리"로 부른다
# 부른 뒤 따라오는 호칭·구두점은 본문이 아니다: "웰리야 ~" · "웰리님, ~" · "웰리 - ~"
_AFTER_WAKE = " ,·:-야님씨!?~"

# ── 밖과 트는 방(external_rooms) 1시간 감지 (GM 결정 2026-09-08 20:2x · 시토 배1137) ──
# GM 계정으로 카톡을 쓰므로 GM 이 직접 치든 AI 가 대신 보내든 우리 쪽 발신은 전부
# 이 이름으로 내보내기 파일에 찍힌다(실측: 다이어트캠프·조재오부장님 방 모두 "[김남욱]").
# 그 이름만 빼면 남는 줄이 전부 상대 발언이다 — 방마다 상대 이름을 따로 등록할 필요가 없다.
GM_SELF = "김남욱"

# 카톡 내보내기 한 줄 형식: [보낸사람] [오전 11:56] 내용
LINE = re.compile(r"^\[(?P<who>[^\]]+)\]\s*\[(?P<when>[^\]]+)\]\s*(?P<text>.*)$")
# 날짜 구분선: --------------- 2026년 5월 26일 화요일 ---------------
DAY = re.compile(r"^-{3,}\s*(?P<y>\d{4})년\s*(?P<m>\d{1,2})월\s*(?P<d>\d{1,2})일.*-{3,}$")


def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"seen": []}


def _save(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    st["seen"] = st.get("seen", [])[-500:]   # 지문만 보관 — 대화 원문은 남기지 않는다
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _commit_state() -> None:
    """지문 상태를 커밋해 둔다(배1140 · 시토). 이 파일이 미커밋으로만 쌓이면 공유 작업트리에서
    누군가의 git 되돌림(reset/checkout 류)이 그때그때 최신 커밋으로 되감아 지문이 사라진다 —
    2026-08-24 커밋 이후 실측: 그 뒤 로그상 새 호출 19건 이상이 잡혔는데 지문은 5건에 묶여 있었다
    (2026-09-08 07:30 에 정상 잡힌 지문이 09-09 07:30 재발화 전 사라짐 — 배1139 원인).
    safe_commit 은 락 직렬화·HEAD 재검증을 이미 하므로(cpo_inquiry_snapshot.py 관례 재사용,
    약속 L21) 여기서 새 커밋 로직을 만들지 않는다. 실패해도 접수 자체는 이미 끝났다 — 무해."""
    try:
        rel = str(STATE.relative_to(ROOT)).replace("\\", "/")
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "safe_commit.py"),
             "-m", "chore(cto): 카톡 호출 접수 지문 갱신 (kakao_listen_state)", "--", rel],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=120)
        if r.returncode != 0:
            print(f"[warn] 지문 커밋 실패(무해 — 다음 회차 재시도): rc={r.returncode}")
    except Exception as e:
        print(f"[warn] 지문 커밋 실패(무해): {type(e).__name__}: {e}")


REPLY_LOOKAHEAD_DAYS = 2  # ops_room_issue_extract.py RESOLVE_LOOKAHEAD_DAYS 관례 재사용(약속 L21)
# 완료·확인 신호 키워드 — ops_room_issue_extract.py _RESOLVED_RE 와 같은 관례(약속 L21 재사용).
_REPLIED_RE = re.compile(
    r"(확인했습니다|확인했어요|확인함|처리했습니다|처리했어요|해결|완료|끝났습니다|"
    r"됐습니다|됐어요|드렸습니다|전달했습니다|전달했어요|답변|회신)"
)
_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]{2,}")
# 흔한 업무어 — 어느 대화에나 등장해 겹치는 척만 한다. 이걸 빼야 "우연히 완료 신호가 낀 다른
# 화제"를 답신으로 오판하지 않는다(실측 2026-09-09: 이 목록 없이는 호출 29건 중 18건이 오탐).
_GENERIC_TOKENS = {"업무", "확인", "완료", "처리", "오늘", "내일", "어제", "회신", "답변", "그거", "이거"}


def _shares_topic(call_text: str, reply_text: str) -> bool:
    """호출과 답신이 같은 화제인지 — 완료 신호만으로는 GM 이 그 시간대에 한 다른 말과
    구별이 안 된다(배1140). 서로 겹치는 구체 낱말(흔한 업무어 제외)이 있어야 같은 화제로 본다."""
    call_toks = _TOKEN_RE.findall(call_text)
    reply_toks = set(_TOKEN_RE.findall(reply_text)) - _GENERIC_TOKENS
    return any(t in reply_toks for t in call_toks if t not in _GENERIC_TOKENS)


def _day_ord(day: str) -> int:
    y, m, d = (int(x) for x in day.split("-"))
    return datetime(y, m, d).toordinal()


def extract(text: str) -> list[dict]:
    """내보낸 대화에서 「웰리」 호출만 뽑는다. 나머지 줄은 버린다.
    각 호출에 replied(호출 뒤 REPLY_LOOKAHEAD_DAYS 일 내 김남욱 발신 확인·완료 신호 유무)를 매긴다 —
    GM 본인이든 AI 대행이든 이 계정 이름으로 나가므로(kakao_room_listen_external.py GM_SELF 와
    동일 근거), 큐를 거치지 않고 방에서 이미 답한 건은 지문이 사라져도 다시 배로 뜨지 않는다(배1140)."""
    lines: list[dict] = []      # 판정용 — 방 안 전체 발신 줄(누구든), 호출 뒤 답신 탐색에만 쓴다
    out, cur, day = [], None, ""
    for raw in text.splitlines():
        d = DAY.match(raw.strip())
        if d:
            day = f"{d.group('y')}-{int(d.group('m')):02d}-{int(d.group('d')):02d}"
            cur = None            # 날짜가 바뀌면 앞 호출은 거기서 끝난다(구분선이 본문에 붙지 않게)
            continue
        m = LINE.match(raw.strip())
        if m:
            who = m.group("who").strip()
            body = m.group("text").strip()
            lines.append({"who": who, "day": day, "text": body})
            if body.startswith(WAKE):
                cur = {"who": who, "day": day, "when": m.group("when").strip(),
                       "text": body[len(WAKE):].lstrip(_AFTER_WAKE).strip(),
                       "_line_idx": len(lines) - 1}
                out.append(cur)
            else:
                cur = None          # 다른 사람 말 — 이어붙이지 않는다
        elif cur is not None and raw.strip():
            cur["text"] = (cur["text"] + "\n" + raw.strip()).strip()   # 여러 줄 호출

    for c in out:
        idx = c.pop("_line_idx")
        replied = False
        # GM 본인이 부른 호출은 이 판정 대상이 아니다 — "이미 GM 이 방에서 직접 답했다"는
        # 실무진이 부르고 GM 이 답한 경우만 뜻한다(배1140 실사고 그대로). GM 자신의 호출 뒤에
        # 나오는 그의 다른 발신까지 "답신"으로 잡으면 자기 자신에게 오탐만 늘어난다.
        if c["day"] and c["who"] != GM_SELF:
            call_ord = _day_ord(c["day"])
            for later in lines[idx + 1:]:
                if not later.get("day"):
                    continue
                if _day_ord(later["day"]) - call_ord > REPLY_LOOKAHEAD_DAYS:
                    break
                later_text = later.get("text", "")
                if (later["who"] == GM_SELF and _REPLIED_RE.search(later_text)
                        and _shares_topic(c["text"], later_text)):
                    replied = True
                    break
        c["replied"] = replied
    return [c for c in out if c["text"]]


def fingerprint(c: dict) -> str:
    return f"{c.get('day','')}|{c['who']}|{c['when']}|{c['text'][:40]}"


_AMPM = re.compile(r"(오전|오후)\s*(\d{1,2}):(\d{2})")


def call_key(c: dict) -> str:
    """day+when → "YYYY-MM-DD HH:MM"(24시간) 정렬 키. 카톡 내보내기는 분 단위까지만 준다 —
    같은 분에 여러 줄이 와도 이 키로는 못 가른다(그건 fingerprint 의 몫)."""
    m = _AMPM.match((c.get("when") or "").strip())
    if not m:
        return f"{c.get('day','')} 00:00"
    ap, h, mi = m.group(1), int(m.group(2)), m.group(3)
    h = (0 if h == 12 else h) if ap == "오전" else (12 if h == 12 else h + 12)
    return f"{c.get('day','')} {h:02d}:{mi}"


def extract_external(text: str) -> list[dict]:
    """상대(GM_SELF 제외)가 쓴 줄만 뽑는다. extract()와 뼈대는 같고 조건만 다르다
    ("웰리" 호출 대신 "우리 쪽 아님") — 두 조건을 하나로 합치면 오히려 읽기 어려워져 그대로 둔다."""
    out, cur, day = [], None, ""
    for raw in text.splitlines():
        d = DAY.match(raw.strip())
        if d:
            day = f"{d.group('y')}-{int(d.group('m')):02d}-{int(d.group('d')):02d}"
            cur = None
            continue
        m = LINE.match(raw.strip())
        if m:
            who = m.group("who").strip()
            body = m.group("text").strip()
            if who != GM_SELF:
                cur = {"who": who, "day": day, "when": m.group("when").strip(), "text": body}
                out.append(cur)
            else:
                cur = None          # 우리 쪽 발신(GM 본인·AI 대신 발신 모두 이 계정으로 나간다)
        elif cur is not None and raw.strip():
            cur["text"] = (cur["text"] + "\n" + raw.strip()).strip()   # 여러 줄 발언
    return [c for c in out if c["text"]]


def to_ship(c: dict, dry: bool) -> bool:
    title = f"[웰리] ★중간관리자 방 호출 — {c['who']}: {c['text'][:60]}"
    note = (f"[카톡 호출 자동 접수] ★중간관리자 방 · {c.get('day','')} {c['when']} · {c['who']}\n\n"
            f"{c['text']}\n\n"
            "▸이 방에 글을 쓰는 쪽 = 중간관리자(실무진) · 웰리 · GM 셋뿐이다(GM 확정 2026-08-21).\n"
            "  AI 중에서는 웰리만 쓴다 — 다른 역할은 웰리에게 배로 넘긴다(약속 L24).\n"
            "▸사실 안내는 바로 답하고, 판단·약속·숫자가 들어가면 GM 승인을 먼저 받는다(GM 확정 2026-08-21).")
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


ARCHIVE = ROOT / "1. AI자료_아카이브" / "11_카카오톡" / ROOM


def _latest_export() -> Path | None:
    files = sorted(ARCHIVE.glob("*/★중간관리자_auto_*.txt"))
    return files[-1] if files else None


def _export_now() -> Path | None:
    """카톡 대화를 지금 다시 뽑는다. 정본 = scripts/kakao_export_chat.py (배906 · 이미 매일 도는 도구).
    새 내보내기 도구를 만들지 않는다(약속 L21)."""
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "kakao_export_chat.py"),
                        "--room-key", "mgr"],
                       capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT), timeout=300)
    tail = (r.stdout or r.stderr or "").strip().splitlines()
    print(tail[-1] if tail else "(내보내기 출력 없음)")
    return _latest_export()


def _load_external_rooms() -> list[dict]:
    try:
        data = json.loads((ROOT / "scripts" / "kakao_rooms.json").read_text(encoding="utf-8"))
    except Exception:
        return []
    return data.get("external_rooms") or []


def _latest_export_for(room_name: str) -> Path | None:
    """방 이름 → 아카이브 폴더명 매핑은 kakao_export_chat.ROOM_DIR_NAME 하나만 쓴다(약속 L21 —
    새 매핑표를 여기 복제하지 않는다)."""
    import kakao_export_chat as _kec
    folder = _kec.ROOM_DIR_NAME.get(room_name, room_name.replace(" ", ""))
    files = sorted((ROOT / "1. AI자료_아카이브" / "11_카카오톡" / folder).glob(f"*/{folder}_auto_*.txt"))
    return files[-1] if files else None


def _export_now_external(room_name: str) -> Path | None:
    """지금 그 방을 다시 뽑는다. 정본 도구 그대로 호출(약속 L21) — room_name 은 파이썬 subprocess
    리스트 인자로 넘어가 .bat 의 CP949 한글 깨짐을 겪지 않는다(kakao_rooms.json room_aliases 필요 없음)."""
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "kakao_export_chat.py"),
                        "--room", room_name],
                       capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT), timeout=300)
    tail = (r.stdout or r.stderr or "").strip().splitlines()
    print(tail[-1] if tail else "(내보내기 출력 없음)")
    return _latest_export_for(room_name)


OPEN = ("PENDING", "IN_PROGRESS")


def _append_to_ship(role: str, room_name: str, ship_no, fresh: list[dict]) -> str | None:
    """이 방 전용 배(kakao_rooms.json external_rooms.ship_no)에 note 한 줄씩 append.
    붙이는 배는 그 고정 매핑 하나뿐이다 — 역할 추론 폴백은 쓰지 않는다(2026-09-08 시보 확인).
    전용 배가 없거나 닫혀 있으면 여기서 아무 데도 붙이지 않고 None 을 돌려주며,
    호출부가 그 방 전용 배를 새로 띄운다(_new_ship_for_external).
    큐 쓰기는 queue_lock.mutate_queue 한 관문으로만(약속 — 직접 열어 쓰지 않는다).
    돌려주는 값 = 붙인 배의 표시 번호(short_no 우선) — 없으면 None(붙일 배가 없었다는 뜻)."""
    from queue_lock import mutate_queue

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"- [시토 {now} · 카톡 자동감지 · {room_name}] {c['who']}: {c['text'].replace(chr(10), ' ')[:60]}"
             for c in fresh]
    hit: dict = {}

    def mutator(queue):
        target = None
        pinned = next((it for it in queue if isinstance(it, dict) and it.get("ship_no") == ship_no), None) \
            if ship_no is not None else None
        block = "\n".join(lines)
        # ★방 → 배는 고정 매핑만 쓴다(external_rooms.ship_no). 시보 확인 2026-09-08.
        #   "그 역할의 가장 최근 배" 추론으로 폴백하면 방마다 내용이 섞여 담당이 못 읽는다 —
        #   09-08 초판이 그렇게 해서 조재오·다캠 대화 6줄이 무관한 AX 허브 배에 붙었다.
        #   전용 배가 없거나 닫혀 있으면 여기서 붙이지 않고, 호출부가 그 방 전용 배를 새로 띄운다.
        if pinned is None or pinned.get("status") not in OPEN:
            hit["need_new_ship"] = True
            hit["closed_reason"] = (f"전용 배 {ship_no} 닫힘(status={pinned.get('status')})"
                                    if pinned is not None else "전용 배 미지정")
            return queue
        target = pinned
        prev = str(target.get("note") or "")
        target["note"] = (prev + ("\n" if prev else "") + block).strip()
        hit["disp"] = target.get("short_no") if target.get("short_no") is not None else target.get("ship_no")
        return queue

    mutate_queue(mutator, holder="kakao_room_listen_external")
    return hit.get("disp")


def _new_ship_for_external(role: str, room_name: str, fresh: list[dict]) -> None:
    """전용 배(external_rooms.ship_no)가 없거나 닫혔을 때 — 그 방 전용 배 1척을 새로 띄운다.
    제목에 방 이름이 들어가므로 방마다 다른 배가 서고, 담당이 kakao_rooms.json 의 ship_no 를
    그 번호로 바꿔 주면 다음 회차부터 고정 매핑으로 돌아온다(역할 추론 폴백은 쓰지 않는다)."""
    now = datetime.now().strftime("%Y-%m-%d")
    lines = [f"- [{now} · 카톡 자동감지] {c['who']}: {c['text'].replace(chr(10), ' ')[:60]}" for c in fresh]
    cmd = [sys.executable, str(ROOT / "scripts" / "queue_dispatch.py"),
           "--to", role, "--sender", "cto", "--priority", "⛴️여객선",
           "--audience", "office", "--reversible", "yes", "--work-type", "update",
           "--title", f"[카톡 감지] {room_name} 새 대화",
           "--note", "\n".join(lines),
           "--next", "카톡 내용 확인 후 회신 판단",
           # 담당은 kakao_rooms.json external_rooms.owner_role 이 이미 정한 값이다 —
           # ownership_map 낱말 스캔과 어긋나도(예: '카톡'=시토 낱말) 그대로 보낸다.
           "--force-route"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT))
    print((r.stdout or r.stderr or "").strip().splitlines()[0] if (r.stdout or r.stderr) else "")


def _ping_external(room_name: str, role: str, fresh: list[dict], disp) -> None:
    import queue_dispatch as _qd
    nick = _qd.ROLES.get(role, role)
    who = " · ".join(dict.fromkeys(c["who"] for c in fresh))
    first = fresh[0]["text"].replace("\n", " ")[:40]
    where = f"{nick} 배 {disp}" if disp is not None else f"{nick} 새 배"
    msg = (f"{room_name} 방에서 상대({who}) 새 톡 {len(fresh)}건 감지 — {where}에 올렸습니다\n"
           f"   첫 건: {first}…")
    try:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "notify_gm_progress.py"),
                        msg, "--ship", "시토 1137", "--state", "done"],
                       capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT), timeout=60)
    except Exception as e:
        print(f"[WARN] 알림 실패(배는 정상 등록됨): {type(e).__name__}: {e}")


def _kakao_activity_snapshot() -> dict[str, float] | None:
    """방마다 로컬 대화DB 파일(chatLogs_<id>.edb[-wal])의 수정시각 스냅샷(배1149 실측).
    카톡 PC는 새 메시지가 오면 그 방의 -wal(없으면 .edb 자체) mtime을 갱신한다 — 내용은
    암호화라 못 읽지만 "뭔가 왔다/안 왔다"는 시각만으로 가른다(포커스·클릭 0회).
    -shm은 뺀다 — 세션이 열릴 때마다 전 방이 동시에 갱신돼(실측: 전부 같은 시각) 신호가 아니라
    노이즈다. 폴더가 없거나 읽기 실패하면 None — 호출부가 fail-open(저장 진행)한다."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    users_dir = Path(local) / "Kakao" / "KakaoTalk" / "users"
    if not users_dir.exists():
        return None
    snap: dict[str, float] = {}
    try:
        for chat_data in users_dir.glob("*/chat_data"):
            for f in chat_data.glob("chatLogs_*.edb*"):
                if f.name.endswith("-shm"):
                    continue
                base_id = f.name.split(".edb")[0]
                mtime = f.stat().st_mtime
                if mtime > snap.get(base_id, 0.0):
                    snap[base_id] = mtime
    except OSError:
        return None
    return snap


def _kakao_local_changed(baseline: dict[str, float] | None, snap: dict[str, float]) -> list[str]:
    """직전 스냅샷 대비 mtime이 늘어난(또는 새로 생긴) 파일id 목록. baseline이 없으면(첫 실행)
    전부를 '바뀐 것'으로 본다 — 기준선이 없을 때 무조건 건너뛰면 첫 실행에 진짜 새 메시지를
    놓칠 수 있다(안전 쪽으로 기운다)."""
    if baseline is None:
        return sorted(snap.keys())
    return [k for k, v in snap.items() if v > baseline.get(k, 0.0)]


def run_external(dry: bool, probe: bool = False) -> int:
    """방마다 last_processed_at(마지막으로 처리한 상대 발언 시각) 뒤에 온 줄만 배에 올린다.
    GM 지적 2026-09-08 — since-days(날짜 단위) 컷오프로는 "어제 이미 시보가 회신까지 마친 대화"도
    다시 새 걸로 본다. 시분 단위 커서(call_key)로 바꿔 이미 처리한 순간 이후만 본다.
    최초 가동(그 방에 last_processed_at 이 아예 없을 때)은 지금 시각을 기준선으로만 잡고
    아무것도 올리지 않는다 — 안 그러면 방이 열린 날부터 전부가 '새 것'이 된다(2026-09-08 실사고).

    GM 지적 2026-09-09(배1149) — 매시 카톡 창을 앞으로 띄워 GM 화면을 8~14분/일 가렸다.
    실측 결과 그 회차는 거의 항상 헛돌았다(대상 방에 새 메시지가 없었다). 방↔로컬DB파일id
    매핑은 암호화 때문에 지금은 못 만든다 — 대신 "저장이 필요한가"만 거른다: 로컬 대화DB
    파일(어느 방이든) mtime이 하나도 안 바뀌었으면 그 시간 동안 카톡에 아무 메시지도 안 왔다는
    뜻이므로 내보내기 자체를 통째로 건너뛴다(포커스 0회). 하나라도 바뀌면 — 그게 대상 방이
    아닐 수도 있지만 — 지금까지 하던 대로 진행한다(그래도 지금보다 나쁘지 않다, fail-open).
    변화가 있었던 회차는 그 파일id들을 상태 파일에 몇 건만 쌓아 둔다 — 며칠 지나면 어느 id가
    어느 방인지 저절로 드러나고, 그때 가서 매핑을 좁히면 된다(지금은 만들려 하지 않는다)."""
    rooms = _load_external_rooms()
    if not rooms:
        print("[external] kakao_rooms.json 에 external_rooms 없음 — 할 일 없음")
        return 0
    t0 = time.monotonic()
    now_key = datetime.now().strftime("%Y-%m-%d %H:%M")
    st = _state()
    activity = st.setdefault("external_activity", {})
    snap = _kakao_activity_snapshot()
    if snap is None:
        changed_ids: list[str] | None = None
        print("[external] 로컬 대화DB mtime 확인 실패 — 저장 진행(fail-open)")
    else:
        changed_ids = _kakao_local_changed(activity.get("mtimes"), snap)
        skip = not changed_ids
        if skip or probe:
            # skip이면 "찍어 보니 조용했다"를 기준선으로 남긴다. probe면 실제 내보내기는
            # 안 하지만 판정에 쓴 스냅샷은 남겨야 다음 --probe 로 skip 경로를 재현해 볼 수 있다.
            activity["mtimes"] = snap
            if not dry:
                _save(st)
                _commit_state()
        if skip:
            elapsed = time.monotonic() - t0
            print(f"[external] 새 메시지 없음 — 저장 건너뜀(포커스 0회) · {elapsed:.1f}초")
            return 0
        print(f"[external] 로컬 대화DB 변화 {len(changed_ids)}건 감지 — 저장 진행")
    if probe:
        elapsed = time.monotonic() - t0
        print(f"[external] (probe) 저장 경로로 진입함 · {elapsed:.1f}초 · 실제 내보내기는 안 함")
        return 0
    ext = st.setdefault("external", {})
    any_new = False
    rooms_with_new: list[str] = []
    MAX_LINES = 20  # 안전판(2026-09-08) — 커서가 있어도 혹시 몰아온 하루엔 이 이상 안 싣는다
    for r in rooms:
        name, role, ship_no = r.get("name"), r.get("owner_role"), r.get("ship_no")
        if not name or not role:
            print(f"[external] 항목에 name·owner_role 없음 — 건너뜀: {r}")
            continue
        room_state = ext.get(name, {})
        last = room_state.get("last_processed_at")
        print(f"[external] {name} 내보내기 시작")
        p = _export_now_external(name)
        if p is None or not p.exists():
            print(f"[external] {name} — 내보내기 실패, 건너뜀")
            continue
        calls = extract_external(p.read_text(encoding="utf-8", errors="replace"))

        if last is None:
            print(f"[external] {name} — 최초 가동, 과거는 안 올리고 기준선만 잡음({now_key})")
            if not dry:
                ext[name] = {"last_processed_at": now_key, "seen": []}
            continue

        seen = set(room_state.get("seen", []))
        # last 이후(같은 분 포함 — 분 해상도라 같은 분 재발화를 놓치지 않게 >=)만 후보,
        # 그 안에서 이미 처리한 것은 fingerprint 로 걸러낸다(같은 분 중복 발화 대비).
        candidates = [c for c in calls if call_key(c) >= last]
        fresh_all = [c for c in candidates if fingerprint(c) not in seen]
        fresh = fresh_all[-MAX_LINES:]
        skipped = len(fresh_all) - len(fresh)
        print(f"[external] {name} — {last} 이후 {len(candidates)}건 · 새 것 {len(fresh_all)}건" +
              (f" · 배에는 최근 {MAX_LINES}건만(초과 {skipped}건 생략)" if skipped else ""))

        new_last = max((call_key(c) for c in candidates), default=last)
        new_last = max(new_last, last)
        if not fresh_all:
            if not dry:
                ext[name] = {"last_processed_at": new_last, "seen": sorted(seen)[-500:]}
            continue
        any_new = True
        rooms_with_new.append(name)
        if dry:
            for c in fresh:
                print(f"    (dry) {c['who']}: {c['text'][:60]}")
            continue
        disp = _append_to_ship(role, name, ship_no, fresh)
        if disp is None:
            _new_ship_for_external(role, name, fresh)
        ext[name] = {"last_processed_at": new_last,
                     "seen": sorted(seen | {fingerprint(c) for c in candidates})[-500:]}
        _ping_external(name, role, fresh, disp)
    if snap is not None:
        activity["mtimes"] = snap
        if rooms_with_new:
            hist = activity.setdefault("history", [])
            hist.append({"at": now_key, "changed_ids": changed_ids, "rooms_with_new": rooms_with_new})
            activity["history"] = hist[-5:]  # 매핑용 흔적만 — 최근 5건만 쌓는다
    if not dry:
        _save(st)
        _commit_state()
    if not any_new:
        print("[external] 새 줄 없음 — 전 방 조용")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=f"{ROOM} 방 「{WAKE}」 호출 접수")
    ap.add_argument("--file", help="카톡에서 내보낸 대화 txt(미지정 시 아카이브 최신본)")
    ap.add_argument("--export", action="store_true",
                    help="지금 카톡에서 다시 뽑고 읽는다(1시간 예약이 쓰는 경로)")
    ap.add_argument("--since-days", type=int, default=1,
                    help="최근 며칠치 호출만 본다(기본 1 = 오늘). 옛 대화가 한꺼번에 배가 되는 것을 막는다")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--external", action="store_true",
                    help="★중간관리자 대신 kakao_rooms.json external_rooms(밖과 트는 방)를 돈다 — "
                         "새 줄 감지 → owner_role 배에 append(GM 결정 2026-09-08 · 배1137)")
    ap.add_argument("--probe", action="store_true",
                    help="--external 전용 — 로컬DB mtime 판정만 찍고 멈춘다(내보내기 자체를 안 함, "
                         "배1149 스킵판정 검증용)")
    a = ap.parse_args()

    if a.external:
        return run_external(a.dry_run, probe=a.probe)

    p = Path(a.file) if a.file else (_export_now() if a.export else _latest_export())
    if p is None or not p.exists():
        print(f"[FAIL] 읽을 대화 파일이 없다: {p}")
        return 2
    calls = extract(p.read_text(encoding="utf-8", errors="replace"))
    # ★내보낸 파일은 방이 열린 날부터 전부 들어 있다(수천 줄). 날짜 제한이 없으면 첫 실행에
    #   몇 달치 옛 호출이 한꺼번에 배가 된다 — 이미 지나간 이야기라 웰리 항로만 어지럽힌다.
    cutoff = (datetime.now() - timedelta(days=a.since_days)).strftime("%Y-%m-%d")
    old = [c for c in calls if c.get("day", "") < cutoff]
    calls = [c for c in calls if c.get("day", "") >= cutoff]
    st = _state()
    seen = set(st.get("seen", []))
    fresh_all = [c for c in calls if fingerprint(c) not in seen]
    # 이미 방에서 답신된 건(호출 뒤 REPLY_LOOKAHEAD_DAYS 일 내 김남욱 발신 줄)은 지문이 사라져도
    # 다시 배로 뜨지 않는다 — 지문 유지(_commit_state)가 1차 방어, 이건 2차 방어(배1140).
    replied_skip = [c for c in fresh_all if c.get("replied")]
    fresh = [c for c in fresh_all if not c.get("replied")]
    print(f"호출 {len(calls)}건(최근 {a.since_days}일) · 새 것 {len(fresh)}건"
          + (f" · 이미 답신됨(제외) {len(replied_skip)}건" if replied_skip else "")
          + f" · 지난 것 {len(old)}건 건너뜀")
    made = []
    for c in fresh:
        if to_ship(c, a.dry_run) and not a.dry_run:
            seen.add(fingerprint(c))
            made.append(c)
    if not a.dry_run:
        for c in replied_skip:
            seen.add(fingerprint(c))
        st["seen"] = sorted(seen)
        _save(st)
        _commit_state()
        _ping(made)
    return 0


def _ping(made: list[dict]) -> None:
    """호출을 받았다는 사실만 AI 진행현황방에 한 줄. 발신 도구는 기존 것 하나뿐(약속 L21).

    왜 필요한가: 배는 큐에 잘 쌓이지만 웰리 세션이 열려야 눈에 띈다. 실무진은 물어 놓고
    답을 기다리는데 다음 날 아침까지 아무도 모르면, 받아 놓고 방치한 것과 같다.
    ★한 번 실행에 한 줄만 보낸다 — 호출마다 보내면 여러 통이 몰아쳐 방이 시끄러워진다.
    """
    if not made:
        return                      # 조용한 것이 정상 — 호출이 없으면 아무 말도 하지 않는다
    who = " · ".join(dict.fromkeys(c["who"] for c in made))
    first = made[0]["text"].replace("\n", " ")[:40]
    msg = (f"★중간관리자 방에서 웰리를 {len(made)}번 불렀습니다 — {who}\n"
           f"   첫 건: {first}…\n   웰리 항로에 배로 올려 뒀습니다.")
    try:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "notify_gm_progress.py"),
                        msg, "--ship", "시토 733", "--state", "done"],
                       capture_output=True, text=True, encoding="utf-8",
                       cwd=str(ROOT), timeout=60)
    except Exception as e:          # 알림 실패가 접수를 되돌리면 안 된다 — 배는 이미 떴다
        print(f"[WARN] 알림 실패(배는 정상 등록됨): {type(e).__name__}: {e}")


def demo() -> None:
    """자체 점검 — 「웰리」 줄만 뽑고 남의 대화는 안 가져오는지."""
    sample = (
        "[이경연] [오전 9:10] 오늘 청소 시간 조정합니다\n"
        "[이정헌] [오전 9:12] 웰리야 정화조 공사 일정 언제였지?\n"
        "확인 부탁해\n"
        "[나우열] [오전 9:20] 네 확인했습니다\n"
        "[임정은] [오전 9:31] 웰리, 회원 명단 링크 좀\n"
        "[김남욱] [오전 9:40] 웰리님 어제 접수건 정리해줘\n"
    )
    got = extract(sample)
    assert len(got) == 3, got
    assert got[0]["who"] == "이정헌" and got[0]["text"].startswith("정화조"), got[0]
    assert "확인 부탁해" in got[0]["text"], "여러 줄 호출이 이어붙지 않았다"
    assert "네 확인했습니다" not in got[0]["text"], "남의 대화가 딸려 들어왔다"
    assert got[1]["text"].startswith("회원 명단"), got[1]
    # 호칭이 붙어도 본문만 남는다 — "야"·"님"이 본문 앞에 남으면 그대로 배 제목이 된다.
    assert got[2]["text"].startswith("어제 접수건"), got[2]
    assert extract("[A] [오전 1:00] 웰리야") == [], "본문 없는 호출은 버려야 한다"
    assert extract("[A] [오전 1:00] 웰리") == [], "이름만 부른 것도 버려야 한다"
    print("[OK] 자체 점검 통과 — 「웰리」·「웰리야」·「웰리님」 3건 추출, 남의 대화 미포함")

    # replied 판정 — 배1140 실사고 재현: 호출 다음날 김남욱 발신이 있으면 replied=True.
    reply_sample = (
        "--------------- 2026년 9월 7일 월요일 ---------------\n"
        "[이경연 실장] [오후 5:29] 웰리 분리수거장 마감일 변경함\n"
        "--------------- 2026년 9월 8일 화요일 ---------------\n"
        "[김남욱] [오전 8:00] 실장님, 분리수거장 건 확인했습니다.\n"
        "--------------- 2026년 9월 9일 수요일 ---------------\n"
        "[이정헌] [오전 9:00] 웰리 소화기 점검일 언제였지?\n"
    )
    got3 = extract(reply_sample)
    assert len(got3) == 2, got3
    assert got3[0]["replied"] is True, "다음날 김남욱 발신을 답신으로 못 잡았다(배1140 재발)"
    assert got3[1]["replied"] is False, "답신 없는 호출을 답신됨으로 오판했다"
    print("[OK] replied 판정 자체 점검 통과 — 호출 뒤 김남욱 발신 유무 정상 판정")

    # external_rooms 감지 — 우리 쪽(GM_SELF) 발신은 빠지고 상대 발언만 남는지.
    ext_sample = (
        "[김남욱] [오후 4:22] 오우 굳굳\n"
        "[다이어트캠프 이승기 대표님] [오후 4:54] 색이 맞다\n"
        "자진 좋다\n"
        "[김남욱] [오후 5:00] 감사합니다\n"
    )
    got2 = extract_external(ext_sample)
    assert len(got2) == 1, got2
    assert got2[0]["who"] == "다이어트캠프 이승기 대표님", got2[0]
    assert "자진 좋다" in got2[0]["text"], "여러 줄 발언이 이어붙지 않았다"
    assert "감사합니다" not in got2[0]["text"], "우리 쪽 발신이 딸려 들어왔다"
    print("[OK] external_rooms 자체 점검 통과 — GM_SELF 발신 제외, 상대 발언만 추출")

    # last_processed_at 커서 계산(call_key) — 오전/오후 12시 경계가 실수하기 가장 쉬운 지점.
    assert call_key({"day": "2026-09-08", "when": "오전 11:18"}) == "2026-09-08 11:18"
    assert call_key({"day": "2026-09-08", "when": "오후 8:07"}) == "2026-09-08 20:07"
    assert call_key({"day": "2026-09-08", "when": "오후 12:00"}) == "2026-09-08 12:00", "오후 12시=정오"
    assert call_key({"day": "2026-09-08", "when": "오전 12:00"}) == "2026-09-08 00:00", "오전 12시=자정"
    assert call_key({"day": "2026-09-07", "when": "오전 11:18"}) < call_key({"day": "2026-09-08", "when": "오전 0:01"})
    print("[OK] call_key 자체 점검 통과 — 오전/오후 12시 경계·날짜 비교 정상")

    # 로컬DB mtime 스킵 판정(배1149) — 기준선 없음=전부 변화, 있음=늘어난 것만.
    assert _kakao_local_changed(None, {"a": 1.0}) == ["a"], "기준선 없을 때는 안전 쪽(전부 변화)"
    assert _kakao_local_changed({"a": 1.0}, {"a": 1.0}) == [], "안 늘었으면 변화 없음"
    assert _kakao_local_changed({"a": 1.0}, {"a": 2.0, "b": 5.0}) == ["a", "b"], "늘었거나 새로 생기면 변화"
    print("[OK] 로컬DB mtime 스킵 판정 자체 점검 통과")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--selfcheck":
        demo()
    else:
        raise SystemExit(main())
