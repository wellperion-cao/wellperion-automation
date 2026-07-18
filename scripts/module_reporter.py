# -*- coding: utf-8 -*-
"""
module_reporter.py — 범용 모듈 자동보고 리포터 (공유 SSOT 소비).
─────────────────────────────────────────────────────────────────────────────
정본 등록부 = status/module_registry.json (시우/COO 소유 스키마). 이 리포터는
scripts/module_registry.py:load_registry() 로 등록부를 읽어, 각 모듈의
notify_spec 기준으로 주기·채널을 필터하고, id 규약으로 수집기를 해소해
표준 payload 를 만들어 텔레그램으로 발송한다 → status/module_report_log.jsonl 기록.

플래그:
  --cadence {daily|weekly|monthly}   notify_spec[cadence]==True 인 모듈만
  --dry-run                          발송 0(네트워크 미호출)·payload 프리뷰
  --module <id>                      특정 모듈만

선택 규칙: notify_spec[cadence] is True AND notify_spec.channel == "telegram".
라이브 게이트: notify_spec.bot_id — None 이면 발송 스킵(현재 전부 null=미발효).
  · bot_id int  → 그대로 chat_id
  · bot_id str  → status/telegram_rooms.json 에서 방이름→chat_id 해소
  · bot_id None → 스킵(미발효)
수집기 해소(id 규약): 모듈 id(하이픈) → collectors.<id_underscore>.
  예: cto-automation-health → collectors.cto_automation_health.
  구현 없는 모듈은 '로그+스킵'(오류 아님 · 후속 구현 대기).
멱등: dedup 키 = "{module_id}|{date}|{cadence}". notify_spec 은 슬롯시각 없이
  daily/weekly/monthly 불리언이라 cadence 버킷이 정확한 멱등 단위다.
격리: 한 수집기 예외가 다른 모듈 발송을 막지 않음(실패는 로그만 남기고 넘어감).
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from datetime import datetime

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from module_registry import load_registry  # noqa: E402
from clevel_colors import color_dot  # noqa: E402 — 부서 색동그라미 정본(단일 딕셔너리)

_STATUS_DIR = os.path.join(_PROJECT_ROOT, "status")
ROOMS_PATH = os.path.join(_STATUS_DIR, "telegram_rooms.json")
REPORT_LOG_PATH = os.path.join(_STATUS_DIR, "module_report_log.jsonl")

VALID_CADENCES = ("daily", "weekly", "monthly")


# ── 로더 ─────────────────────────────────────────────────────────────────────
def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# ── 수집기 해소(id 규약) ──────────────────────────────────────────────────────
def collector_module_name(module_id):
    """모듈 id(하이픈) → 수집기 모듈명(언더스코어).
    예: cto-automation-health → collectors.cto_automation_health."""
    return "collectors." + str(module_id or "").replace("-", "_")


# ── 라이브 게이트: notify_spec.bot_id → chat_id ──────────────────────────────
def resolve_chat_id(bot_id, rooms):
    """notify_spec.bot_id → chat_id(int) 또는 None(미발효/미해소).
      int  → 그대로 chat_id
      str  → rooms(방이름→chat_id) 해소(없으면 None)
      None → None(미발효)
    """
    if bot_id is None:
        return None
    if isinstance(bot_id, bool):        # bool 은 int 하위형 — 방어
        return None
    if isinstance(bot_id, int):
        return bot_id
    if isinstance(bot_id, str):
        return rooms.get(bot_id) if isinstance(rooms, dict) else None
    return None


# ── 선택 규칙 ────────────────────────────────────────────────────────────────
def selected_for_cadence(mod, cadence):
    """notify_spec[cadence] is True AND channel == 'telegram' → 선택."""
    spec = mod.get("notify_spec")
    if not isinstance(spec, dict):
        return False
    return bool(spec.get(cadence)) and spec.get("channel") == "telegram"


# ── 템플릿 포맷 ──────────────────────────────────────────────────────────────
def format_report(payload, module_name, cadence, owner_role=None):
    """owner_role 있으면 부서 색동그라미(clevel_colors 정본)를 제목 앞에 붙인다."""
    dot_prefix = (color_dot(owner_role) + " ") if owner_role else ""
    lines = [f"📊 {dot_prefix}{payload.get('title', module_name)} ({cadence})"]
    summary = payload.get("summary_line", "")
    if summary:
        lines.append(summary)
    for m in payload.get("metrics", []):
        lines.append(f"  · {m.get('label')}: {m.get('value')}")
    honesty = payload.get("honesty_tag")
    if honesty:
        lines.append(f"정직: {honesty}")
    link = payload.get("link")
    if link:
        lines.append(link)
    return "\n".join(lines)


# ── 로그 ─────────────────────────────────────────────────────────────────────
def _already_sent(key, log_path):
    """로그에 sent=True 로 남은 동일 dedup 키가 있으면 True(멱등)."""
    if not os.path.exists(log_path):
        return False
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("dedup_key") == key and rec.get("sent") is True:
                    return True
    except Exception:
        return False
    return False


def _append_log(log_path, record):
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ── 핵심 실행 ────────────────────────────────────────────────────────────────
def run_report(cadence, *, dry_run=False, only_module=None,
               registry_path=None, rooms_path=ROOMS_PATH,
               log_path=REPORT_LOG_PATH, sender=None, now=None):
    """
    cadence 버킷에서 notify_spec 로 선택된 모듈을 순회·수집·발송(dry_run 시 발송 0).
    registry_path=None → 공유 SSOT(load_registry 기본경로).
    sender: send(chat_id, text)->bool. None이면 notify.telegram_send.send 지연 로드.
    반환: 실행 결과 dict(테스트·CLI 공용).
    """
    now = now or datetime.now()
    date_str = now.strftime("%Y-%m-%d")

    registry = load_registry(registry_path)
    rooms = load_json(rooms_path, {})
    modules = registry.get("modules", []) if isinstance(registry, dict) else []

    # 발송기 지연 로드(dry-run·테스트에서 미접촉 가능)
    if sender is None and not dry_run:
        from notify.telegram_send import send as sender  # noqa: PLC0415

    results = []

    for mod in modules:
        mid = mod.get("id")
        if only_module and mid != only_module:
            continue
        if not selected_for_cadence(mod, cadence):
            continue

        # ── 수집기 해소(id 규약) — 미구현이면 로그+스킵(오류 아님) ──
        cname = collector_module_name(mid)
        try:
            collector_mod = importlib.import_module(cname)
        except ImportError:
            if not dry_run:
                _append_log(log_path, {
                    "ts": now.isoformat(), "module": mid, "cadence": cadence,
                    "sent": False, "reason": "collector_missing",
                    "note": "collector 미구현·후속", "collector": cname,
                })
            results.append({"module": mid, "action": "skip",
                            "reason": "collector_missing", "collector": cname})
            continue

        # ── 수집(개별 try/except 격리) — 실패는 로그만 남기고 다음 모듈로 ──
        try:
            payload = collector_mod.collect(mod)
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:120]}"
            if not dry_run:
                _append_log(log_path, {
                    "ts": now.isoformat(), "module": mid, "cadence": cadence,
                    "sent": False, "error": err, "dedup_key": None,
                })
            results.append({"module": mid, "action": "error", "error": err})
            continue

        key = f"{mid}|{date_str}|{cadence}"
        text = format_report(payload, mod.get("feature", mid), cadence,
                              owner_role=mod.get("owner_role"))
        bot_id = (mod.get("notify_spec") or {}).get("bot_id")
        chat_id = resolve_chat_id(bot_id, rooms)

        # dry-run: 프리뷰만(네트워크·로그 부작용 0)
        if dry_run:
            results.append({"module": mid, "action": "dry-run", "dedup_key": key,
                            "bot_id": bot_id, "chat_id": chat_id,
                            "payload": payload, "text": text})
            continue

        # 멱등: 동일 {module|date|cadence} 발송 이력 있으면 스킵
        if _already_sent(key, log_path):
            results.append({"module": mid, "action": "skip",
                            "reason": "dedup", "dedup_key": key})
            continue

        # 라이브 게이트: bot_id None(미발효) 또는 방 미해소 → 발송 스킵
        if chat_id is None:
            reason = "bot_id_null" if bot_id is None else "room_unresolved"
            _append_log(log_path, {
                "ts": now.isoformat(), "module": mid, "cadence": cadence,
                "dedup_key": key, "sent": False, "reason": reason, "bot_id": bot_id,
            })
            results.append({"module": mid, "action": "skip",
                            "reason": reason, "dedup_key": key})
            continue

        ok = bool(sender(chat_id, text))
        _append_log(log_path, {
            "ts": now.isoformat(), "module": mid, "cadence": cadence,
            "dedup_key": key, "sent": ok, "chat_id": chat_id,
            "honesty_tag": payload.get("honesty_tag"),
        })
        results.append({"module": mid, "action": "sent" if ok else "send_failed",
                        "dedup_key": key, "sent": ok})

    return {"cadence": cadence, "date": date_str, "dry_run": dry_run, "results": results}


def main(argv=None):
    ap = argparse.ArgumentParser(description="범용 모듈 자동보고 리포터(공유 SSOT 소비)")
    ap.add_argument("--cadence", required=True, choices=VALID_CADENCES)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--module", default=None)
    args = ap.parse_args(argv)

    out = run_report(args.cadence, dry_run=args.dry_run, only_module=args.module)

    for r in out["results"]:
        if r["action"] == "dry-run":
            print(f"[dry-run] {r['module']} → bot_id={r['bot_id']} "
                  f"chat_id={r['chat_id']} key={r['dedup_key']}")
            print(json.dumps(r["payload"], ensure_ascii=False, indent=2))
            print("--- 발송 텍스트 ---")
            print(r["text"])
            print()
        else:
            print(f"[{r['action']}] {r['module']} "
                  f"{r.get('reason', '') or r.get('dedup_key', '') or ''}".rstrip())

    print(f"\n요약: cadence={out['cadence']} dry_run={out['dry_run']} "
          f"결과 {len(out['results'])}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
