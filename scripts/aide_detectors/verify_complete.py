# -*- coding: utf-8 -*-
"""자동 검증-완결 핸들러 (자율 실행 루프 첫 닫힘 · v1 · 시토).

설계 정본: docs/superpowers/specs/2026-07-09-cto-autonomous-verify-complete-handler-design.md

목표: '검증형' 재개가능·가역 배를 세션 없이 코드가 대신 검증(결정론적 `log_contains`)해
      PASS 시 입항(증거 첨부)·FAIL/불명 시 surface. **PASS만 완결(거짓완료 0)**.

경계(절대 준수):
  - v1 검증기 유형 = `log_contains` 하나. 그 외 유형/스펙 없음 = 무시(오완결 방지).
  - 순수 모듈: verify()=순수함수, close_ship()=순수 뮤테이터, handle()=배 dict in-place 변경까지만.
    **_queue.json 파일 쓰기는 이 모듈이 하지 않는다**(호출측 gm_aide_scan.run 책임 · 기존 패턴 답습).
  - 게이트(AIDE_VERIFY_APPLY)는 호출측이 읽어 gate_on 인자로 전달. OFF면 handle 이 close 하지 않음.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

# scripts/aide_detectors/verify_complete.py → repo 루트(../../..)
ROOT = Path(__file__).resolve().parent.parent.parent

# 라인 앞부분 타임스탬프: 'YYYY-MM-DD[ T]HH:MM:SS'
_LINE_TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})")


def _parse_iso(value) -> datetime | None:
    """since(ISO) 파싱 — 'YYYY-MM-DDTHH:MM:SS' 또는 'YYYY-MM-DD'. 실패 시 None."""
    if not isinstance(value, str):
        return None
    s = value.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_line_ts(line: str) -> datetime | None:
    """라인 앞부분(40자 이내) 타임스탬프 파싱. 없거나 파싱 실패 시 None."""
    m = _LINE_TS_RE.search(line[:40])
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def verify(spec: dict) -> tuple[bool, str]:
    """순수 검증기. v1 = `log_contains` 만 지원.

    spec = {type:'log_contains', path(리포상대), match(문자열), since(ISO·선택), evidence_label(선택)}.
    path 파일에서 match 포함 라인 탐색(since 있으면 라인 앞부분 타임스탬프 ≥ since 만).
    매칭 → (True, '{evidence_label}: {path}에서 매칭 (라인일부)').
    없음/파일없음/타입미지원/예외 → (False, 사유). **예외 안전(throw 금지)**.
    """
    if not isinstance(spec, dict):
        return False, "verify 스펙 없음/형식 오류"
    if spec.get("type") != "log_contains":
        return False, f"미지원 검증 유형: {spec.get('type')!r} (v1=log_contains만)"
    path = spec.get("path")
    match = spec.get("match")
    if not path or match is None:
        return False, "verify 스펙 필드 부족(path·match 필수)"
    label = spec.get("evidence_label") or "log_contains"
    since_dt = _parse_iso(spec.get("since")) if spec.get("since") else None

    file_path = ROOT / path
    if not file_path.exists():
        return False, f"{label}: 로그 파일 없음({path})"
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # 파일 읽기 실패 = 검증 실패(throw 금지)
        return False, f"{label}: 로그 읽기 실패({path}): {e}"

    for line in text.splitlines():
        if match not in line:
            continue
        if since_dt is not None:
            line_dt = _parse_line_ts(line)
            if line_dt is None or line_dt < since_dt:
                continue  # since 이전(또는 타임스탬프 없는) 라인 제외
        snippet = line.strip()[:120]
        return True, f"{label}: {path}에서 매칭 ({snippet})"
    return False, f"{label}: {path}에 match 미발견"


def close_ship(ship: dict, evidence: str, today: str | None = None) -> None:
    """순수 뮤테이터 — 배를 입항(DONE·terminal) 처리하고 증거 첨부.
    이미 terminal 이면 no-op(멱등 · 중복 완결 0). today 미지정 시 오늘 날짜."""
    if ship.get("terminal"):
        return
    ship["status"] = "DONE"
    ship["terminal"] = True
    ship["artifact"] = evidence
    ship["next"] = "🏁 입항 — 자동검증 완결"
    ship["processed_at"] = today or datetime.now().strftime("%Y-%m-%d")


def _is_target(ship: dict) -> bool:
    """검증 대상 = 명시적 `verify` 스펙 보유 + 재개가능·가역.
    가역 판정: aide_flags 에 'resumable' 포함(재개가능 auto 레인 태그) 또는
    reversibility.route(ship)=='auto'(revert_ok·¬external·¬data_loss). 둘 중 하나면 대상."""
    if not isinstance(ship.get("verify"), dict):
        return False
    flags = ship.get("aide_flags")
    if isinstance(flags, list) and "resumable" in flags:
        return True
    try:
        import reversibility  # type: ignore
        return reversibility.route(ship) == "auto"
    except Exception:
        return False


def handle(ships: list, gate_on: bool, today: str) -> dict:
    """재개가능+가역+`verify` 스펙 가진 배만 순회하며 검증 → 입항/surface.

    각 배: verify() 실행 →
      - ok and gate_on  → close_ship + outcome='closed'
      - ok and not gate → outcome='dryrun_would_close'(status 불변)
      - not ok          → outcome='surface'(status 불변 · 절대 완결 X)
    이미 terminal 배 = outcome='skipped_terminal'(멱등). verify 없음/비대상 = 무시(집계만).

    **_queue 파일 쓰기 없음**(순수 유지 · 호출측 책임). 반환 = counts + 각 배 결과."""
    counts = {"targets": 0, "closed": 0, "surface": 0,
              "dryrun_would_close": 0, "skipped_terminal": 0, "ignored": 0}
    results = []
    for ship in ships:
        if not _is_target(ship):
            counts["ignored"] += 1
            continue
        counts["targets"] += 1
        tid = ship.get("task_id") or str(ship.get("ship_no") or "?")
        if ship.get("terminal"):
            counts["skipped_terminal"] += 1
            results.append({"task_id": tid, "ship_no": ship.get("ship_no"),
                            "ok": None, "outcome": "skipped_terminal",
                            "evidence": "이미 terminal — skip(멱등)"})
            continue
        ok, evidence = verify(ship["verify"])
        if ok and gate_on:
            close_ship(ship, evidence, today)
            outcome = "closed"
            counts["closed"] += 1
        elif ok:
            outcome = "dryrun_would_close"
            counts["dryrun_would_close"] += 1
        else:
            outcome = "surface"
            counts["surface"] += 1
        results.append({"task_id": tid, "ship_no": ship.get("ship_no"),
                        "ok": ok, "outcome": outcome, "evidence": evidence})
    return {"counts": counts, "results": results}
