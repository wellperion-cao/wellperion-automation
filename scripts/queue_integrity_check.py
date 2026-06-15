#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/queue_integrity_check.py — 🧭 항로 정합검사 (2026-06-15)

왜: G1 '오늘의 항로' 보드는 두 소스를 머지한다 — 큐(status/_queue.json) + 시트(GAS todo_list).
둘이 어긋나면 유령·중복·상태불일치 배가 보드에 떠 GM이 혼란("한 적 없는데 갑툭튀").
이 검사가 '그 순간' 불일치를 잡아 띄운다. 읽기 전용 — 아무것도 고치지 않는다.

보드의 실제 로더(hangro_board.fetch_gas_items)를 그대로 재사용 → 보드가 보는 것과 동일 기준.

검출(전부 코드로 결정적 판정):
  1) 👻 유령      : 큐에서 폐기/완료인데 시트엔 같은 배가 아직 '살아있음'(보드에 유령으로 뜸)
  2) ⚠️ 상태불일치 : 같은 배가 큐·시트에서 서로 다른 상태(진행중 vs 완료 등)
  3) 🔁 중복위험   : 같은 핵심제목이 큐·시트 양쪽에 있는데 '전체 제목'이 미묘히 달라
                     보드 dedup(전체제목 기준)이 못 합침 → 두 번 뜰 위험
  4) 🧱 형식오류   : 큐 task_id 누락·중복, 미지(未知) 상태값

사용:
  python scripts/queue_integrity_check.py           # 사람용 리포트
  python scripts/queue_integrity_check.py --json     # JSON
  python scripts/queue_integrity_check.py --quiet    # 문제 있을 때만 출력(스케줄·알림용)
종료코드: 문제 0건=0 / 1건 이상=1 (스케줄·게이트용). 네트워크 실패 등은 fail-open(=0).
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

QUEUE_PATH = _REPO / "status" / "_queue.json"

# 보드의 GAS 로더 재사용(보드가 보는 것과 동일). import 실패 시 fail-open.
# ※ hangro_board는 import 시 sys.stdout을 utf-8로 감싼다 — 여기서 또 감싸면 이중래핑으로
#   stdout이 닫히는 버그가 난다. 그래서 직접 감싸지 않고, import 실패 시에만 reconfigure 폴백.
try:
    from hangro_board import fetch_gas_items  # noqa: E402
except Exception as _e:  # pragma: no cover
    fetch_gas_items = None
    _IMPORT_ERR = str(_e)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
else:
    _IMPORT_ERR = ""


# ── 정규화 헬퍼 ────────────────────────────────────────────────────────────
def _full_key(title: str) -> str:
    """보드 dedup이 쓰는 키와 동일: 전체 제목 공백정규화 + 소문자."""
    return re.sub(r"\s+", " ", str(title).strip()).lower()


def _core_key(title: str) -> str:
    """핵심 제목: 맨 앞 [태그]/#번호/머리기호 떼고 정규화 → 같은 배인지 더 잘 매칭."""
    t = str(title)
    t = re.sub(r"^\s*\[[^\]]*\]\s*", "", t)   # 맨 앞 [웰리]·[시토-01] 등 1개 제거
    t = re.sub(r"^\s*#\s*\d+\s*[:·\-]?\s*", "", t)  # 맨 앞 #NN 제거
    return re.sub(r"\s+", " ", t.strip()).lower()


def _canon_status(st: str) -> str:
    """상태를 3분류로: 폐기 / DONE / OPEN."""
    s = str(st)
    if "폐기" in s:
        return "폐기"
    if s.upper() in {"DONE", "완료"} or "완료" in s:
        return "DONE"
    return "OPEN"


# ── 큐 raw 로드(폐기 포함 — 유령검출에 필요) ───────────────────────────────
def load_queue_raw() -> list[dict]:
    if not QUEUE_PATH.exists():
        return []
    try:
        rows = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] _queue.json 읽기 실패: {e}", file=sys.stderr)
        return []
    return rows if isinstance(rows, list) else []


# ── 검사 본체 ──────────────────────────────────────────────────────────────
_KNOWN_STATUS = {
    "PENDING", "IN_PROGRESS", "ON_HOLD", "DONE",
    "완료", "진행중", "대기", "보류", "폐기",
}


