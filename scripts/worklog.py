# scripts/worklog.py
# 전 C-Level 공용 "작업 현황 로그" 기록 모듈 (2026-07-23, GM 승인 · CMO-2026-07-23-WORKLOG-PANEL).
#
# 계기: AI하루 EP10이 검수큐 등록 누락돼 아무도 못 봄(2026-07-23 실사고) — 로그가
# "한 일"만 남기면 "빠진 것"은 놓친다. 이 모듈은 "한 일" 쪽(기록)만 담당한다.
# "빠진 것" 자동 적발은 scripts/worklog_gaps.py.
#
# API 1개:
#   from worklog import log
#   log(role, area, event, result="ok", detail="", ref="", url="")
#   → status/worklog.jsonl 에 1줄 append.
#
# ★고정 스키마(절대 변경 금지 — 화면 담당 에이전트가 동시에 이 규격으로 렌더 중):
#   {"ts":"2026-07-23T07:39:35+09:00","role":"cmo","area":"발행",
#    "event":"AI하루 01 인스타 발행","result":"warn",
#    "detail":"성공 토스트 확인·주소 미회수","ref":"CMO-...","url":""}
#   - ts = ISO8601 KST(+09:00) / role ∈ ceo|cfo|chro|cmo|coo|cpo|cto
#   - area = 짧은 한국어 분류(예 "발행","검수","제작","점검")
#   - event = 한 줄 한국어 요약(실무진이 읽는다 — 영어·코드·약어 금지)
#   - result ∈ ok|warn|fail / detail·ref·url 선택
#
# ★ best-effort — 기록 실패가 호출부(발행 등 본업)를 절대 막지 않는다.
#   log() 는 절대 예외를 던지지 않고 성공 여부(bool)만 반환한다.
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
WORKLOG_PATH = ROOT / "status" / "worklog.jsonl"

KST = timezone(timedelta(hours=9))

VALID_RESULTS = {"ok", "warn", "fail"}
_APPEND_RETRIES = 3
_APPEND_RETRY_WAIT_SEC = 0.2


def log(
    role: str,
    area: str,
    event: str,
    result: str = "ok",
    detail: str = "",
    ref: str = "",
    url: str = "",
) -> bool:
    """status/worklog.jsonl 에 고정 스키마로 1줄 append. best-effort(항상 bool 반환, 예외 안 던짐).

    role: ceo|cfo|chro|cmo|coo|cpo|cto (소문자 정규화만 하고 값 자체는 검증 실패해도 기록 시도
          — 스키마 계약을 지키되 호출부를 막지 않는 게 우선).
    result: ok|warn|fail (그 외 값이 오면 'ok'로 안전 폴백).
    """
    try:
        result_v = (result or "ok").strip().lower()
        if result_v not in VALID_RESULTS:
            result_v = "ok"
        record = {
            "ts": datetime.now(tz=KST).isoformat(timespec="seconds"),
            "role": (role or "").strip().lower(),
            "area": area or "",
            "event": event or "",
            "result": result_v,
            "detail": detail or "",
            "ref": ref or "",
            "url": url or "",
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"
        WORKLOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        last_exc: Exception | None = None
        for attempt in range(_APPEND_RETRIES):
            try:
                with open(WORKLOG_PATH, "a", encoding="utf-8") as f:
                    f.write(line)
                return True
            except Exception as exc:  # 동시 쓰기 등 — 짧게 재시도
                last_exc = exc
                if attempt < _APPEND_RETRIES - 1:
                    time.sleep(_APPEND_RETRY_WAIT_SEC)
        if last_exc:
            print(f"[WARN] worklog.log append 실패(best-effort): {last_exc}")
        return False
    except Exception as exc:
        print(f"[WARN] worklog.log 예외(best-effort, 호출부 무영향): {exc}")
        return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 4:
        ok = log(sys.argv[1], sys.argv[2], sys.argv[3])
        print(f"[{'OK' if ok else 'FAIL'}] worklog.log() 호출 — {WORKLOG_PATH}")
    else:
        print("사용: python worklog.py <role> <area> <event>")
