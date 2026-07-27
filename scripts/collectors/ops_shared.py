# -*- coding: utf-8 -*-
"""
ops_shared.py — 운영 다이제스트 2계열(아침 scripts/ops_daily_digest.py ·
밤 telegram_bot/daily_scheduler.py run_daily_digest) 공용 수집층(2026-07-21 순수 리팩터).

두 파일이 "동일 정본 최소 복사" 주석과 함께 각자 들고 있던 GAS URL 상수 3종·재시도 GET
래퍼·UTC→KST 시각 변환·업무완료 상태셋을 이 파일 하나로 수렴한다.

★동작보존 원칙(중요): 값·리턴 시그니처를 그대로 유지한다.
- gas_get(): 두 원본 _gas_get의 재시도(attempts=3)·성공판정(HTTP 200)·리턴(Response|None)
  로직은 동일. 유일한 차이는 daily_scheduler.py 쪽이 실패 시도마다 logger.warning으로
  경보를 남기던 것 — log_fn 콜백으로 그대로 보존(기본값 None=무음, ops_daily_digest.py는
  콜백을 넘기지 않아 기존처럼 무음 유지).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import requests

# 문의·등록 GAS(.deploy-funnel/Survey.js 배포본). inquiry_list=문의알림방 대시보드 소스와 동일 정본.
# env로 오버라이드 가능(기본값=두 소비자 파일이 이전에 각자 갖고 있던 동일 리터럴).
FUNNEL_EXEC_URL = os.environ.get(
    "FUNNEL_EXEC_URL",
    "https://script.google.com/macros/s/AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec",
)
# 종합접수처 GAS(.deploy-reception/RECEPTION_배포.js) — reg_list=6종 접수 카테고리(분실물/시설물고장/청결/칭찬/쓴소리/컴플레인).
RECEPTION_EXEC_URL = os.environ.get(
    "RECEPTION_EXEC_URL",
    os.environ.get("VOC_EXEC_URL", "https://script.google.com/macros/s/AKfycbwk2XS1FND9V2xtXlWgsXzgA5p0FG7jVm6YKD74JK_ME_ZvHsNUUfGE5A_8p0X8VcF3gQ/exec"),
)
# 실무진 업무현황(G1 항로 SSOT·S3) GAS — action=todo_list.
SSOT_API_URL = os.environ.get(
    "SSOT_API_URL",
    "https://script.google.com/macros/s/AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec",
)

# todo_list '상태' 완료 판정 기준(양쪽 소비자 동일).
TODO_DONE_STATUSES = {"완료", "폐기", "DONE", "완료됨"}


def gas_get(
    url: str,
    params: dict | None = None,
    *,
    timeout: int = 40,
    attempts: int = 3,
    label: str = "GAS",
    log_fn=None,
) -> object | None:
    """GAS(script.google.com) GET 재시도 래퍼. 성공(HTTP 200) 시 Response, 전량 실패 시 None.
    log_fn(msg: str)을 넘기면 실패 시도마다 호출(선택 — 기본은 무음)."""
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            if resp.status_code == 200:
                return resp
            if log_fn is not None:
                log_fn(f"{label} HTTP {resp.status_code} (시도 {attempt}/{attempts})")
        except Exception as e:
            if log_fn is not None:
                log_fn(f"{label} 조회 실패 (시도 {attempt}/{attempts}): {e}")
    return None


def utc_iso_to_kst_date(iso_str: str) -> str:
    """문의 API '시각' 필드 → KST YYYY-MM-DD.
    ★2026-07-27 시토(배10357): GAS inquiry_list가 그동안 Date를 그대로 JSON.stringify해
    UTC ISO('...Z')로 내보내던 버그를 서버에서 KST 문자열('YYYY-MM-DD HH:mm:ss', Z 없음)로
    고쳤다(.deploy-funnel-v2/Survey.js). 그 GAS 배포가 나가기 전까지는 라이브가 여전히
    UTC를 준다 — 배포 시점과 이 코드 반영 시점이 어긋나도 이중변환 사고가 안 나도록
    두 포맷을 모두 정확히 처리한다(Z 있으면 UTC로 보고 +9시간, 없으면 이미 KST이므로
    그대로 날짜만 취한다)."""
    s = str(iso_str or "").strip()
    if not s:
        return ""
    try:
        if s.endswith("Z"):
            dt_utc = datetime.fromisoformat(s.rstrip("Z").replace("T", " ")).replace(tzinfo=timezone.utc)
            return (dt_utc + timedelta(hours=9)).strftime("%Y-%m-%d")
        return s[:10]
    except Exception:
        return ""
