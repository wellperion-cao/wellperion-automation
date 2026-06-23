# -*- coding: utf-8 -*-
"""
kpi_collector.py  --  KPI 자동집계 (1차 vertical slice · 2026-06-23)

측정 가능한 지표만 실수치로 기록. 측정 불가 = null.
거짓 숫자 절대 금지 (대시보드 정직 원칙 · ssot/약속.json 참조).

출력: status/kpi_values.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE_PATH = ROOT / "status" / "_queue.json"
OUT_PATH   = ROOT / "status" / "kpi_values.json"

KST = timezone(timedelta(hours=9))
ACTIVE = {"PENDING", "IN_PROGRESS"}
DONE   = {"DONE"}


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _load_queue() -> list[dict]:
    try:
        data = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _role_stats(ships: list[dict], role: str) -> dict:
    """role별 완료/활성/완결률 계산. 완결률 = DONE / (DONE + ACTIVE)."""
    role_ships = [s for s in ships if isinstance(s, dict) and s.get("clevel") == role]
    done   = sum(1 for s in role_ships if s.get("status") in DONE)
    active = sum(1 for s in role_ships if s.get("status") in ACTIVE)
    total  = done + active
    rate   = round(done / total, 4) if total > 0 else None
    return {"완결률": rate, "완료": done, "활성": active}


def _unpushed_count() -> int | None:
    """origin/master..HEAD 미푸시 커밋 수. 실패 시 None."""
    try:
        r = subprocess.run(
            ["git", "rev-list", "origin/master..HEAD", "--count"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            return int((r.stdout or "0").strip() or "0")
    except Exception:
        pass
    return None


def _mirror_ok() -> str | None:
    """
    status/_queue.json 와 가이드 미러 비교.
    "ok" / "drift" / None(미러 없음)
    """
    mirror = ROOT / "3. 웰페리온 가이드" / "status" / "_queue.json"
    try:
        if not mirror.exists():
            return None
        return "ok" if QUEUE_PATH.read_bytes() == mirror.read_bytes() else "drift"
    except Exception:
        return None


def _integration_health() -> str | None:
    """
    integration_health.py check_bridges() 결과 요약.
    all_ok=True→"ok" / False→"warn" / 예외→None
    """
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from integration_health import check_bridges  # type: ignore
        results = check_bridges()
        all_ok = all(ok for _, ok, _ in results)
        return "ok" if all_ok else "warn"
    except Exception:
        return None


# ── 메인 집계 ─────────────────────────────────────────────────────────────────

def collect() -> dict:
    ships    = _load_queue()
    unpushed = _unpushed_count()
    mirror   = _mirror_ok()
    health   = _integration_health()

    roles_data: dict[str, dict] = {}
    for role in ("ceo", "coo", "cfo", "cmo", "cto", "chro", "cpo"):
        stats = _role_stats(ships, role)
        # 역할별 추가 지표 (1차: 공통 stats만, 역할 특화는 2차)
        roles_data[role] = stats

    now_kst = datetime.now(KST)
    return {
        "_doc": (
            "KPI 자동집계 결과. 측정 불가=null(거짓 숫자 금지). "
            "생성: kpi_collector.py | 스케줄: 일 2회"
        ),
        "generated_at":     now_kst.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "generated_at_kst": now_kst.strftime("%Y-%m-%d %H:%M KST"),
        "global": {
            "unpushed":  unpushed,
            "mirror_ok": mirror,
            "health":    health,
        },
        "roles": roles_data,
    }


def main() -> None:
    data = collect()
    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    g = data["global"]
    print(f"[kpi_collector] {data['generated_at_kst']}")
    print(f"  global: unpushed={g['unpushed']}  mirror={g['mirror_ok']}  health={g['health']}")
    for role, v in data["roles"].items():
        print(f"  {role:5s}: 완결률={v['완결률']}  완료={v['완료']}  활성={v['활성']}")
    print(f"  -> {OUT_PATH}")


if __name__ == "__main__":
    main()
