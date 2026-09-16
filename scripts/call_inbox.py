# -*- coding: utf-8 -*-
"""사람 방 호출 인박스 — status/calls.json 한 원장 (배 2614 줄기 · 2026-09-16 시토 · 웰리 요청).

왜 있나: 업무관리 방(나우열M)·★중간관리자 방에서 웰리를 부른 말이 그동안 「배」로 만들어졌다(9/10~16 생성 207척 중
48척 = 23%). 호출에 답하는 것은 실업무지 체계 작업이 아니다(GM 2026-09-16 「배 = 체계·시스템화만」). 그래서
배 대신 여기 원장에 받고, 살아 있는 웰리 세션이 생존 신호(session_register --heartbeat)에서 미답 호출을 읽어
그 자리에서 답한다. 세션이 없으면 러너가 같은 원장을 읽는다. 아침 보드(hangro_board)엔 「📞 미답 호출 N」 한 줄.

원장 모양: {"calls": [{"id": "C260916-1305-ab12", "room": "업무관리"|"★중간관리자", "who": "...", "text": "...",
                     "at": "2026-09-16T13:05:00+09:00", "answered_at": null, "answer": ""}]}
- text 는 mask_secrets 를 거친 값만(비밀값 원문 금지 · INC-061).
- 중복 = 같은 방·같은 날·같은 본문(앞 80자) → 새로 안 만든다.

쓰는 법:
  python scripts/call_inbox.py --list [--room 업무관리]      미답 호출
  python scripts/call_inbox.py --answer C260916-1305-ab12 --note "답 보냄 13:10"
  python scripts/call_inbox.py --selfcheck
코드에서: from call_inbox import add_call, open_calls, answer_call
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "status" / "calls.json"
KST = timezone(timedelta(hours=9))
ROOMS = ("업무관리", "★중간관리자")


def _now() -> datetime:
    return datetime.now(KST)


def _load(path: Path = PATH) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("calls"), list):
            return d
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {"calls": []}


def _save(d: dict, path: Path = PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".calls-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _mask(text: str) -> str:
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from kakao_room_listen import mask_secrets  # 원문을 적는 자리는 한 함수로(2026-09-15 비밀번호 유출)
        return mask_secrets(text)
    except Exception:
        return text


def _key(room: str, day: str, text: str) -> str:
    return hashlib.sha1(f"{room}|{day}|{text[:80]}".encode("utf-8")).hexdigest()[:8]


def add_call(room: str, who: str, text: str, at: datetime | None = None, path: Path = PATH) -> str | None:
    """호출 한 건 받기. 같은 방·같은 날·같은 본문이면 None(중복). 돌려주는 값 = id."""
    at = at or _now()
    text = _mask((text or "").strip())
    if not text or room not in ROOMS:
        return None
    day = at.strftime("%Y-%m-%d")
    k = _key(room, day, text)
    d = _load(path)
    for c in d["calls"]:
        if c.get("key") == k:
            return None
    cid = f"C{at.strftime('%y%m%d-%H%M')}-{k[:4]}"
    d["calls"].append({"id": cid, "key": k, "room": room, "who": (who or "").strip()[:40], "text": text[:600],
                       "at": at.isoformat(timespec="seconds"), "answered_at": None, "answer": ""})
    _save(d, path)
    return cid


def open_calls(room: str | None = None, path: Path = PATH) -> list[dict]:
    """미답 호출 — 오래된 순."""
    d = _load(path)
    rows = [c for c in d["calls"] if not c.get("answered_at") and (room is None or c.get("room") == room)]
    return sorted(rows, key=lambda c: str(c.get("at") or ""))


def answer_call(cid: str, note: str = "", path: Path = PATH) -> bool:
    d = _load(path)
    for c in d["calls"]:
        if c.get("id") == cid and not c.get("answered_at"):
            c["answered_at"] = _now().isoformat(timespec="seconds")
            c["answer"] = (note or "")[:300]
            _save(d, path)
            return True
    return False


def summary_line(path: Path = PATH) -> str:
    """보드·생존 신호용 한 줄. 미답 0 이면 빈 문자열."""
    rows = open_calls(path=path)
    if not rows:
        return ""
    oldest = rows[0]
    age_h = int((_now() - datetime.fromisoformat(oldest["at"])).total_seconds() // 3600)
    return f"📞 미답 호출 {len(rows)}건 — 가장 오래된 것 {age_h}시간 · {oldest['room']} {oldest['who']}: {oldest['text'][:40]}"


def _selfcheck() -> None:
    import io
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "calls.json"
        t = datetime(2026, 9, 16, 13, 5, tzinfo=KST)
        cid = add_call("업무관리", "나우열M", "웰리 결제 패치가 뭐야", t, p)
        assert cid and cid.startswith("C260916-1305-")
        assert add_call("업무관리", "나우열M", "웰리 결제 패치가 뭐야", t, p) is None      # 같은 날 같은 본문 = 중복
        assert add_call("업무관리", "나우열M", "웰리 결제 패치가 뭐야", t + timedelta(days=1), p)   # 다음 날은 새 호출
        assert add_call("★운영부", "x", "y", t, p) is None                                  # 호출 방 밖은 안 받는다
        assert add_call("★중간관리자", "이정헌 소장", "   ", t, p) is None                    # 빈 본문
        assert len(open_calls(path=p)) == 2 and open_calls("업무관리", p)[0]["id"] == cid
        assert answer_call(cid, "답 보냄", p) and not answer_call(cid, "다시", p)
        assert len(open_calls(path=p)) == 1
        assert summary_line(p).startswith("📞 미답 호출 1건")
        _save({"calls": []}, p)
        assert summary_line(p) == ""
    print("call_inbox selfcheck OK")


def main() -> int:
    ap = argparse.ArgumentParser(description="사람 방 호출 인박스")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--room", choices=ROOMS)
    ap.add_argument("--answer", metavar="ID")
    ap.add_argument("--note", default="")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        _selfcheck(); return 0
    if a.answer:
        ok = answer_call(a.answer, a.note)
        print("답 처리" if ok else "! 그 id 의 미답 호출이 없다"); return 0 if ok else 1
    rows = open_calls(a.room)
    print(summary_line() or "📞 미답 호출 0건")
    for c in rows:
        print(f"- {c['id']} · {c['at'][5:16]} · {c['room']} {c['who']}: {c['text'][:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
