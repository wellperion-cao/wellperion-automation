#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 운영 가이드 화면(clevel-guide.html) 저장 대기열을 GM PC 에서 실제로 반영한다.

서버(api_guide.py)가 받아 둔 pending 건을 가져와 저장소 파일에 쓰고 커밋한 뒤,
성공한 건만 서버에 applied 로 알려 대기열에서 치운다. GM 지시 2026-09-14 · 지시자 시토.

열쇠 = token_usage.read_push_key() 재사용(%USERPROFILE%\\.claude\\token_push.key · 없으면
환경변수 ERP_TOKEN_PUSH_KEY) — api_token_usage.py 와 같은 값.

Windows 예약작업(시토 등록 몫) — 10분 주기:
  이름: Wellperion-Guide-Edits-Apply
  명령: python C:\\Users\\jjky0\\welperion-automation\\scripts\\guide_edits_apply.py
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import token_usage as tu  # 열쇠 읽기 재사용(read_push_key)

REPO = tu.REPO
PENDING_URL = "https://erp.wellperion.com/api/guide/pending"
APPLIED_URL = "https://erp.wellperion.com/api/guide/applied"

# 서버 api_guide.py 의 ALLOWED_PATHS 와 같은 값(늘리면 양쪽 다 고친다).
ALLOWED_PATHS = frozenset([
    "3. 웰페리온 가이드/coo/bootsetup_matrix.json",
])


def fetch_pending(key):
    req = urllib.request.Request(PENDING_URL, headers={"X-Token-Push-Key": key})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))["items"]


def report_applied(key, ids):
    body = json.dumps({"ids": ids}).encode("utf-8")
    req = urllib.request.Request(
        APPLIED_URL, data=body, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8", "X-Token-Push-Key": key},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        r.read()


def apply_one(item, dry_run=False):
    """대기 건 하나를 파일에 쓰고 커밋한다. 성공하면 True."""
    path = item.get("path") or ""
    if path not in ALLOWED_PATHS:
        print("건너뜀(허용 경로 밖): %s" % path)
        return False
    content = item.get("content") or ""
    try:
        json.loads(content)
    except Exception:
        print("건너뜀(content 가 JSON 아님): %s" % item.get("id"))
        return False
    if dry_run:
        print("dry-run: %s ← %s (%d bytes)" % (path, item.get("id"), len(content)))
        return True

    abs_path = REPO / path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(content, encoding="utf-8")

    message = "[GM] %s (AI 운영 가이드 화면 저장 · 서버 대기열)" % (item.get("message") or path)
    res = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "safe_commit.py"),
         "--holder", "guide-edits", "-m", message, path],
        cwd=str(REPO),
    )
    return res.returncode == 0


def main():
    dry_run = "--dry-run" in sys.argv
    key = tu.read_push_key()
    if not key:
        sys.stderr.write("열쇠 없음 - %s 또는 환경변수 ERP_TOKEN_PUSH_KEY\n" % tu.TOKEN_PUSH_KEY_FILE)
        return 1
    try:
        items = fetch_pending(key)
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        sys.stderr.write("대기열 조회 실패: %s: %s\n" % (type(e).__name__, e))
        return 1

    if not items:
        print("대기 건 없음")
        return 0

    applied_ids = []
    failed = 0
    for item in items:
        ok = apply_one(item, dry_run=dry_run)
        if ok:
            applied_ids.append(item["id"])
        else:
            failed += 1

    if applied_ids and not dry_run:
        try:
            report_applied(key, applied_ids)
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            sys.stderr.write("applied 통보 실패(파일은 이미 커밋됨): %s: %s\n" % (type(e).__name__, e))

    print("반영 %d건 · 실패(대기열에 남음) %d건" % (len(applied_ids), failed))
    return 1 if failed else 0


def _selfcheck():
    assert not apply_one({"path": "허용밖", "content": "{}"}, dry_run=True)
    assert not apply_one({"path": list(ALLOWED_PATHS)[0], "content": "이건 JSON 아님"}, dry_run=True)
    assert apply_one({"path": list(ALLOWED_PATHS)[0], "content": "{}", "id": "t"}, dry_run=True)
    print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
        sys.exit(0)
    sys.exit(main())
