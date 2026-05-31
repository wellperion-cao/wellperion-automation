"""
텔레그램 메시지 저장소 — CEO CLI 세션과 bot.py 사이의 "비서 메모장"

모든 텔레그램 수신/발신 메시지를 ceo_inbox.jsonl에 기록.
CEO CLI 세션에서 read_messages()로 조회 가능.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

STORE_FILE = Path(__file__).parent / "ceo_inbox.jsonl"
MAX_LINES = 500


def append_message(direction: str, sender: str, text: str, msg_type: str = "text") -> None:
    entry = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dir": direction,
        "sender": sender,
        "type": msg_type,
        "text": text[:2000],
    }
    with open(STORE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    _rotate_if_needed()


def read_messages(last_n: int = 30) -> list[dict]:
    if not STORE_FILE.exists():
        return []
    lines = STORE_FILE.read_text(encoding="utf-8").strip().splitlines()
    entries = []
    for line in lines[-last_n:]:
        try:
            entries.append(json.loads(line))
        except Exception:
            continue
    return entries


def unread_summary() -> str:
    msgs = read_messages(50)
    if not msgs:
        return "수신 메시지 없음"
    lines = []
    for m in msgs:
        arrow = "<<" if m["dir"] == "in" else ">>"
        lines.append(f"[{m['ts']}] {arrow} {m['sender']}: {m['text'][:80]}")
    return "\n".join(lines)


def _rotate_if_needed() -> None:
    if not STORE_FILE.exists():
        return
    lines = STORE_FILE.read_text(encoding="utf-8").strip().splitlines()
    if len(lines) > MAX_LINES:
        keep = lines[-MAX_LINES:]
        STORE_FILE.write_text("\n".join(keep) + "\n", encoding="utf-8")
