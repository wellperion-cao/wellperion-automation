# -*- coding: utf-8 -*-
"""COO 모듈 일간 자동보고 라인 생성 (레지스트리 telegram.daily_join 구동)."""
import coo_registry as R


def build_coo_daily_lines(reg=None, fetch_fn=None) -> list:
    reg = reg or R.load_registry()
    fetch = fetch_fn or R._http_get_json
    lines = []
    for m in R.iter_enabled(reg):
        if not m["telegram"].get("daily_join"):
            continue
        try:
            st = R.fetch_check_status(m, fetch_fn=fetch)
        except Exception:
            lines.append(f"• {m['name']}: (측정 실패 — 정직 표기)")
            continue
        parts = []
        for dept, d in st["depts"].items():
            label = {"facility": "시설", "support": "지원"}.get(dept, dept)
            parts.append(f"{label} {d['pct']}%")
        badge = "⚠" if st["anomaly"] else "✅"
        lines.append(f"{badge} {m['name']}: " + " · ".join(parts))
    return lines
