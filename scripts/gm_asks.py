#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gm_asks.py — GM 손이 꼭 필요한 질문 원장 (GM 2026-09-16 "일을 늘리지 말고 줄여라 · 내가 다 체크한다").

왜 있나
  배 생성 관문(queue_dispatch.py --gm-needed yes)과 GM 답변 가드(gm_wording_guard.py 의
  👉 GM 액션 검사)가 "지금 GM 을 붙잡을 일"을 여기 한 줄씩 쌓는다. GM 은 턴마다 끌려다니지
  않고 07:50 통(또는 hangro_board 📊 줄)에서 한 번에 모아 본다.

스키마: status/gm_asks.json = {"asks": [
    {"id": int, "at": ISO8601(KST), "role": str, "title": str, "why_gm": str,
     "ship_no": int|null, "answered_at": str(""=미답)}]}

쓰는 법
  python scripts/gm_asks.py --list
  python scripts/gm_asks.py --answer <id>
  python scripts/gm_asks.py --selfcheck

# ponytail: JSON 통째 read-modify-write, 전용 락 없음(worklog.jsonl 의 append-only 락과
# 다르다) — 쓰기 빈도가 낮아(사람 개입 요청뿐) 동시쓰기 충돌 위험이 작다. 경합이 실측되면
# queue_lock.py 패턴(msvcrt 바이트범위 락)을 얹는다.
"""
from __future__ import annotations
import argparse
import datetime as _dt
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KST = _dt.timezone(_dt.timedelta(hours=9))


def _resolve_path(path: str | None = None) -> str:
    # 자가점검이 실제 원장을 더럽히지 않도록 GM_ASKS_PATH 로 경로를 바꿔 끼울 수 있다.
    return path or os.environ.get("GM_ASKS_PATH") or os.path.join(ROOT, "status", "gm_asks.json")


def _load(path: str | None = None) -> dict:
    p = _resolve_path(path)
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"asks": []}
    if not isinstance(data, dict) or not isinstance(data.get("asks"), list):
        return {"asks": []}
    return data


def _save(data: dict, path: str | None = None) -> None:
    p = _resolve_path(path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def add(role: str, title: str, why_gm: str = "", ship_no=None, path: str | None = None) -> int:
    """gm_asks.json 에 한 줄 append. 새 항목의 id 를 돌려준다(실패해도 0 — best-effort)."""
    try:
        data = _load(path)
        asks = data["asks"]
        new_id = max((int(a.get("id") or 0) for a in asks), default=0) + 1
        asks.append({
            "id": new_id,
            "at": _dt.datetime.now(tz=KST).isoformat(timespec="seconds"),
            "role": (role or "unknown").strip().lower() or "unknown",
            "title": (title or "")[:120],
            "why_gm": (why_gm or "")[:120],
            "ship_no": ship_no,
            "answered_at": "",
        })
        _save(data, path)
        return new_id
    except Exception:
        return 0


def unanswered(path: str | None = None) -> list[dict]:
    return [a for a in _load(path)["asks"] if not a.get("answered_at")]


def answer(ask_id: int, path: str | None = None) -> bool:
    data = _load(path)
    for a in data["asks"]:
        if a.get("id") == ask_id and not a.get("answered_at"):
            a["answered_at"] = _dt.datetime.now(tz=KST).isoformat(timespec="seconds")
            _save(data, path)
            return True
    return False


def _selfcheck() -> None:
    import tempfile
    tf = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tf.close()
    p = tf.name
    os.unlink(p)  # _load 가 파일 없을 때도 안전한지부터 본다
    try:
        assert _load(p) == {"asks": []}
        i1 = add("cmo", "테스트 질문", "가격 확인", path=p)
        assert i1 == 1, i1
        i2 = add("unknown", "두번째", path=p)
        assert i2 == 2, i2
        assert len(unanswered(p)) == 2
        assert answer(i1, path=p) is True
        assert answer(999, path=p) is False       # 없는 id
        assert answer(i1, path=p) is False         # 이미 답한 id 재답변 금지
        u = unanswered(p)
        assert len(u) == 1 and u[0]["id"] == i2, u
        print("[OK] gm_asks 자가검사 통과")
    finally:
        try:
            os.unlink(p)
        except OSError:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description="GM 손 필요한 질문 원장")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--answer", type=int, default=None, metavar="ID")
    ap.add_argument("--selfcheck", action="store_true")
    args = ap.parse_args()
    if args.selfcheck:
        _selfcheck()
        return 0
    if args.answer is not None:
        ok = answer(args.answer)
        print(f"[{'OK' if ok else 'FAIL'}] gm_asks #{args.answer} 답변 처리")
        return 0 if ok else 1
    u = unanswered()
    print(f"미답 GM 여쭐 것 — {len(u)}건")
    for a in u:
        print(f"  #{a['id']} · {a.get('role')} · {a.get('title')} — {a.get('why_gm')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
