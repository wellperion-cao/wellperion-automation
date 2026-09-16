# -*- coding: utf-8 -*-
"""marketing_upload_worker.py — 마케팅 발행 워커 1단계: 접수 큐(서버) → 네이버 블로그 임시저장까지
(배 12680 · GM 확정 2026-09-16 「일단 임시저장까지 · 신뢰 쌓이면 그때부터 자동화 · 발행 완료 시 인스타
및 다른 채널에 내용 같게 해서 생성 후 자동 업로드」).

이 파일은 그 앞부분(임시저장)만 한다. instagram·threads·kakao-channel 등 다른 채널은 손대지 않고
queued 그대로 둔다 — 2단계(공개 자동 + 채널 간 같은 내용 생성)는 다음 배.

흐름: GET /api/marketing/uploads/queue (열쇠 헤더 X-Token-Push-Key · partner_blog_daily._push_key() 와
같은 방식) → naver-blog 채널이 낀 행만 골라 naver_blog_upload_playwright.py --mode draft
(WP_TENANT=tenant) 로 임시저장 → POST /api/marketing/uploads/status 로 채널 결과 기록.

이미지: 큐 응답은 파일 메타(name·path)만 준다 — 서버 파일을 내려받는 문이 이 배 범위(서버 문 2개)에
없어 본문 텍스트만 올린다. 사진 첨부가 필요해지면 다운로드 문을 하나 더 판다.
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPLOADER = ROOT / "scripts" / "naver_blog_upload_playwright.py"
QUEUE_URL = "https://erp.wellperion.com/api/marketing/uploads/queue"
STATUS_URL = "https://erp.wellperion.com/api/marketing/uploads/status"
PUSH_KEY_FILE = Path.home() / ".claude" / "token_push.key"
LOG_FILE = ROOT / "logs" / "marketing_upload_worker.log"
LOCK_FILE = ROOT / "status" / ".marketing_upload_worker.lock"
DAILY_CAP = 5


def _push_key() -> str:
    """발행 PC 열쇠 — partner_blog_daily.py·token_usage_push 와 같은 파일(없으면 환경변수)."""
    try:
        v = PUSH_KEY_FILE.read_text(encoding="utf-8").strip()
        if v:
            return v
    except OSError:
        pass
    return (os.environ.get("ERP_TOKEN_PUSH_KEY") or "").strip()


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as exc:
        print(f"[WARN] 로그 기록 실패(무시): {exc}")


def _fetch_queue(tenant: str = "") -> list[dict]:
    key = _push_key()
    if not key:
        log("[ERROR] 열쇠 없음 — ~/.claude/token_push.key 또는 ERP_TOKEN_PUSH_KEY")
        return []
    url = QUEUE_URL + (("?" + urllib.parse.urlencode({"tenant": tenant})) if tenant else "")
    req = urllib.request.Request(url, headers={"X-Token-Push-Key": key})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = json.load(r)
    except urllib.error.HTTPError as e:
        log(f"[ERROR] 큐 조회 실패 HTTP {e.code}")
        return []
    except Exception as e:                        # noqa: BLE001
        log(f"[ERROR] 큐 조회 실패({type(e).__name__})")
        return []
    if not body.get("ok"):
        log(f"[ERROR] 큐 조회 실패 — {body.get('error')}")
        return []
    return body.get("items") or []


def _report_status(uid: str, channel: str, status: str, note: str) -> bool:
    key = _push_key()
    if not key:
        return False
    payload = json.dumps({"id": uid, "channel": channel, "status": status, "note": note[:500]}).encode("utf-8")
    req = urllib.request.Request(STATUS_URL, data=payload, method="POST",
                                  headers={"X-Token-Push-Key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return bool(json.load(r).get("ok"))
    except Exception as e:                         # noqa: BLE001
        log(f"[WARN] 상태 보고 실패({type(e).__name__})")
        return False


def _filter_naver_targets(items: list[dict], cap: int) -> list[dict]:
    return [it for it in items if "naver-blog" in (it.get("channels") or [])][:cap]


def upload_naver_draft(tenant: str, title: str, body: str, mode: str) -> tuple[int, str]:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False)
    try:
        tmp.write(body)
        tmp.close()
        env = dict(os.environ)
        env["WP_TENANT"] = tenant
        argv = [sys.executable, str(UPLOADER), "--mode", mode, "--title", title, "--body-file", tmp.name]
        ret = subprocess.run(argv, cwd=str(ROOT), env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        out = (ret.stdout or "") + (ret.stderr or "")
        return ret.returncode, out[-4000:]
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="", help="비우면 전 테넌트")
    ap.add_argument("--dry-run", action="store_true", help="서버 조회·본문 조립까지만 — 업로드 호출 안 함")
    ap.add_argument("--self-test", action="store_true", help="순수 함수 자가점검")
    args = ap.parse_args()

    if args.self_test:
        _self_test()
        print("marketing_upload_worker 자가점검 통과")
        return 0

    if args.dry_run:
        items = _fetch_queue(args.tenant)
        targets = _filter_naver_targets(items, DAILY_CAP)
        print(f"[dry-run] queued {len(items)}건 · naver-blog 대상 {len(targets)}건")
        for it in targets:
            print(f"  - {it['id']} {it['tenant']} 「{it['title']}」 {len(it.get('body') or '')}자")
        return 0

    # 겹쳐 돌면 같은 글이 두 번 올라간다 — 2026-09-15 다캠 블로그 중복 사고와 같은 본질. 잠금 파일 하나.
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        age = datetime.now().timestamp() - LOCK_FILE.stat().st_mtime
        if age < 40 * 60:
            log(f"[INFO] 이미 도는 중({int(age)}초 전 시작) — 건너뜀")
            return 0
        LOCK_FILE.unlink(missing_ok=True)          # 40분 넘은 잠금은 죽은 프로세스가 남긴 것
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    atexit.register(lambda: LOCK_FILE.unlink(missing_ok=True))

    items = _fetch_queue(args.tenant)
    targets = _filter_naver_targets(items, DAILY_CAP)
    if not targets:
        log("[INFO] naver-blog 대상 없음")
        return 0

    for it in targets:
        uid, tenant = it["id"], it["tenant"]
        title, body = it.get("title") or "(제목 없음)", it.get("body") or ""
        rc, out = upload_naver_draft(tenant, title, body, mode="draft")
        if rc == 0:
            log(f"[OK] {tenant}/{uid} 임시저장 성공 「{title}」")
            _report_status(uid, "naver-blog", "drafted", "")
        else:
            err = next((ln for ln in reversed(out.splitlines()) if "[ERROR]" in ln), out[-160:])
            log(f"[FAIL] {tenant}/{uid} 임시저장 실패 — {err}")
            _report_status(uid, "naver-blog", "failed", err)
    log(f"[DONE] {len(targets)}건 처리")
    return 0


def _self_test() -> None:
    items = [
        {"id": "a", "channels": ["naver-blog"]},
        {"id": "b", "channels": ["instagram"]},
        {"id": "c", "channels": ["naver-blog", "instagram"]},
    ]
    got = _filter_naver_targets(items, cap=5)
    assert [i["id"] for i in got] == ["a", "c"], got
    assert _filter_naver_targets(items, cap=1) == [items[0]]
    assert _filter_naver_targets(items, cap=0) == []


if __name__ == "__main__":
    sys.exit(main())
