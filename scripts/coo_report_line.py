# -*- coding: utf-8 -*-
"""COO 모듈 일간 자동보고 라인 생성 (레지스트리 telegram.daily_join 구동)."""
import coo_registry as R


def build_coo_daily_lines(reg=None, fetch_fn=None) -> list:
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
        badge = "⚠" if st["anomaly"] else "✅"
        lines.append(f"{badge} {name}: {st['display']}")
    return lines
