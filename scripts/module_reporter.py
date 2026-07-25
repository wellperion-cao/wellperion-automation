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
_SSOT_DIR = os.path.join(_PROJECT_ROOT, "ssot")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from module_registry import load_registry  # noqa: E402
from clevel_colors import color_dot  # noqa: E402 — 부서 색동그라미 정본(단일 딕셔너리)
import weekly_bundle_pending as _bundle  # noqa: E402 — 배10011 알림 묶기 공용 pending

# ── 배10011(2026-07-24, GM 승인) — 자동화현황방(GM 2인 전용, 실측 확인) 직접 발신을
#   다른 메시지로 흡수한다. (cadence, bot_id) → bundle_id 매핑. 직접 sender() 호출 대신
#   weekly_bundle_pending 에 적재만 하고, 실제 발송은 흡수 대상 메시지(스트림#3·월요일
#   주간묶음)가 소비(consume)+발송 후 mark_bundle_sent() 로 로그를 확정한다.
ABSORB_BUNDLES = {
    ("daily", "자동화현황방"): "stream3_daily",       # 09:10 모듈데일리 → 09:30 스트림#3에 흡수
    ("weekly", "자동화현황방"): "monday_weekly_bundle",  # 월요일 모듈위클리 → AI자기학습제안에 흡수
}

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
               log_path=REPORT_LOG_PATH, sender=None, now=None, heartbeat=False):
    """
    cadence 버킷에서 notify_spec 로 선택된 모듈을 순회·수집·발송(dry_run 시 발송 0).
    registry_path=None → 공유 SSOT(load_registry 기본경로).
    sender: send(chat_id, text)->bool. None이면 notify.telegram_send.send 지연 로드.
    heartbeat: True 면 collect() 성공 직후 module_heartbeat.record_heartbeat() 호출
      (배1307 5차 — "실제 결과를 낸 시점" 기록). 기본 False — pytest 가 가짜 id("good" 등)로
      실제 registry_path·collector 를 우회할 때 status/heartbeats/ 에 테스트 오염 방지.
      실제 CLI(main())는 항상 True 로 호출한다.
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

        # 하트비트(배1307 5차) — collect() 성공 = "실제 결과를 낸 시점"(발송 여부와 무관).
        # dry_run 이든 live 든 수집 자체는 동일하게 실제 GAS/시트 조회이므로 여기서 기록.
        if heartbeat:
            try:
                from module_heartbeat import record_heartbeat  # noqa: PLC0415
                record_heartbeat(mid, detail=str(payload.get("summary_line", ""))[:120])
            except Exception:
                pass  # 하트비트 실패가 리포터 본 작업을 막지 않는다(fail-soft)

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
        # ★배10191(2026-07-25) — 이 게이트가 아래 흡수 분기보다 **먼저** 와야 한다.
        #   전에는 흡수 분기가 앞에 있어서, 흡수 대상(자동화현황방)인 모듈은 그 방의 chat_id 가
        #   null 이어도 게이트를 지나치고 pending 번들에 쌓이기만 했다 — 로그에도 results 에도
        #   'room_unresolved' 가 안 남는 **조용한 실패**. 번들도 결국 같은 방으로 나가므로 방을
        #   못 찾으면 흡수해봤자 아무도 못 받는다. 그러니 못 찾으면 흡수 전에 정직하게 스킵한다.
        #   (이 순서를 지키던 테스트 test_bot_id_str_unresolved_room_skips 가 흡수 분기 도입 때
        #    빨간불이 됐고 그대로 방치돼 있었다 — 안전망이 꺼진 줄도 모르고 있었던 것.)
        if chat_id is None:
            reason = "bot_id_null" if bot_id is None else "room_unresolved"
            _append_log(log_path, {
                "ts": now.isoformat(), "module": mid, "cadence": cadence,
                "dedup_key": key, "sent": False, "reason": reason, "bot_id": bot_id,
            })
            results.append({"module": mid, "action": "skip",
                            "reason": reason, "dedup_key": key})
            continue

        # ★배10011 — 흡수 대상(자동화현황방 등)이면 직접 발송 대신 pending에 적재만.
        #   sent=True 기록은 흡수한 메시지가 실제 발송에 성공한 뒤 mark_bundle_sent()가 한다
        #   (여기서 먼저 sent 처리하면 흡수측이 실패해도 "보낸 걸로" 착각 — 순서 중요).
        bundle_id = ABSORB_BUNDLES.get((cadence, bot_id))
        if bundle_id:
            _bundle.append(bundle_id, source=key, text=text, now=now)
            results.append({"module": mid, "action": "absorbed",
                            "bundle": bundle_id, "dedup_key": key})
            continue

        ok = bool(sender(chat_id, text))
        _append_log(log_path, {
            "ts": now.isoformat(), "module": mid, "cadence": cadence,
            "dedup_key": key, "sent": ok, "chat_id": chat_id,
            "honesty_tag": payload.get("honesty_tag"),
        })
        results.append({"module": mid, "action": "sent" if ok else "send_failed",
                        "dedup_key": key, "sent": ok})

    # 침묵 감지기 스냅샷 갱신(배1307 4차) — 기존 daily 예약작업에 편승, 새 스케줄러 등록 없음.
    # 로컬 파일 기록뿐(알림·네트워크 없음) → dry-run "부작용 0" 계약 보존 위해 실발행에서만 실행.
    if cadence == "daily" and not dry_run:
        try:
            from module_silence_detector import publish_snapshot  # noqa: PLC0415
            publish_snapshot()
        except Exception:
            pass  # 스냅샷 갱신 실패가 본 리포터의 발송 결과를 막지 않는다

        # 재발방지 회귀감시(캐논값·규칙 발산) 일일 실행(2026-07-20 웰리) — status/schedule.json에
        # "매일 09:15" 로 문서화만 돼 있고 실제 Task Scheduler 등록이 없던 사각지대를,
        # 새 예약작업 등록 대신 이미 라이브 등록된 Wellperion-Module-Report-Daily 에 편승해 메운다.
        # 회귀(신규 캐논복사/규칙재서술·가드유실·박제깨짐) 발견 시 내부에서 텔레그램 1줄 경보
        # (telegram_bot/.env TELEGRAM_CHAT_ID=GM 업무보고봇방)까지 자체 처리 — 정상이면 무발신.
        try:
            if _SSOT_DIR not in sys.path:
                sys.path.insert(0, _SSOT_DIR)
            from incident_regression_monitor import run as run_regression_monitor  # noqa: PLC0415
            run_regression_monitor()
        except Exception:
            pass  # 회귀감시 실패가 본 리포터의 발송 결과를 막지 않는다

    return {"cadence": cadence, "date": date_str, "dry_run": dry_run, "results": results}


def mark_bundle_sent(dedup_keys: list[str], *, cadence: str, log_path=REPORT_LOG_PATH, now=None) -> None:
    """배10011 — weekly_bundle_pending 으로 흡수된 모듈들을, 흡수한 메시지가 실제로
    발송 성공한 뒤 이 함수로 module_report_log.jsonl 에 sent=True 확정 기록한다.
    이래야 다음 실행에서 _already_sent() 가 True 를 내어 재적재·중복을 막는다."""
    now = now or datetime.now()
    for key in dedup_keys:
        mid = key.split("|", 1)[0]
        _append_log(log_path, {
            "ts": now.isoformat(), "module": mid, "cadence": cadence,
            "dedup_key": key, "sent": True, "note": "absorbed_bundle(배10011)",
        })


def main(argv=None):
    ap = argparse.ArgumentParser(description="범용 모듈 자동보고 리포터(공유 SSOT 소비)")
    ap.add_argument("--cadence", required=True, choices=VALID_CADENCES)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--module", default=None)
    args = ap.parse_args(argv)

    out = run_report(args.cadence, dry_run=args.dry_run, only_module=args.module, heartbeat=True)

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
