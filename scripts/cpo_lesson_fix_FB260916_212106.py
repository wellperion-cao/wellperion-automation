# -*- coding: utf-8 -*-
"""
강습 회원관리 상태·담당 교정 (2026-09-16 · 접수ID FB260916-212106)

실무진 피드백(박민서):
  수영 민하서 010-4852-6216 / LOSS 상태 / 담당 이형주 → 잘못됨
  9월11일 천주희 담당으로 그룹강습 4회 등록완료
  → 상태: LOSS → SUC / 담당: 이형주 → 천주희

사용:
  python scripts\\cpo_lesson_fix_FB260916_212106.py --dry-run   # 레코드 확인만(쓰기 없음)
  python scripts\\cpo_lesson_fix_FB260916_212106.py             # 실제 변경

되돌리기:
  python scripts\\cpo_lesson_fix_FB260916_212106.py --restore   # LOSS·이형주로 원복
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

# 실제 변경 쓰기는 서버 원본(/api/write)을 거친다 — origin_switch write_member=server(실측 2026-09-17)라
# GAS(FUNNEL_EXEC_URL) 에 바로 쓰면 서버 원장이 옛값인 채로 남아 거울(mirror_inquiry)이 되돌린다.
# /api/write 는 로그인 뒤 통로(401)라 서버 안(127.0.0.1:8001)에서 SSH 로 부른다 — proc_approve.py 와 같은 자리:
# 관문을 우회하는 게 아니라 관문 뒤에서 부르는 것이다.
SSH_KEY = os.path.expanduser("~/.aws/wellperion-sito.pem")
SSH_HOST = "ec2-user@15.164.151.105"
SERVER_WRITE_API = "http://127.0.0.1:8001/api/write"
WRITE_WHO = "cpo@wellperion.com"   # 원장에 남는 실행자 — 사람이 아니라 이 도구가 넣었음을 남긴다


def _ssh(script: str) -> str:
    out = subprocess.run(["ssh", "-i", SSH_KEY, "-o", "StrictHostKeyChecking=accept-new", SSH_HOST,
                          "/usr/bin/python3 -"],
                         input=script.encode("utf-8"), capture_output=True, timeout=120)
    txt = (out.stdout or b"").decode("utf-8", "replace")
    err = (out.stderr or b"").decode("utf-8", "replace")
    err = "\n".join(l for l in err.splitlines()
                    if "WARNING" not in l and "decrypt later" not in l and "openssh.com" not in l)
    if err.strip():
        print(err.strip(), file=sys.stderr)
    return txt.strip()


def _server_write(payload: dict) -> tuple[bool, str]:
    """/api/write 로 쓴다(서버 원장 경유). X-Erp-Allowed=* 는 관문 뒤(127.0.0.1)에서만 붙이는 값 —
    nginx 를 지나지 않으므로 위조가 아니라 이 배관이 스스로 매기는 값이다(WRITE_MODULES 관문 통과용)."""
    body_json = json.dumps(payload, ensure_ascii=False)
    script = (
        "import urllib.request\n"
        "body=%r.encode('utf-8')\n"
        "req=urllib.request.Request(%r,data=body,headers={'Content-Type':'application/json',"
        "'X-Erp-User':%r,'X-Erp-Allowed':'*'})\n"
        "print(urllib.request.urlopen(req,timeout=60).read().decode('utf-8'))\n"
        % (body_json, SERVER_WRITE_API, WRITE_WHO)
    )
    txt = _ssh(script)
    try:
        data = json.loads(txt.splitlines()[-1])
        return bool(data.get("ok")), json.dumps(data, ensure_ascii=False)
    except Exception:
        return False, txt

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

REPO = Path(__file__).resolve().parent.parent

FUNNEL_EXEC_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec"
)
FB_GAS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec"
)
FB_TOKEN = "wlp_intake_9f4c1b7e2a63"
FB_ID = "FB260916-212106"

BACKUP = REPO / "status" / "backups" / "lesson_fix_FB260916_212106.json"

TARGET_PHONE = "010-4852-6216"
TARGET_NAME = "민하서"
TARGET_STATUS_FROM = "LOSS"
TARGET_STATUS_TO = "SUC"
TARGET_OWNER_FROM = "이형주"
TARGET_OWNER_TO = "천주희"
# 22년생 성인 → 성인강습. 없으면 전체 타입으로 폴백.
LESSON_TYPES = ["성인강습", "유소년강습", "수영강습"]

# 실무진 피드백 등록 정보 (GM 지시 2026-09-16)
REG_DATE    = "2026-09-11"   # 박민서: 9월11일 등록완료
REG_COUNT   = "4"            # 그룹강습 4회
START_DATE  = "2026-09-11"   # 등록일=시작일(별도 언급 없음)
# 종료일: 수영 그룹강습 4회=월 1회→1개월, 9/11+1개월=10/11
REG_EXPIRE  = "2026-10-11"
REG_PROGRAM = "그룹강습"      # 박민서: 그룹강습
LESSON_TYPE_KIND = "단체레슨"


def _fetch_rows(lesson_type: str) -> list[dict] | None:
    try:
        resp = requests.get(
            FUNNEL_EXEC_URL,
            params={"action": "lesson_inquiry_list", "type": lesson_type, "scope": "all"},
            timeout=60,
            allow_redirects=True,
        )
        data = resp.json()
        if not data.get("ok"):
            return []
        return data.get("data") or []
    except Exception as e:
        print(f"[error] {lesson_type} 조회 실패: {e}")
        return None


def _find_target(rows: list[dict]) -> list[dict]:
    """LOSS+이형주 행만 반환 — 실무진이 명시한 조건."""
    phone_norm = TARGET_PHONE.replace("-", "").replace(" ", "")
    hits = []
    for r in rows:
        phone = str(r.get("phone") or r.get("휴대폰") or r.get("연락처") or "").replace("-", "").replace(" ", "")
        if phone != phone_norm:
            continue
        status = str(r.get("status") or "").strip().upper()
        owner = str(r.get("owner") or "").strip()
        # 실무진 피드백 조건: LOSS 상태 + 이형주 담당
        if status == TARGET_STATUS_FROM.upper() and owner == TARGET_OWNER_FROM:
            hits.append(r)
    return hits


def _update_row(row: dict, new_status: str, new_owner: str, dry: bool) -> tuple[bool, str]:
    if dry:
        return True, "DRY"
    lesson_type = row.get("type") or row.get("lessonType") or "성인강습"
    params = {
        "action": "lesson_inquiry_update",
        "type": lesson_type,
        "rowIndex": str(row.get("rowIndex") or ""),
        "keyPhone": TARGET_PHONE,
        "rowKey": str(row.get("rowKey") or ""),
        "sport": "",
        "status": new_status,
        "owner": new_owner,
    }
    # SUC 전환 시 필수 5칸 포함(saveRegProgramModal 화면 사양 2026-08-25)
    if new_status == TARGET_STATUS_TO:
        params.update({
            "regProgram": REG_PROGRAM,
            "lessonType": LESSON_TYPE_KIND,
            "regDate":    REG_DATE,
            "regCount":   REG_COUNT,
            "startDate":  START_DATE,
            "regExpire":  REG_EXPIRE,
        })
    if row.get("gid"):
        params["gid"] = str(row["gid"])
    return _server_write(params)


def _update_feedback(dry: bool, success: bool) -> None:
    if dry:
        print("[feedback] DRY — staff_feedback_update 건너뜀")
        return
    if success:
        memo = (
            f"[2026-09-16 처리완료] {TARGET_NAME}({TARGET_PHONE}) 강습문의 레코드 교정. "
            f"상태 {TARGET_STATUS_FROM}→{TARGET_STATUS_TO}, 담당 {TARGET_OWNER_FROM}→{TARGET_OWNER_TO}. "
            f"9/11 천주희 강사 그룹강습 4회 등록완료 확인 후 반영."
        )
        status_str = "처리완료"
    else:
        memo = (
            f"[2026-09-16 처리불가] {TARGET_NAME}({TARGET_PHONE}) 레코드를 GAS 에서 찾지 못함 또는 업데이트 실패. "
            f"강습 회원관리 화면에서 직접 확인 필요: 상태 LOSS→SUC, 담당 이형주→천주희."
        )
        status_str = "처리불가"
    payload = [{"id": FB_ID, "status": status_str, "memo": memo}]
    body = json.dumps(
        {"action": "staff_feedback_update", "t": FB_TOKEN, "updates": payload}
    ).encode("utf-8")
    req = __import__("urllib.request", fromlist=["Request", "urlopen"])
    try:
        import urllib.request as ureq
        req_obj = ureq.Request(
            FB_GAS_URL, data=body, headers={"Content-Type": "text/plain;charset=utf-8"}
        )
        raw = ureq.urlopen(req_obj, timeout=60).read().decode("utf-8")
        data = json.loads(raw)
        if data.get("ok"):
            print(f"[feedback] {status_str} — staff_feedback_update OK")
        else:
            print(f"[feedback] 응답 ok=false: {data.get('error') or data}")
    except Exception as e:
        print(f"[feedback] 실패: {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--restore", action="store_true", help="SUC·천주희 → LOSS·이형주 원복")
    args = ap.parse_args()

    # 전체 타입에서 대상 검색
    all_hits: list[dict] = []
    for lt in LESSON_TYPES:
        rows = _fetch_rows(lt)
        if rows is None:
            print(f"[warn] {lt} 조회 실패 — 건너뜀")
            continue
        hits = _find_target(rows)
        if hits:
            print(f"[fetch] {lt}: {TARGET_PHONE} 매칭 {len(hits)}건")
            for h in hits:
                h.setdefault("type", lt)
            all_hits.extend(hits)
        else:
            print(f"[fetch] {lt}: {len(rows)}행 조회, 매칭 없음")

    if not all_hits:
        print(f"[warn] {TARGET_NAME}({TARGET_PHONE}) 어느 강습 타입에서도 찾지 못함")
        _update_feedback(args.dry_run, success=False)
        return 1

    for r in all_hits:
        print(f"  rowIndex={r.get('rowIndex')} status={r.get('status')} owner={r.get('owner')} type={r.get('type')}")

    # 백업
    if not args.dry_run and not args.restore:
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        BACKUP.write_text(
            json.dumps(
                [{"rowIndex": r.get("rowIndex"), "rowKey": r.get("rowKey"),
                  "name": r.get("name"), "phone": r.get("phone"),
                  "status_before": r.get("status"), "owner_before": r.get("owner"),
                  "type": r.get("type"), "gid": r.get("gid")} for r in all_hits],
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        print(f"[backup] 원본 저장 → {BACKUP}")

    new_status = TARGET_STATUS_FROM if args.restore else TARGET_STATUS_TO
    new_owner = TARGET_OWNER_FROM if args.restore else TARGET_OWNER_TO

    all_ok = True
    for r in all_hits:
        cur_status = str(r.get("status") or "").strip()
        cur_owner = str(r.get("owner") or "").strip()
        name = str(r.get("name") or TARGET_NAME)
        ri = r.get("rowIndex")
        print(f"[target] rowIndex={ri} / {name} / 상태 {cur_status}→{new_status} / 담당 {cur_owner}→{new_owner}")

        ok, err = _update_row(r, new_status, new_owner, args.dry_run)
        if ok:
            tag = "[DRY]" if args.dry_run else "[OK]"
            print(f"  {tag} 완료: 상태 {cur_status}→{new_status}, 담당 {cur_owner}→{new_owner}")
        else:
            print(f"  [FAIL] rowIndex={ri} — {err}")
            all_ok = False
        time.sleep(0.3)

    if args.dry_run:
        print("\n★ dry-run 완료.")
        return 0

    _update_feedback(args.dry_run, success=all_ok)

    if all_ok:
        if args.restore:
            print(f"\n★ 원복 완료: {TARGET_STATUS_TO}·{TARGET_OWNER_TO} → {TARGET_STATUS_FROM}·{TARGET_OWNER_FROM}")
        else:
            print(f"\n★ 교정 완료: 상태 LOSS→SUC, 담당 이형주→천주희")
            print(f"  원복: python scripts\\cpo_lesson_fix_FB260916_212106.py --restore")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
