# -*- coding: utf-8 -*-
"""
integration_health.py — 연동 다리(브릿지) 자가점검 단일 정의 (INC-007 후속).
─────────────────────────────────────────────────────────────────────────────
데이터 소스 사이를 잇는 '다리'가 끊기면(미푸시·라이브 404·미러 드리프트 등)
GM이 먼저 발견하는 일이 반복됐다. 이 모듈이 모든 다리를 한 곳에서 점검한다.
박제 지점(부팅 가드 / 30분 주기 발행기)은 이 모듈을 import 해서만 쓴다 — 정의 복사 금지.

설계 원칙: 모든 점검은 fail-soft. 네트워크·파싱 실패는 예외를 삼키고 ok=False+사유로
떨어진다. check_bridges() 는 절대 예외로 죽지 않는다.

반환: check_bridges() → List[Tuple[name:str, ok:bool, detail:str]]
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── 캐논 상수 (라이브 URL/경로는 여기 1곳에만) ─────────────────────────────────
LIVE_BASE = "https://wellperion-cao.github.io/wellperion-automation"
LIVE_QUEUE_URL = f"{LIVE_BASE}/status/_queue.json"
LIVE_REVIEW_URL = f"{LIVE_BASE}/cmo/review/review_queue.json"
# G1 이 쓰는 업무·결재 SSOT (todo_list GAS) — wellperion_guide(main).html 의 TODO_API_URL 과 동일
SSOT_API_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"
)

LOCAL_QUEUE = ROOT / "status" / "_queue.json"
MIRROR_QUEUE = ROOT / "3. 웰페리온 가이드" / "status" / "_queue.json"

ACTIVE_STATUSES = ("PENDING", "IN_PROGRESS")
HTTP_TIMEOUT = 15
REMOTE = "origin"
BRANCH = "master"


def _http_get(url: str, timeout: int = HTTP_TIMEOUT):
    """GET → (status_code, bytes). cache-bust 쿼리 부착(CDN 지연 회피). 예외는 호출부에서."""
    sep = "&" if "?" in url else "?"
    busted = f"{url}{sep}_cb={int(time.time())}"
    req = urllib.request.Request(
        busted, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def _active_count(items) -> int:
    """리스트에서 active(PENDING+IN_PROGRESS) 건수."""
    if not isinstance(items, list):
        return -1
    return sum(
        1 for x in items if isinstance(x, dict) and x.get("status") in ACTIVE_STATUSES
    )


def _local_active_count() -> int:
    """로컬 status/_queue.json 의 active 건수. 실패 시 -1."""
    try:
        data = json.loads(LOCAL_QUEUE.read_text(encoding="utf-8"))
        return _active_count(data)
    except Exception:
        return -1


def check_queue_live() -> tuple[str, bool, str]:
    """① G1 큐 라이브: HTTP 200 + JSON + 라이브 active == 로컬 active."""
    name = "G1 큐 라이브"
    try:
        status, body = _http_get(LIVE_QUEUE_URL)
        if status != 200:
            return name, False, f"라이브 HTTP {status} — 발행경로 끊김(404 회귀 의심)"
        live = json.loads(body)
        live_active = _active_count(live)
        if live_active < 0:
            return name, False, "라이브 JSON 형식 이상(리스트 아님)"
        local_active = _local_active_count()
        if local_active < 0:
            return name, False, f"라이브 active {live_active}건 / 로컬 큐 읽기 실패"
        if live_active != local_active:
            return (
                name,
                False,
                f"건수 불일치 — 라이브 {live_active}건 ≠ 로컬 {local_active}건"
                f"(미푸시·발행 지연 의심, 즉시 push 필요)",
            )
        return name, True, f"HTTP 200 · active {live_active}건 라이브=로컬 일치"
    except urllib.error.HTTPError as e:
        return name, False, f"라이브 HTTP {e.code} — 발행경로 끊김"
    except Exception as e:
        return name, False, f"점검 실패({type(e).__name__}): {str(e)[:80]}"


def check_queue_mirror() -> tuple[str, bool, str]:
    """② 큐 미러 동기: 로컬 _queue.json == 가이드/status/_queue.json (active·바이트)."""
    name = "큐 미러 동기"
    try:
        if not LOCAL_QUEUE.exists():
            return name, False, "로컬 _queue.json 없음"
        if not MIRROR_QUEUE.exists():
            return name, False, "가이드 미러 _queue.json 없음 — 미러 미생성"
        lb = LOCAL_QUEUE.read_bytes()
        mb = MIRROR_QUEUE.read_bytes()
        local_active = _active_count(json.loads(lb))
        mirror_active = _active_count(json.loads(mb))
        if len(lb) != len(mb) or local_active != mirror_active:
            return (
                name,
                False,
                f"미러 드리프트 — 로컬 active {local_active}건/{len(lb)}B "
                f"≠ 미러 {mirror_active}건/{len(mb)}B",
            )
        return name, True, f"일치 · active {local_active}건/{len(lb)}B"
    except Exception as e:
        return name, False, f"점검 실패({type(e).__name__}): {str(e)[:80]}"


def check_sheet_gas() -> tuple[str, bool, str]:
    """③ 시트 GAS(todo_list) 라이브: HTTP 200 + data 배열 존재."""
    name = "시트 GAS(todo_list)"
    try:
        status, body = _http_get(SSOT_API_URL + "?action=todo_list", timeout=20)
        if status != 200:
            return name, False, f"GAS HTTP {status} — 업무·결재 SSOT 끊김"
        d = json.loads(body)
        data = d.get("data") if isinstance(d, dict) else None
        if not isinstance(data, list):
            return name, False, "응답에 data 배열 없음(엔벨로프 이상)"
        return name, True, f"HTTP 200 · data {len(data)}건"
    except urllib.error.HTTPError as e:
        return name, False, f"GAS HTTP {e.code} — 업무·결재 SSOT 끊김"
    except Exception as e:
        return name, False, f"점검 실패({type(e).__name__}): {str(e)[:80]}"


def check_review_live() -> tuple[str, bool, str]:
    """④ M5 검수큐 라이브: HTTP 200 + JSON 파싱."""
    name = "M5 검수큐 라이브"
    try:
        status, body = _http_get(LIVE_REVIEW_URL)
        if status != 200:
            return name, False, f"라이브 HTTP {status} — 검수큐 발행경로 끊김"
        d = json.loads(body)
        n = len(d) if hasattr(d, "__len__") else "?"
        return name, True, f"HTTP 200 · {n}건 파싱 OK"
    except urllib.error.HTTPError as e:
        return name, False, f"라이브 HTTP {e.code} — 검수큐 발행경로 끊김"
    except Exception as e:
        return name, False, f"점검 실패({type(e).__name__}): {str(e)[:80]}"


def check_unpushed() -> tuple[str, bool, str]:
    """⑤ 미푸시 커밋: origin/master..HEAD == 0."""
    name = "미푸시 커밋"
    try:
        r = subprocess.run(
            ["git", "rev-list", f"{REMOTE}/{BRANCH}..HEAD", "--count"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 0:
            return name, False, "확인 불가(원격 ref 없음/네트워크)"
        n = int((r.stdout or "0").strip() or "0")
        if n == 0:
            return name, True, "없음 — 로컬=origin/master 동기화"
        return name, False, f"{n}건 미푸시 — 라이브 stale 위험, 즉시 push 필요"
    except Exception as e:
        return name, False, f"점검 실패({type(e).__name__}): {str(e)[:80]}"


def check_bridges() -> list[tuple[str, bool, str]]:
    """모든 연동 다리를 점검해 [(이름, ok, 상세)] 반환. 절대 예외로 죽지 않음."""
    checks = (
        check_queue_live,
        check_queue_mirror,
        check_sheet_gas,
        check_review_live,
        check_unpushed,
    )
    results: list[tuple[str, bool, str]] = []
    for fn in checks:
        try:
            results.append(fn())
        except Exception as e:  # 최후 방어 — 어떤 점검도 전체를 죽이지 못함
            results.append((fn.__name__, False, f"치명 예외({type(e).__name__})"))
    return results


if __name__ == "__main__":
    import io
    import sys

    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )
    rows = check_bridges()
    ok_n = sum(1 for _, ok, _ in rows if ok)
    print(f"연동 다리 {ok_n}/{len(rows)} ✅")
    for nm, ok, detail in rows:
        print(f"  {'✅' if ok else '⚠️'} {nm}: {detail}")
    sys.exit(0 if ok_n == len(rows) else 1)
