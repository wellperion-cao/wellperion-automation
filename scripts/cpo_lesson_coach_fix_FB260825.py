# -*- coding: utf-8 -*-
"""
강습 회원관리 담당강사 1건 교정 (2026-08-25 · 접수ID FB260825-154700)

실무진 피드백(박민서):
  수영 서승규 010-4525-7585 / SUC 상태 / 담당 이형주 → 박주혜
  8월 20일 등록완료 / 유소년 단체강습 4회 / 종료일 10월 19일

사용:
  python scripts\\cpo_lesson_coach_fix_FB260825.py --dry-run   # 레코드 확인만(쓰기 없음)
  python scripts\\cpo_lesson_coach_fix_FB260825.py             # 실제 담당 변경

되돌리기:
  python scripts\\cpo_lesson_coach_fix_FB260825.py --restore   # 이형주로 원복
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
BACKUP = REPO / "status" / "backups" / "lesson_coach_fix_FB260825.json"

TARGET_PHONE = "010-4525-7585"
TARGET_NAME  = "서승규"
TARGET_FROM  = "이형주"
TARGET_TO    = "박주혜"
LESSON_TYPE  = "유소년강습"
SUC_STATUS   = ("SUC", "단기SUC")


def _fetch_lesson_rows() -> list[dict] | None:
    try:
        resp = requests.get(
            FUNNEL_EXEC_URL,
            params={"action": "lesson_inquiry_list", "type": LESSON_TYPE, "scope": "all"},
            timeout=60,
            allow_redirects=True,
        )
        data = resp.json()
        if not data.get("ok"):
            print(f"[error] GAS 응답 ok=false: {data.get('error') or data}")
            return None
        return data.get("data") or []
    except Exception as e:
        print(f"[error] 조회 실패: {e}")
        return None


def _find_target(rows: list[dict]) -> list[dict]:
    phone_norm = TARGET_PHONE.replace("-", "").replace(" ", "")
    hits = []
    for r in rows:
        phone = str(r.get("phone") or r.get("휴대폰") or r.get("연락처") or "").replace("-", "").replace(" ", "")
        status = str(r.get("status") or r.get("진행상태") or "")
        if phone == phone_norm and status in SUC_STATUS:
            hits.append(r)
    return hits


def _write_owner(row: dict, new_owner: str, dry: bool) -> tuple[bool, str]:
    if dry:
        return True, "DRY"
    params = {
        "action": "lesson_inquiry_update",
        "type": LESSON_TYPE,
        "rowIndex": str(row.get("rowIndex") or ""),
        "keyPhone": TARGET_PHONE,
        "rowKey": str(row.get("rowKey") or ""),
        "sport": "",
        "owner": new_owner,
    }
    if row.get("gid"):
        params["gid"] = str(row["gid"])
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
    ap.add_argument("--restore", action="store_true", help=f"{TARGET_TO}→{TARGET_FROM} 원복")
    args = ap.parse_args()

    rows = _fetch_lesson_rows()
    if rows is None:
        return 1
    print(f"[fetch] 유소년강습 전체 {len(rows)}행")

    targets = _find_target(rows)
    if not targets:
        print(f"[warn] {TARGET_NAME} ({TARGET_PHONE}) SUC 행 없음 — 종목/상태 확인 필요")
        # 이름만으로 재검색
        name_hits = [r for r in rows if TARGET_NAME in str(r.get("name") or r.get("성함") or "")]
        if name_hits:
            print(f"  이름 매칭 {len(name_hits)}건(상태 무관):")
            for r in name_hits[:5]:
                print(f"    rowIndex={r.get('rowIndex')} status={r.get('status')} phone={r.get('phone')} owner={r.get('owner')}")
        return 1

    new_owner = TARGET_FROM if args.restore else TARGET_TO

    if not args.dry_run and not args.restore:
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        BACKUP.write_text(
            json.dumps([{"rowIndex": r.get("rowIndex"), "rowKey": r.get("rowKey"),
                         "name": r.get("name"), "phone": r.get("phone"),
                         "owner_before": r.get("owner"), "gid": r.get("gid")} for r in targets],
                        ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[backup] 원본 저장 → {BACKUP}")

    for r in targets:
        cur_owner = str(r.get("owner") or "").strip()
        name = str(r.get("name") or TARGET_NAME)
        ri = r.get("rowIndex")
        print(f"[target] rowIndex={ri} / {name} / 현재담당={cur_owner or '(없음)'} → {new_owner}")

        ok, err = _write_owner(r, new_owner, args.dry_run)
        if ok:
            tag = "[DRY]" if args.dry_run else "[OK]"
            print(f"  {tag} 담당 변경 완료: {cur_owner or '(없음)'} → {new_owner}")
        else:
            print(f"  [FAIL] rowIndex={ri} — {err}")
            return 1
        time.sleep(0.3)

    if args.dry_run:
        print(f"\n★ dry-run 완료. 실제 적용은 --dry-run 없이 실행하세요.")
    elif args.restore:
        print(f"\n★ 원복 완료: {TARGET_TO} → {TARGET_FROM}")
    else:
        print(f"\n★ 교정 완료: {TARGET_FROM} → {TARGET_TO}")
        print(f"  원복: python scripts\\cpo_lesson_coach_fix_FB260825.py --restore")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
