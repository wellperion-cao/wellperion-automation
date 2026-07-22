# -*- coding: utf-8 -*-
"""
decision_replay_log.py — 결정 정합 게이트 공용 신호 로거 (2026-07-22 CTO).
─────────────────────────────────────────────────────────────────────────────
스펙: docs/superpowers/specs/2026-07-22-결정정합게이트-전사-design.md §4

각 패턴 K/N 가드가 '옛것 재생을 막는 그 순간' 이 로그에 1줄 append 한다
(status/decision_replay_log.jsonl). self_health_watchdog §6 이 이 로그만 읽어
"오늘 옛것 재생 차단 N건"을 하루 1통 자가건강 디제스트에 노출한다(surface-only).

레코드 스키마(§4.3):
  {date, ts, module_id, subject, action, detail}
  action = "blocked"  — 가드가 재선정/재발송을 정상 차단(정상 작동 증거)
         = "leaked"   — 가드 우회로 실제 재발송된 흔적(회귀감시 에스컬레이션 대상, §6.3)

★ 이 모듈은 발신하지 않는다. 파일 1줄 append 만 한다 — best-effort(실패해도
  절대 raise 하지 않음, 가드/발신 흐름을 죽이지 않는다). additive·부작용 최소.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
LOG_PATH = os.path.join(_PROJECT_ROOT, "status", "decision_replay_log.jsonl")

KST = timezone(timedelta(hours=9))  # 저장소 관행(self_health_watchdog·module_silence_detector 동일)


def append(module_id: str, subject: str, detail: str = "",
           action: str = "blocked", log_path: str = LOG_PATH) -> bool:
    """결정 재생 차단(또는 누출) 신호 1줄 append. 실패해도 False 반환하고 삼킨다.

    module_id : 계약 파일(ssot/decision_contracts.json)의 module_id 와 조인.
    subject   : 무엇이 차단됐나(예: 'CASE08', '실전사례 시리즈', 발행 그룹키).
    detail    : 사람이 읽을 한 줄 설명.
    action    : 'blocked'(정상 차단) | 'leaked'(가드 우회 재발송 — 회귀 대상).
    """
    now = datetime.now(KST)
    rec = {
        "date": now.strftime("%Y-%m-%d"),
        "ts": now.isoformat(timespec="seconds"),
        "module_id": module_id,
        "subject": subject,
        "action": action,
        "detail": detail,
    }
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def read_today(now=None, log_path: str = LOG_PATH) -> list[dict]:
    """오늘(KST) 자 레코드만 반환. 파일 없음/파싱 실패 → 빈 리스트(fail-soft)."""
    if now is None:
        now = datetime.now(KST)
    date_str = now.astimezone(KST).strftime("%Y-%m-%d") if now.tzinfo else now.strftime("%Y-%m-%d")
    out: list[dict] = []
    if not os.path.exists(log_path):
        return out
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict) and rec.get("date") == date_str:
                    out.append(rec)
    except Exception:
        return out
    return out


if __name__ == "__main__":
    # 스모크: 오늘 레코드 요약 출력(발신 없음).
    recs = read_today()
    print(f"decision_replay_log 오늘 {len(recs)}건 (path={LOG_PATH})")
    for r in recs:
        print(f"  · [{r.get('action')}] {r.get('module_id')} — {r.get('subject')}: {r.get('detail')}")
