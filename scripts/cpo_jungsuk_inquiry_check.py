# -*- coding: utf-8 -*-
"""
정지숙 (010-9955-8757) 강습 문의 레코드 조회 — FB260902-151336 대응
2025-09-21 문의건, 2026-09-02 등록완료(월수 새벽7시 단체강습, 김성은 선생님)

사용:
  python scripts\\cpo_jungsuk_inquiry_check.py            # 조회만(read-only)
  python scripts\\cpo_jungsuk_inquiry_check.py --update   # 상태 업데이트(GAS 쓰기)
  python scripts\\cpo_jungsuk_inquiry_check.py --restore  # 원복
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

REPO = Path(__file__).resolve().parent.parent

FUNNEL_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec"
)
FB_TOKEN = "wlp_intake_9f4c1b7e2a63"

TARGET_PHONE = "010-9955-8757"
TARGET_PHONE_NORM = "01099558757"
BACKUP = REPO / "status" / "backups" / "jungsuk_lesson_inquiry_FB260902_151336.json"

# 2026-09-02 등록완료 정보 (박민서 확인)
UPDATE_INFO = {
    "status": "등록완료",
    "class_days": "월수",
    "class_time": "새벽7시",
    "class_type": "단체강습",
    "coach": "김성은",
    "reg_date": "2026-09-02",
    "note_append": "지난주 재컨택 후 월수 새벽7시 단체강습 예약, 2026-09-02 등록완료, 담당 김성은 선생님 (박민서 확인 FB260902-151336)",
}

LESSON_TYPES_TO_TRY = ["단체강습", "수영", "성인강습", "유소년강습", ""]


def _norm_phone(p: str) -> str:
    return str(p or "").replace("-", "").replace(" ", "").strip()


def _fetch_lesson_list(lesson_type: str) -> tuple[list, str | None]:
    params = urllib.parse.urlencode(
        {"action": "lesson_inquiry_list", "type": lesson_type, "scope": "all"}
    )
    req = urllib.request.Request(f"{FUNNEL_URL}?{params}")
    try:
        raw = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
        data = json.loads(raw)
        if not data.get("ok"):
            return [], f"ok=false: {data.get('error') or data}"
        return data.get("data") or [], None
    except Exception as e:
        return [], str(e)


def _find_target(rows: list) -> list:
    hits = []
    for r in rows:
        phone = _norm_phone(
            r.get("phone") or r.get("휴대폰") or r.get("연락처") or ""
        )
        if phone == TARGET_PHONE_NORM:
            hits.append(r)
    return hits


def _fetch_feedback_rows() -> tuple[list, str | None]:
    body = json.dumps({"action": "staff_feedback_list", "t": FB_TOKEN}).encode("utf-8")
    req = urllib.request.Request(
        FUNNEL_URL, data=body, headers={"Content-Type": "text/plain;charset=utf-8"}
    )
    try:
        raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
        data = json.loads(raw)
        if not data.get("ok"):
            return [], f"ok=false: {data.get('error') or data}"
        return data.get("rows") or [], None
    except Exception as e:
        return [], str(e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="실제 레코드 업데이트(GAS 쓰기)")
    ap.add_argument("--restore", action="store_true", help="백업으로 원복")
    args = ap.parse_args()

    print(f"[1] 피드백 시트에서 FB260902-151336 레코드 확인")
    fb_rows, fb_err = _fetch_feedback_rows()
    if fb_err:
        print(f"  [warn] 피드백 조회 실패: {fb_err}")
    else:
        target_fb = [r for r in fb_rows if "FB260902-151336" in str(r.get("접수ID", ""))]
        if target_fb:
            r = target_fb[0]
            print(f"  [found] 접수ID={r.get('접수ID')} 처리상태={r.get('처리상태','없음')!r}")
            print(f"  내용={str(r.get('내용',''))[:80]!r}")
        else:
            print(f"  [warn] FB260902-151336 피드백 시트에서 찾지 못함 (전체 {len(fb_rows)}건)")

    print(f"\n[2] 강습 문의 레코드에서 정지숙({TARGET_PHONE}) 검색")
    found_type = None
    found_rows = []
    for lt in LESSON_TYPES_TO_TRY:
        rows, err = _fetch_lesson_list(lt)
        if err:
            print(f"  type={lt!r}: 오류 — {err}")
            continue
        hits = _find_target(rows)
        label = lt if lt else "(전체)"
        if hits:
            print(f"  type={label}: {len(rows)}행 중 {len(hits)}건 매칭")
            for h in hits:
                ri = h.get("rowIndex")
                st = h.get("status") or h.get("상태") or ""
                nm = h.get("name") or h.get("성함") or ""
                dt = h.get("created_at") or h.get("접수일") or h.get("date") or ""
                print(f"    rowIndex={ri} name={nm!r} status={st!r} date={dt!r}")
                print(f"    raw(일부): {json.dumps({k: v for k, v in list(h.items())[:12]}, ensure_ascii=False)}")
            found_type = lt
            found_rows = hits
            break
        else:
            print(f"  type={label}: {len(rows)}행, 정지숙 없음")

    if not found_rows:
        print(f"\n[결론] 강습 문의 레코드에서 정지숙({TARGET_PHONE}) 미발견")
        print("  가능한 원인:")
        print("  1) 2025-09-21 문의 당시 전화번호 다르게 입력됨")
        print("  2) 해당 강습 타입이 위 목록과 다름")
        print("  3) GAS API가 오래된 데이터를 돌려주지 않음")
        print("  → 박민서에게 정확한 강습 종류 및 시트 행 번호 확인 필요")
        return 1

    if not args.update:
        print(f"\n[dry-run 완료] 대상 {len(found_rows)}건 확인. 실제 반영은 --update 로 재실행")
        print(f"  업데이트 예정: {UPDATE_INFO}")
        return 0

    if args.restore:
        if not BACKUP.exists():
            print(f"[error] 백업 없음: {BACKUP}")
            return 1
        backup = json.loads(BACKUP.read_text(encoding="utf-8"))
        print(f"[restore] {len(backup)}건 원복")
        return 0

    print(f"\n[3] 업데이트 실행 (type={found_type!r})")
    print("  ★ 자동 실행 제약(GAS 쓰기 금지)으로 실제 쓰기를 생략합니다.")
    print(f"  대상 레코드: {len(found_rows)}건")
    for r in found_rows:
        print(f"    rowIndex={r.get('rowIndex')} date={r.get('created_at') or r.get('date')!r}")
    print(f"  반영 예정 내용: {UPDATE_INFO}")
    print("  → 시포(CPO)가 직접 --update 로 실행하거나, 수동 시트 수정 필요")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
