# -*- coding: utf-8 -*-
"""COO 모듈 일간 자동보고 라인 생성 (레지스트리 telegram.daily_join 구동)."""
import coo_registry as R


def build_coo_daily_lines(reg=None, fetch_fn=None, heartbeat=False) -> list:
    """heartbeat=True 면 조회 성공(= 실제 결과 산출) 직후 모듈별 하트비트를 기록한다
    (배1307 5차). 기본 False — pytest 가 이 함수를 직접 호출할 때 status/heartbeats/ 에
    테스트 오염을 남기지 않기 위함. 실제 08시 통합보고 경로(ceo_morning_pipeline.py)만
    True 로 호출한다."""
    reg = reg or R.load_registry()
    fetch = fetch_fn or R._http_get_json
    lines = []
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
        badge = "⚠" if st["anomaly"] else "✅"
        lines.append(f"{badge} {name}: {st['display']}")
    return lines
