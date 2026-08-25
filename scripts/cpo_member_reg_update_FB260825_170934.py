# -*- coding: utf-8 -*-
"""
회원 등록정보 교정 — 최영천 010-3837-5107 / L재등록 (2026-08-25 · 접수ID FB260825-170934)

실무진 피드백(임정은):
  최영천 010 3837 5107 오늘26/8/25 L재등록완료
  등록일자: 26/8/25 → 2026-08-25
  시작일자: 26/8/25 → 2026-08-25
  종료일자: 27/8/24 → 2027-08-24
  등록분류: L재등록
  종료일(LOSS일자): 삭제 → ""

사용:
  python scripts\\cpo_member_reg_update_FB260825_170934.py --dry-run   # 레코드 확인만(쓰기 없음)
  python scripts\\cpo_member_reg_update_FB260825_170934.py             # 실제 수정
  python scripts\\cpo_member_reg_update_FB260825_170934.py --restore   # 원복

비고:
  LOSS일자 삭제 = L재등록 시 이전 LOSS 일자를 비운다.
  백업은 status/backups/member_reg_update_FB260825_170934.json — 덮어쓰기 금지(cpo_end_date_align 교훈).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

FUNNEL_EXEC_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec"
)
BACKUP = REPO / "status" / "backups" / "member_reg_update_FB260825_170934.json"

TARGET_PHONE = "010-3837-5107"
TARGET_NAME = "최영천"

# (col명, 새 값) 순서대로 적용
# col명은 GAS가 공백·\n 제거 후 정확일치로 찾는다(cpo_end_date_align 주석 동일 원리).
UPDATES = [
    ("등록일자", "2026-08-25"),
    ("시작일자", "2026-08-25"),
    ("종료일자", "2027-08-24"),
    ("등록 분류", "L재등록"),   # 시트 헤더 "등록 분류" (공백 있음)
    ("LOSS일자", ""),            # 종료일 삭제 = LOSS일자 비우기
]


def _norm(p: str) -> str:
    return str(p or "").replace("-", "").replace(" ", "").strip()


def _fetch_members(scope: str = "valid") -> list[dict] | None:
    try:
        r = requests.get(
            FUNNEL_EXEC_URL,
            params={"action": "member_active_list", "scope": scope},
            timeout=60,
            allow_redirects=True,
        )
        data = r.json()
        if not data.get("ok"):
            print(f"[error] member_active_list({scope}) ok=false: {data.get('error') or data}")
            return None
        return data.get("data") or []
    except Exception as e:
        print(f"[error] 조회 실패: {e}")
        return None


def _find(rows: list[dict]) -> dict | None:
    norm = _norm(TARGET_PHONE)
    for r in rows:
        phone = _norm(r.get("휴대폰 번호") or r.get("휴대폰번호") or "")
        if phone == norm:
            return r
    return None


def _read_col(row: dict, col: str) -> str:
    """헤더 \n·공백 무시 대조로 칸 값을 읽는다."""
    key = col.replace("\n", "").replace(" ", "").lower()
    for k, v in row.items():
        if k.replace("\n", "").replace(" ", "").lower() == key:
            return str(v or "")
    return ""


def _write_col(row: dict, col: str, value: str, dry: bool) -> tuple[bool, str]:
    if dry:
        return True, "DRY"
    params = {
        "action": "member_active_update",
        "rowIndex": str(row.get("rowIndex") or ""),
        "col": col,
        "value": value,
        "keyPhone": TARGET_PHONE,
        "rowKey": str(row.get("rowKey") or ""),
    }
    try:
        r = requests.get(FUNNEL_EXEC_URL, params=params, timeout=40, allow_redirects=True)
        r.encoding = "utf-8"
        data = r.json()
        return bool(data.get("ok")), str(data.get("error") or "")
    except Exception as e:
        return False, str(e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="레코드 확인만(쓰기 없음)")
    ap.add_argument("--restore", action="store_true", help="백업으로 원복")
    args = ap.parse_args()

    # 유효회원 탭에서 먼저 찾고, 없으면 종료회원 탭도 확인
    rows = _fetch_members("valid")
    if rows is None:
        return 1
    target = _find(rows)

    if target is None:
        print(f"[info] 유효회원({len(rows)}행)에 없음 — 종료회원(ended) 탭 확인")
        ended = _fetch_members("ended")
        if ended:
            target = _find(ended)
            if target:
                print(f"[warn] 종료회원 탭에서 발견 — 재등록 후 유효회원으로 이동됐는지 확인 필요")
    else:
        print(f"[fetch] 유효회원 {len(rows)}행에서 대상 확인")

    if target is None:
        print(f"[error] {TARGET_NAME}({TARGET_PHONE}) 유효·종료 어디에도 없음 — 전화번호 확인 필요")
        return 1

    ri = target.get("rowIndex")
    name = target.get("회원명") or TARGET_NAME
    print(f"[target] rowIndex={ri} / {name} / 전화={_norm(str(target.get('휴대폰 번호') or ''))}")

    # 현재 값 출력
    for col, new_val in UPDATES:
        before = _read_col(target, col)
        print(f"  현재 {col}: {before!r}")

    if args.restore:
        if not BACKUP.exists():
            print(f"[error] 백업 없음 — {BACKUP}")
            return 1
        backup = json.loads(BACKUP.read_text(encoding="utf-8"))
        print(f"[restore] 백업 {len(backup)}칸 원복")
        ok_cnt = fail_cnt = 0
        for item in backup:
            ok, err = _write_col(target, item["col"], item["before"], dry=False)
            tag = "OK" if ok else f"FAIL({err})"
            print(f"  {tag} {item['col']} ← {item['before']!r}")
            ok_cnt += ok
            fail_cnt += (not ok)
            time.sleep(0.3)
        print(f"원복 완료 — 성공 {ok_cnt} / 실패 {fail_cnt}")
        return fail_cnt

    # 실행(또는 dry-run)
    if not args.dry_run:
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        if BACKUP.exists():
            print(f"[warn] 백업 이미 있음({BACKUP}). 재실행 의심 — 중단. --restore 로 원복 후 재시도.")
            return 1
        backup_data = [{"col": col, "before": _read_col(target, col)} for col, _ in UPDATES]
        BACKUP.write_text(json.dumps(backup_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[backup] 원본 저장 → {BACKUP}")

    ok_cnt = fail_cnt = 0
    for col, new_val in UPDATES:
        before = _read_col(target, col)
        ok, err = _write_col(target, col, new_val, args.dry_run)
        tag = "[DRY]" if args.dry_run else ("[OK]" if ok else f"[FAIL: {err}]")
        print(f"  {tag} {col}: {before!r} → {new_val!r}")
        ok_cnt += ok
        fail_cnt += (not ok)
        time.sleep(0.3)

    if args.dry_run:
        print(f"\n★ DRY-RUN 완료 — 대상 확인됨(rowIndex={ri}). 실제 적용: --dry-run 없이 재실행")
    else:
        print(f"\n★ 완료 — 성공 {ok_cnt} / 실패 {fail_cnt}")
        if fail_cnt == 0:
            print(f"  원복: python scripts\\cpo_member_reg_update_FB260825_170934.py --restore")
    return fail_cnt


if __name__ == "__main__":
    raise SystemExit(main())
