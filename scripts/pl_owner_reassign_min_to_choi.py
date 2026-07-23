# -*- coding: utf-8 -*-
"""
필라테스(P.L) 담당자 일괄 재배정: 민경서 → 최은지 (GM 지시, 2026-07-20).

⚠️ 조영은(689명)은 절대 건드리지 않는다 — 이 스크립트는 P.L 담당자 값이 정확히
'민경서'인 회원만 대상으로 한다(부분일치·공백 변형 매칭 금지).

절차: (1) 대상 조회(member_active_list scope=valid) → (2) 변경 전 백업 JSON 기록
→ (3) member_owner_save POST(전화번호 매칭, 화이트리스트 field='P.L 담당자')로 각 건
쓰기 → (4) 재조회로 민경서 0명·최은지 이전값+대상건수 실측 확인.
숫자가 안 맞으면 백업을 이용해 원복하고 중단(지어내지 않음 — 정직 실패 신호).

기존 인프라 재활용: scripts/cpo_report.py 의 FUNNEL_EXEC_URL·_gas_get() 재사용.
백업 포맷 선례: status/backups/owner_reassign_before_20260720.json 동일 구조.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import requests

from cpo_report import FUNNEL_EXEC_URL, _gas_get

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = REPO_ROOT / "status" / "backups"

FIELD = "P.L 담당자"
OLD_VALUE = "민경서"
NEW_VALUE = "최은지"


def fetch_valid_rows() -> list[dict] | None:
    data = _gas_get("member_active_list", {"scope": "valid"})
    if data is None:
        return None
    return data.get("data", [])


def find_targets(rows: list[dict]) -> list[dict]:
    """P.L 담당자 값이 정확히 '민경서'인 행만(부분일치·공백변형 금지)."""
    return [r for r in rows if str(r.get(FIELD) or "").strip() == OLD_VALUE]


def owner_save(phone: str, field: str, value: str) -> dict:
    payload = {"action": "member_owner_save", "phone": phone, "field": field, "value": value}
    resp = requests.post(
        FUNNEL_EXEC_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "text/plain;charset=utf-8"},
        timeout=30,
        allow_redirects=True,
    )
    try:
        return resp.json()
    except Exception:
        return {"ok": False, "error": f"응답 파싱 실패(http {resp.status_code})"}


def write_backup(targets: list[dict]) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    path = BACKUP_DIR / f"pl_owner_reassign_before_{ts}.json"
    payload = {
        "_comment": "GM 지시 P.L(필라테스) 담당자 재배정 실행 전 백업 — 되돌릴 때 사용",
        "_purpose": f"{FIELD} '{OLD_VALUE}' → '{NEW_VALUE}' 일괄변경 대상 원본 스냅샷(조영은 등 타 강사 미포함)",
        "_created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "_source": "member_active_list?scope=valid (GAS 경유)",
        "field": FIELD,
        "oldValue": OLD_VALUE,
        "newValue": NEW_VALUE,
        "total": len(targets),
        "records": [
            {
                "rowIndex": t.get("rowIndex"),
                "회원명": t.get("회원명"),
                "휴대폰 번호": t.get("휴대폰 번호"),
                "field": FIELD,
                "oldValue": OLD_VALUE,
                "newValue": NEW_VALUE,
            }
            for t in targets
        ],
    }
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run(apply: bool) -> int:
    rows = fetch_valid_rows()
    if rows is None:
        print("[중단] 유효회원 조회 실패(GAS 응답 없음)")
        return 1

    targets = find_targets(rows)
    before_old = len(targets)
    before_new = sum(1 for r in rows if str(r.get(FIELD) or "").strip() == NEW_VALUE)
    print(f"[조회] {FIELD} = '{OLD_VALUE}' 대상 {before_old}명 / 기존 '{NEW_VALUE}' {before_new}명")
    for t in targets:
        print(f"  - {t.get('회원명')} (rowIndex={t.get('rowIndex')})")

    if not apply:
        print("\n[dry-run] --apply 없이는 쓰기 안 함. 대상 확인만.")
        return 0

    if before_old == 0:
        print("[중단] 대상 0명 — 변경할 것 없음.")
        return 0

    backup_path = write_backup(targets)
    print(f"[백업] {backup_path}")

    failures = []
    for t in targets:
        phone = str(t.get("휴대폰 번호") or "").strip()
        if not phone:
            failures.append((t.get("회원명"), "전화번호 없음 — 매칭 불가"))
            continue
        result = owner_save(phone, FIELD, NEW_VALUE)
        if not result.get("ok"):
            failures.append((t.get("회원명"), result.get("error") or "알 수 없는 실패"))
        else:
            print(f"[저장] {t.get('회원명')} -> {NEW_VALUE} 완료")

    if failures:
        print("\n[실패 발생]")
        for name, err in failures:
            print(f"  - {name}: {err}")
        print(f"백업으로 원복 필요 시: {backup_path}")
        return 1

    # 재조회 검증
    rows_after = fetch_valid_rows()
    if rows_after is None:
        print("[검증 실패] 재조회 실패 — 수동 확인 필요")
        return 1
    after_old = sum(1 for r in rows_after if str(r.get(FIELD) or "").strip() == OLD_VALUE)
    after_new = sum(1 for r in rows_after if str(r.get(FIELD) or "").strip() == NEW_VALUE)
    expected_new = before_new + before_old
    print(f"\n[검증] 변경 후 '{OLD_VALUE}' {after_old}명 / '{NEW_VALUE}' {after_new}명 (기대 {expected_new}명)")

    if after_old == 0 and after_new == expected_new:
        print("[완료] 숫자 일치 — 정상 반영 확인.")
        return 0

    print("[불일치] 숫자가 기대와 다름 — 백업으로 원복이 필요할 수 있음. 수동 확인 요망.")
    print(f"백업: {backup_path}")
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="P.L 담당자 민경서 -> 최은지 재배정")
    parser.add_argument("--apply", action="store_true", help="실제 쓰기 수행(기본은 대상 확인만)")
    raise SystemExit(run(apply=parser.parse_args().apply))