def run_checks(gas_items: list[dict] | None = None) -> dict:
    """gas_items를 넘기면 그걸 쓴다(보드가 이미 가진 데이터 재사용 → 중복 네트워크 방지).
    안 넘기면 직접 시트 조회. 큐는 항상 raw(폐기 포함)로 직접 읽는다."""
    findings = {"ghost": [], "status_mismatch": [], "dup_risk": [], "format": []}
    notes = []

    q_raw = load_queue_raw()

    # 4) 형식오류 — 큐 내부(네트워크 불필요)
    seen_tid: dict[str, int] = {}
    for q in q_raw:
        tid = str(q.get("task_id", "")).strip()
        title = str(q.get("title", "")).strip()
        st = str(q.get("status", "")).strip()
        if not title:
            continue
        if not tid:
            findings["format"].append(f"task_id 없음 — 「{title}」")
        else:
            seen_tid[tid] = seen_tid.get(tid, 0) + 1
        if st and st.upper() not in _KNOWN_STATUS and st not in _KNOWN_STATUS:
            findings["format"].append(f"미지 상태값 '{st}' — 「{title}」")
    for tid, n in seen_tid.items():
        if n > 1:
            findings["format"].append(f"task_id 중복 {n}회 — {tid}")

    # 시트(GAS) 비교가 필요한 1~3은 데이터 확보될 때만(fail-open)
    if gas_items is not None:
        gas = gas_items
    elif fetch_gas_items is None:
        notes.append(f"시트 로더 import 실패 → 큐↔시트 비교 생략(fail-open): {_IMPORT_ERR}")
        return {"findings": findings, "notes": notes}
    else:
        try:
            gas = fetch_gas_items()
        except Exception as e:
            notes.append(f"시트(GAS) 조회 실패 → 큐↔시트 비교 생략(fail-open): {e}")
            return {"findings": findings, "notes": notes}

    # 시트를 핵심키로 인덱싱(살아있는 것 위주). 같은 키 여러개면 OPEN 우선 보관.
    gas_by_core: dict[str, dict] = {}
    for g in gas:
        ck = _core_key(g.get("title", ""))
        if not ck:
            continue
        cur = gas_by_core.get(ck)
        gc = _canon_status(g.get("status", ""))
        if cur is None or (gc == "OPEN" and _canon_status(cur.get("status", "")) != "OPEN"):
            gas_by_core[ck] = g

    for q in q_raw:
        title = str(q.get("title", "")).strip()
        if not title:
            continue
        ck = _core_key(title)
        qcanon = _canon_status(q.get("status", ""))
        g = gas_by_core.get(ck)
        if not g:
            continue  # 시트에 짝 없음 — 큐 단독배(정상)
        gcanon = _canon_status(g.get("status", ""))

        # 1) 유령: 큐는 폐기/완료인데 시트엔 같은 배가 살아있음(OPEN)
        if qcanon in {"폐기", "DONE"} and gcanon == "OPEN":
            findings["ghost"].append(
                f"「{title}」 — 큐={q.get('status')} / 시트(id {g.get('id')})={g.get('status')} "
                f"→ 보드에 유령으로 뜸. 시트 행도 정리 필요"
            )
            continue

        # 2) 상태 불일치: 둘 다 살아있는데 상태 분류가 다름
        if qcanon != gcanon and not (qcanon in {"폐기", "DONE"} and gcanon in {"폐기", "DONE"}):
            findings["status_mismatch"].append(
                f"「{title}」 — 큐={q.get('status')} / 시트={g.get('status')}"
            )

        # 3) 중복위험: 핵심키는 같은데 '전체 제목'이 달라 보드 dedup이 못 합침
        if qcanon == "OPEN" and gcanon == "OPEN" and _full_key(title) != _full_key(g.get("title", "")):
            findings["dup_risk"].append(
                f"「{title}」(큐) ↔ 「{g.get('title')}」(시트) — 같은 배인데 제목이 달라 보드에 둘 다 뜰 수 있음"
            )

    return {"findings": findings, "notes": notes}


# ── 보드 상단 배너(항로 보드에서 호출) ────────────────────────────────────
def board_banner(gas_items: list[dict] | None = None) -> str:
    """항로 보드 상단에 붙일 1줄 경고. 불일치 없으면 빈 문자열. 절대 예외 안 냄(fail-open)."""
    try:
        r = run_checks(gas_items=gas_items)
        f = r["findings"]
        parts = []
        if f["ghost"]:
            parts.append(f"유령 {len(f['ghost'])}")
        if f["status_mismatch"]:
            parts.append(f"상태불일치 {len(f['status_mismatch'])}")
        if f["dup_risk"]:
            parts.append(f"중복위험 {len(f['dup_risk'])}")
        if f["format"]:
            parts.append(f"형식 {len(f['format'])}")
        if not parts:
            return ""
        return "⚠️ 항로 정합경고 " + " · ".join(parts) + "  (상세: queue_integrity_check.py)"
    except Exception:
        return ""


# ── 리포트 ─────────────────────────────────────────────────────────────────
_LABEL = {
    "ghost":          "👻 유령 (큐 폐기/완료인데 시트엔 살아있음)",
    "status_mismatch": "⚠️ 상태 불일치 (큐 vs 시트)",
    "dup_risk":       "🔁 중복 위험 (제목 미세차이로 보드가 못 합침)",
    "format":         "🧱 형식 오류 (task_id·상태값)",
}


def render(result: dict) -> tuple[str, int]:
    findings = result["findings"]
    total = sum(len(v) for v in findings.values())
    lines = ["🧭 항로 정합검사", "━" * 32]
    if total == 0:
        lines.append("✅ 큐↔시트↔보드 정합 — 불일치 0건")
    else:
        lines.append(f"⚠️ 불일치 {total}건 발견")
        for key in ("ghost", "status_mismatch", "dup_risk", "format"):
            arr = findings[key]
            if not arr:
                continue
            lines.append("")
            lines.append(f"{_LABEL[key]} — {len(arr)}건")
            for msg in arr:
                lines.append(f"  • {msg}")
    for note in result.get("notes", []):
        lines.append("")
        lines.append(f"ℹ️ {note}")
    return "\n".join(lines), total


def main() -> None:
    ap = argparse.ArgumentParser(description="항로 정합검사(읽기 전용)")
    ap.add_argument("--json", action="store_true", help="JSON 출력")
    ap.add_argument("--quiet", action="store_true", help="문제 있을 때만 출력")
    args = ap.parse_args()

    result = run_checks()
    text, total = render(result)

    if args.json:
        out = dict(result["findings"])
        out["_total"] = total
        out["_notes"] = result.get("notes", [])
        print(json.dumps(out, ensure_ascii=False, indent=2))
    elif not (args.quiet and total == 0):
        print(text)

    sys.exit(1 if total > 0 else 0)


if __name__ == "__main__":
    main()
