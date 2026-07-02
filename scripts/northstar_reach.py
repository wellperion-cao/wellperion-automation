# -*- coding: utf-8 -*-
"""
northstar_reach.py  --  북극성 도달율 하이브리드 계산 엔진 (2026-07-02)

입력:
  - 3. 웰페리온 가이드/coo/bootsetup_matrix.json  (role.nsmap.reach 설정)
  - status/kpi_values.json                        (실측 KPI · kpi_collector 산출)
  - status/home_kpi.json                          (있으면 매출 폴백 · 없으면 무시)

출력: status/northstar_reach.json
  역할별 { reach_pct(0~100) 또는 null, mode, basis, updated_at,
          (milestone) milestones_done / milestones_total }

규칙(정직 · ssot/약속 L05 · M4-METRIC-HONESTY):
  - measured: 실측/목표. 실측 미측정=null("측정 개통 전"). 가짜 % 금지.
  - milestone: 완료 마일스톤/전체 (제안본 · done=수동 결재 플래그).
  - 순수 집계 · 파일쓰기만. 라이브 부작용 0.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MATRIX_PATH = ROOT / "3. 웰페리온 가이드" / "coo" / "bootsetup_matrix.json"
KPI_PATH = ROOT / "status" / "kpi_values.json"
HOME_KPI_PATH = ROOT / "status" / "home_kpi.json"
OUT_PATH = ROOT / "status" / "northstar_reach.json"

KST = timezone(timedelta(hours=9))


def _load_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _resolve_source(source: str, kpi: dict | None, home: dict | None, role_id: str) -> dict:
    """reach.source 문자열 → 값 딕셔너리(없으면 {})."""
    kpi = kpi or {}
    if source == "kpi_values.global":
        return (kpi.get("global") or {}) if isinstance(kpi, dict) else {}
    if source.startswith("kpi_values.roles."):
        rid = source.split(".", 2)[2] or role_id
        return ((kpi.get("roles") or {}).get(rid) or {}) if isinstance(kpi, dict) else {}
    if source == "home_kpi":
        return home or {}
    return {}


def _check_ok(val: object, rule: str | None) -> bool:
    """indicator ok 규칙 판정. 값 미측정(None/부재)=미달성(정직)."""
    if rule == "eq0":
        return isinstance(val, (int, float)) and not isinstance(val, bool) and val == 0
    if isinstance(rule, str) and rule.startswith("eq:"):
        return str(val) == rule[3:]
    return False


def _measured_indicators(reach: dict, src: dict) -> tuple[int | None, str]:
    """4지표류 measured — 달성개수/전체×100 + 세부(라벨✓/✗)."""
    inds = reach.get("indicators") or []
    if not inds:
        return None, "지표 정의 없음"
    achieved, details = 0, []
    for ind in inds:
        val = src.get(ind.get("key"))
        ok = _check_ok(val, ind.get("ok"))
        achieved += 1 if ok else 0
        details.append(f"{ind.get('label', '?')}{'✓' if ok else '✗'}")
    total = len(inds)
    pct = round(achieved / total * 100)
    return pct, f"{achieved}/{total} 달성 · " + " ".join(details)


def _measured_target(reach: dict, src: dict) -> tuple[int | None, str]:
    """목표값 대비 실측 measured — min(100, 실측/목표×100). 미측정=null."""
    vk = reach.get("value_key")
    target = reach.get("target")
    val = src.get(vk) if isinstance(src, dict) else None
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        return None, f"{vk} 미측정 — 측정 개통 전"
    if not isinstance(target, (int, float)) or not target:
        return None, "목표값 없음"
    pct = min(100, round(val / target * 100))
    return pct, f"실측 {val} / 목표 {target}"


def _milestone(reach: dict) -> tuple[int | None, str, int, int]:
    """마일스톤 진척 — 완료/전체×100 (제안본)."""
    ms = reach.get("milestones") or []
    total = len(ms)
    if not total:
        return None, "마일스톤 정의 없음", 0, 0
    done = sum(1 for m in ms if m.get("done") is True)
    pct = round(done / total * 100)
    return pct, f"마일스톤 {done}/{total} (제안본 · GM 조정)", done, total


def compute() -> dict:
    matrix = _load_json(MATRIX_PATH) or {}
    kpi = _load_json(KPI_PATH)
    home = _load_json(HOME_KPI_PATH)

    now = datetime.now(KST)
    updated_at = now.strftime("%Y-%m-%dT%H:%M:%S+09:00")

    roles_out: dict[str, dict] = {}
    for role in (matrix.get("roles") or []):
        rid = role.get("id")
        reach = (role.get("nsmap") or {}).get("reach")
        if not rid or not isinstance(reach, dict):
            continue
        mode = reach.get("mode")
        entry: dict = {"mode": mode, "updated_at": updated_at}
        if mode == "measured":
            src = _resolve_source(reach.get("source", ""), kpi, home, rid)
            if reach.get("indicators"):
                pct, basis = _measured_indicators(reach, src)
            else:
                pct, basis = _measured_target(reach, src)
            entry["reach_pct"] = pct
            entry["basis"] = basis
        elif mode == "milestone":
            pct, basis, done, total = _milestone(reach)
            entry["reach_pct"] = pct
            entry["basis"] = basis
            entry["milestones_done"] = done
            entry["milestones_total"] = total
        else:
            entry["reach_pct"] = None
            entry["basis"] = f"알 수 없는 mode: {mode}"
        roles_out[rid] = entry

    return {
        "_doc": (
            "북극성 도달율(하이브리드). 산출: northstar_reach.py. "
            "measured=실측/목표 · milestone=마일스톤 완료/전체. 측정 불가=null(가짜 % 금지)."
        ),
        "generated_at": updated_at,
        "generated_at_kst": now.strftime("%Y-%m-%d %H:%M KST"),
        "roles": roles_out,
    }


def main() -> None:
    data = compute()
    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[northstar_reach] {data['generated_at_kst']}")
    for rid, v in data["roles"].items():
        pct = v.get("reach_pct")
        pct_s = f"{pct}%" if isinstance(pct, (int, float)) else "null(측정 개통 전)"
        print(f"  {rid:5s}: {v['mode']:9s} 도달율={pct_s}  · {v.get('basis', '')}")
    print(f"  -> {OUT_PATH}")


if __name__ == "__main__":
    main()
