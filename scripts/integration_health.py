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
import re
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
QUEUE_ARCHIVE = ROOT / "status" / "_queue_archive.json"
PAGE_SCORE = ROOT / "status" / "page_score.json"

_SHIP_NO_RE = re.compile(r"배(\d+)")
# 이미 정정된 note 는 걸러줄 신호(문구는 GM 지정)
_CORRECTION_SIGNALS = ("종결", "해소", "사실 아님", "정상 가동", "확인 완료")

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


# 자가복구 창(초) — 동시 커밋(여러 C-Level·auto-log·ERP 발행)이 같은 순간에 몰리면 post-commit
# push 가 락·경합으로 잠깐 밀린다. 다음 커밋의 push 또는 5분 스위퍼가 곧 비우므로, 이 창 안의
# 순간 미푸시는 '정체'가 아니라 '진행 중'이다. 5분 스위퍼 주기 + 여유.
PUSH_SETTLE_SEC = 600


def _unpushed_settle_age() -> int | None:
    """아직 못 올린 커밋 중 **가장 오래된 것**의 나이(초). 미푸시 0이거나 확인 불가면 None.

    ★이 계산은 여기 한 곳에만 둔다(약속 L01). 예전엔 ⑤ 미푸시 점검 안에만 있어서,
    같은 사실을 보는 ① G1 큐 라이브 점검은 창 없이 즉시 경보했다 — 두 점검이 같은 상태를
    다르게 판정해 확인방에 오탐이 반복됐다(2026-07-31 GM 지적).
    """
    try:
        r = subprocess.run(
            ["git", "log", f"{REMOTE}/{BRANCH}..HEAD", "--reverse", "--format=%ct"],
            cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        if r.returncode != 0 or not (r.stdout or "").strip():
            return None
        import time
        oldest = int(r.stdout.strip().splitlines()[0])
        return int(time.time() - oldest)
    except Exception:
        return None


def _unpushed_count() -> int:
    """origin/master..HEAD 커밋 수. 확인 불가 시 -1."""
    try:
        r = subprocess.run(
            ["git", "rev-list", f"{REMOTE}/{BRANCH}..HEAD", "--count"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if r.returncode != 0:
            return -1
        return int((r.stdout or "0").strip() or "0")
    except Exception:
        return -1


def check_queue_live() -> tuple[str, bool, str]:
    """① G1 큐 라이브: HTTP 200 + JSON + 라이브 active == 로컬 active.

    건수 불일치 + 미푸시=0 + HTTP 200 → CDN 캐시 지연으로 분류(경보 없음, INC-007 후속).
    진짜 끊김 = (미푸시>0) OR (HTTP non-200).
    """
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
            # 미푸시 여부로 진짜 끊김 vs CDN 캐시 지연 구분 (INC-007 후속)
            unpushed = _unpushed_count()
            if unpushed > 0:
                # ★2026-07-31 시토(GM "AI진행현황에 이게 너무 많이 뜬다") — 자가복구 창을 여기에도 적용.
                #   왜: 아래 ⑤ 미푸시 커밋 점검은 이미 600초 창을 두고 "그 안의 순간 미푸시는 정상"으로
                #   보는데, 이 ① 점검만 창 없이 **미푸시가 1건이라도 보이면 즉시 경보**했다. 커밋은
                #   몇 초 뒤 스스로 push 되므로, 그 순간을 스쳐 본 점검이 확인방에 '다리 끊김'을
                #   띄우고 정작 GM 이 열어볼 땐 이미 0건이다(실측 2026-07-31 11:27 경보 → 확인 시 0건).
                #   같은 판정을 두 곳이 다르게 하고 있었으므로 창 계산은 한 곳(_unpushed_settle_age)만 쓴다.
                age = _unpushed_settle_age()
                if age is not None and age < PUSH_SETTLE_SEC:
                    return (
                        name,
                        True,
                        f"동기화 진행 중 — 라이브 {live_active}건 ≠ 로컬 {local_active}건"
                        f" (미푸시 {unpushed}건 · {age}s, 자가복구 창 내) — 정상",
                    )
                return (
                    name,
                    False,
                    f"건수 불일치 — 라이브 {live_active}건 ≠ 로컬 {local_active}건"
                    f" (미푸시 {unpushed}건 · 즉시 push 필요)",
                )
            # 미푸시=0 + HTTP 200 = CDN 반영 지연(캐시). 경보 안 띄움.
            return (
                name,
                True,
                f"CDN 캐시 지연 — 라이브 {live_active}건 ≠ 로컬 {local_active}건"
                f" (미푸시 0 · Pages 반영 대기 중, 정상)",
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
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if r.returncode != 0:
            return name, False, "확인 불가(원격 ref 없음/네트워크)"
        n = int((r.stdout or "0").strip() or "0")
        if n == 0:
            return name, True, "없음 — 로컬=origin/master 동기화"
        # 자가복구 창 — 판정은 _unpushed_settle_age() 한 곳만 쓴다(위 ① 점검과 공용 · 약속 L01).
        age = _unpushed_settle_age()
        if age is not None:
            if age < PUSH_SETTLE_SEC:
                return name, True, f"{n}건 동기화 진행 중({age}s, 자가복구 창 내) — 정상"
            return name, False, f"{n}건 미푸시 {age // 60}분+ 정체 — 스위퍼 미작동 의심, 즉시 push 필요"
        return name, False, f"{n}건 미푸시 — 라이브 stale 위험, 즉시 push 필요"
    except Exception as e:
        return name, False, f"점검 실패({type(e).__name__}): {str(e)[:80]}"


def check_kpi_freshness() -> tuple[str, bool, str]:
    """⑥ KPI 집계 신선도: kpi_values.json generated_at 이 25시간 이내(스케줄=07:50·21:00 일 2회,
    최대 간격 약 13.2h + 1회 결측 여유분).
    ⚠️ 배1307 재발방지(INC): kpi_collector 가 6일간 조용히 timeout 실패(scheduler.log ERROR만 남고
    kpi_values.json 은 갱신 없이 그대로 방치)해도 이 체크가 없으면 아무도 몰랐다 — 측정의 측정.
    """
    name = "KPI 집계 신선도"
    path = ROOT / "status" / "kpi_values.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ts = data.get("generated_at")
        if not ts:
            return name, False, "generated_at 없음(형식 이상)"
        from datetime import datetime
        gen = datetime.fromisoformat(ts)
        age_h = (datetime.now(gen.tzinfo) - gen).total_seconds() / 3600
        if age_h <= 25:
            return name, True, f"{age_h:.1f}h 전 갱신 — 정상"
        return name, False, f"{age_h:.1f}h 전 갱신 — 25h 초과(kpi_collector 결측/timeout 의심)"
    except Exception as e:
        return name, False, f"점검 실패({type(e).__name__}): {str(e)[:80]}"


def check_page_score_stale_ship_refs() -> tuple[str, bool, str]:
    """⑦ 업무 SSOT 배번호 신선도: page_score.json 각 항목 note 가 인용한 '배NNN'이 이미 끝난
    배(_queue_archive.json 등재 또는 _queue.json 에서 status=DONE)인데 정정 신호
    (종결/해소/사실 아님/정상 가동/확인 완료) 없이 남아 있으면 걸린다.
    (2026-08-18, '업무 SSOT 채움 보드'가 종결된 배617을 4일간 미해결로 인용 방치한 사고 후속.)
    """
    name = "업무 SSOT 배번호 신선도"
    try:
        score = json.loads(PAGE_SCORE.read_text(encoding="utf-8"))
        pages = score.get("pages") if isinstance(score, dict) else None
        if not isinstance(pages, list):
            return name, False, "page_score.json 형식 이상(pages 배열 없음)"

        queue = json.loads(LOCAL_QUEUE.read_text(encoding="utf-8"))
        archive = json.loads(QUEUE_ARCHIVE.read_text(encoding="utf-8"))
        queue_status = {
            x["short_no"]: x.get("status")
            for x in queue
            if isinstance(x, dict) and isinstance(x.get("short_no"), int)
        }
        archived_nos = {
            x["short_no"]
            for x in archive
            if isinstance(x, dict) and isinstance(x.get("short_no"), int)
        }

        stale = []
        for p in pages:
            if not isinstance(p, dict):
                continue
            note = p.get("note") or ""
            if any(sig in note for sig in _CORRECTION_SIGNALS):
                continue  # 이미 정정됨 — 통과
            for no_s in _SHIP_NO_RE.findall(note):
                no = int(no_s)
                if no in archived_nos or queue_status.get(no) == "DONE":
                    stale.append(f"{p.get('name', '?')}·배{no}")

        if stale:
            return name, False, "끝난 배 인용(정정 신호 없음) — " + ", ".join(stale)
        return name, True, f"{len(pages)}개 화면 note 배번호 정상"
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
        check_kpi_freshness,
        check_page_score_stale_ship_refs,
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
