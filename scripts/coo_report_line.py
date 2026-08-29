# -*- coding: utf-8 -*-
"""COO 모듈 일간 자동보고 라인 생성 (레지스트리 telegram.daily_join 구동).

여기서 하루 한 줄짜리 운영 추이 원장(status/coo_daily.jsonl)도 함께 남긴다.
▸왜: 운영 지표가 전부 그날 값으로 덮여 어제가 없었다. 그래서 '나아지고 있나'에
  답할 수가 없었다(GM 2026-08-29: "놓치지말고 계속 이어서 가야해 정말중요해").
▸어디에 얹었나: 08:00 아침보고가 매일 이 함수를 heartbeat=True 로 부른다.
  새 예약작업·새 수집기를 만들지 않고 이미 매일 지나가는 자리에 합류한다(약속 L21).
▸선례: status/member_daily.jsonl(회원 일별)과 같은 모양이다 — 새 관례가 아니다.
"""
import json
import os
from datetime import datetime

import coo_registry as R

_TREND_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "status", "coo_daily.jsonl"
)


def _overdue_3d():
    """접수 3일 초과 건수 — status/reception_watch.json 이 이미 세어 둔 값을 읽기만 한다."""
    p = os.path.join(os.path.dirname(_TREND_PATH), "reception_watch.json")
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("overdue_3d"), d.get("generated_at")
    except Exception:
        return None, None


def _submit_rate():
    """지원부 점검 제출률 — status/kpi_values.json 값을 읽기만 한다(재계산 금지)."""
    p = os.path.join(os.path.dirname(_TREND_PATH), "kpi_values.json")
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("roles", {}).get("coo", {}).get("지원부_제출률")
    except Exception:
        return None


def _overdue_tasks(display: str):
    """업무 마감 넘김 건수 — 이 함수가 방금 받은 표시 문구에서 숫자만 집는다."""
    import re  # noqa: PLC0415
    m = re.search(r"마감 넘긴 일\s*—\s*(\d+)\s*건", display or "")
    return int(m.group(1)) if m else None


def append_daily_trend(work_display: str = "") -> dict | None:
    """오늘 한 줄을 원장에 남긴다. 같은 날짜가 이미 있으면 그 줄을 갈아 끼운다.

    ★값이 없으면 0 으로 메우지 않고 null 로 남긴다(약속 L25) — 안 쌓인 날과
      진짜 0 인 날을 구분해야 추이가 거짓말을 하지 않는다.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    overdue3, rec_at = _overdue_3d()
    rec = {
        "date": today,
        "at": datetime.now().strftime("%H:%M"),
        "접수_3일초과": overdue3,
        "업무_마감넘김": _overdue_tasks(work_display),
        "점검_제출률": _submit_rate(),
        "접수원천_시각": rec_at,
    }
    try:
        rows = []
        if os.path.exists(_TREND_PATH):
            with open(_TREND_PATH, encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        r = json.loads(ln)
                    except Exception:
                        continue
                    if r.get("date") != today:
                        rows.append(r)
        rows.append(rec)
        os.makedirs(os.path.dirname(_TREND_PATH), exist_ok=True)
        with open(_TREND_PATH, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    except Exception:
        return None      # 원장 기록 실패가 08시 보고를 막지 않는다(fail-soft)
    return rec


def build_coo_daily_lines(reg=None, fetch_fn=None, heartbeat=False) -> list:
    """heartbeat=True 면 조회 성공(= 실제 결과 산출) 직후 모듈별 하트비트를 기록한다
    (배1307 5차). 기본 False — pytest 가 이 함수를 직접 호출할 때 status/heartbeats/ 에
    테스트 오염을 남기지 않기 위함. 실제 08시 통합보고 경로(ceo_morning_pipeline.py)만
    True 로 호출한다."""
    reg = reg or R.load_registry()
    fetch = fetch_fn or R._http_get_json
    lines = []
    _work_display = ""      # 업무·결재 표시 문구 — 아래 추이 원장이 마감 넘김 건수를 여기서 집는다
    for m in R.iter_enabled(reg):
        if not m["notify_spec"].get("daily"):
            continue
        f = R.STATUS_FETCHERS.get(m["id"])
        if f is None:
            continue
        name = R.DISPLAY_NAME.get(m["id"], m["feature"])
        try:
            st = f(fetch)
        except Exception:
            lines.append(f"• {name}: (측정 실패 — 정직 표기)")
            continue
        if heartbeat:
            try:
                from module_heartbeat import record_heartbeat  # noqa: PLC0415
                record_heartbeat(m["id"], detail=str(st.get("display", "")))
            except Exception:
                pass  # 하트비트 실패가 08시 보고 본 작업을 막지 않는다(fail-soft)
        if m["id"] == "coo-work-approval":
            _work_display = str(st.get("display", ""))
        badge = "⚠" if st["anomaly"] else "✅"
        lines.append(f"{badge} {name}: {st['display']}")
    # 하루 한 줄 추이 원장 — 실제 08시 경로(heartbeat=True)에서만 남긴다.
    # pytest 가 이 함수를 직접 부를 때 원장을 오염시키지 않기 위함(위 heartbeat 주석과 같은 이유).
    if heartbeat:
        append_daily_trend(_work_display)
    return lines
