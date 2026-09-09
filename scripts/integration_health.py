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

# ── 캐논 상수 (라이브 판정은 여기 1곳에만) ─────────────────────────────────
# 배1115 ④(2026-09-08): GitHub Pages 를 비공개로 돌리면서 무인증 GET 판정이 불가능해졌다.
# ERP 서버(erp.wellperion.com)는 HTTP 가 로그인 벽(auth_request)이라 여전히 GET 은 못 쓰지만,
# ssh 로는 서버가 매분 git pull 하는 저장소 사본(/srv/erp/www)을 그대로 볼 수 있다 — 이걸로 대체.
SSH_KEY = str(Path.home() / ".aws" / "wellperion-sito.pem")
SSH_HOST = "15.164.151.105"
SSH_USER = "ec2-user"
REMOTE_REPO = "/srv/erp/www"
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


def _ssh_run(remote_cmd: str, timeout: int = 25) -> tuple[int, str, str]:
    """ERP 서버에서 명령 실행 → (returncode, stdout, stderr). 예외도 rc=-1 로 흡수."""
    try:
        r = subprocess.run(
            ["ssh", "-i", SSH_KEY, "-o", "ConnectTimeout=15", "-o", "StrictHostKeyChecking=no",
             f"{SSH_USER}@{SSH_HOST}", remote_cmd],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
        return r.returncode, r.stdout or "", r.stderr or ""
    except Exception as e:
        return -1, "", f"{type(e).__name__}: {str(e)[:80]}"


def _local_master_head() -> tuple[str | None, int]:
    """로컬 origin/master 의 (sha, 커밋시각epoch). 실패 시 (None, 0)."""
    try:
        r1 = subprocess.run(["git", "rev-parse", f"{REMOTE}/{BRANCH}"], cwd=str(ROOT),
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
        r2 = subprocess.run(["git", "log", "-1", "--format=%ct", f"{REMOTE}/{BRANCH}"], cwd=str(ROOT),
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
        if r1.returncode != 0 or r2.returncode != 0:
            return None, 0
        return r1.stdout.strip(), int(r2.stdout.strip())
    except Exception:
        return None, 0


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
    """① G1 큐 라이브: ERP 서버(erp.wellperion.com) git 사본을 ssh 로 직접 대조(배1115 ④).

    서버 HEAD == 로컬 origin/master(발행 도달) 이거나, 뒤처짐이 pull 주기(1분) 감안 10분
    이내면 정상. 그 안에서는 active 건수 불일치도 '아직 안 당겨옴'으로 보고 경보하지 않는다.
    ssh 자체가 안 되면(네트워크/키) '끊김'으로 단정하지 않고 '확인 불가'로만 분류한다.
    """
    name = "G1 큐 라이브"
    rc, out, err = _ssh_run(
        f"cd {REMOTE_REPO} && git rev-parse HEAD && git log -1 --format=%ct HEAD "
        f"&& git status --short | wc -l && cat status/_queue.json"
    )
    if rc != 0:
        return name, True, f"라이브 확인 불가(ssh 실패: {(err or str(rc)).strip()[:80]})"
    lines = out.splitlines()
    if len(lines) < 4:
        return name, True, f"라이브 확인 불가(서버 출력 형식 이상: {len(lines)}줄)"
    server_head, server_ts_s, dirty_s = lines[0].strip(), lines[1].strip(), lines[2].strip()
    try:
        server_ts = int(server_ts_s)
    except ValueError:
        return name, True, "라이브 확인 불가(서버 커밋시각 파싱 실패)"
    dirty_n = int(dirty_s) if dirty_s.isdigit() else -1
    try:
        server_active = _active_count(json.loads("\n".join(lines[3:])))
    except Exception:
        server_active = -1
    local_active = _local_active_count()
    local_master, local_ts = _local_master_head()
    if local_master is None:
        return name, True, "라이브 확인 불가(로컬 origin/master 조회 실패)"

    if server_head == local_master:
        head_ok, lag_txt = True, "HEAD 일치(발행 도달)"
    else:
        lag = max(0, local_ts - server_ts)
        if lag <= PUSH_SETTLE_SEC:
            head_ok, lag_txt = True, f"HEAD {lag}s 뒤처짐(허용 {PUSH_SETTLE_SEC // 60}분 내)"
        else:
            head_ok, lag_txt = False, f"HEAD {lag // 60}분 뒤처짐(pull 정체 의심)"

    if not head_ok or server_active < 0 or local_active < 0:
        ok = False
    elif server_head == local_master:
        ok = server_active == local_active
    else:
        ok = True  # 아직 안 당겨온 지연 창 안 — active 불일치는 예상됨(경보 안 함)
    dirty_txt = f"더티 {dirty_n}건" if dirty_n >= 0 else "더티 확인 실패"
    detail = f"{lag_txt} · {dirty_txt} · 서버 active {server_active}건/로컬 {local_active}건"
    return name, ok, detail


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
    """④ M5 검수큐 라이브: ERP 서버 사본을 ssh 로 직접 파싱(배1115 ④).

    ssh 자체가 안 되면(네트워크/키) '끊김'으로 단정하지 않고 '확인 불가'로만 분류한다.
    """
    name = "M5 검수큐 라이브"
    rc, out, err = _ssh_run(f"cat {REMOTE_REPO}/cmo/review/review_queue.json")
    if rc != 0:
        return name, True, f"라이브 확인 불가(ssh 실패: {(err or str(rc)).strip()[:80]})"
    try:
        d = json.loads(out)
    except Exception as e:
        return name, False, f"서버 사본 파싱 실패({type(e).__name__})"
    n = len(d) if hasattr(d, "__len__") else "?"
    return name, True, f"서버 사본 파싱 OK · {n}건"


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


def check_server_pushback() -> tuple[str, bool, str]:
    """서버 되밀기(pushback): 서버 원장에만 적힌 행이 시트로 못 돌아간 건수.

    왜 보나 — 원본 스위치가 server 인 영역은 화면이 서버에만 쓰고, 시트는 pushback(1분 cron)이
    되민다. 되밀기가 멈추면 시트에서 그 데이터가 영영 안 보이는데 서버 상태값은 전부 정상이라
    어떤 감시기도 안 잡았다(2026-09-08 실측: health API 안에만 있고 아무도 안 읽음).
    unpushed 는 순간값이라 1분 뒤 0 이 되는 게 정상 — 30건 넘거나 failed 가 있을 때만 경보한다.
    """
    name = "서버 되밀기"
    code, out, err = _ssh_run("curl -s --max-time 10 http://127.0.0.1:8001/api/intake/health")
    if code != 0 or not out.strip():
        return name, True, f"확인 불가(서버 접속 실패) — {(err or '응답 없음')[:60]}"
    try:
        d = json.loads(out)
    except Exception:
        return name, True, "확인 불가(health 응답이 JSON 아님)"
    pb = d.get("pushback") or {}
    unpushed = int(pb.get("unpushed") or 0)
    failed = int(pb.get("failed") or 0)
    last = str(pb.get("last_pushed_at") or "-")
    if failed:
        return name, False, f"되밀기 실패 {failed}건 · 대기 {unpushed}건 — 시트에 안 남는 중(마지막 {last})"
    if unpushed > 30:
        return name, False, f"되밀기 대기 {unpushed}건 정체 — cron 정지 의심(마지막 {last})"
    return name, True, f"대기 {unpushed}건 · 실패 0 (마지막 {last})"


# 서버 크론에 --dry-run 이 붙어 있어도 실제로 일하는 것 = 여기 적은 것뿐. 나머지는 '등록만 되고 아무 일도
# 안 하는 장치'로 본다. 새로 넣을 때는 로그에서 실제 산출물(파일·발신)을 눈으로 확인한 뒤 적는다.
DRYRUN_OK = {
    "ig_reach_collector.py": "--dry-run 인데도 원장을 실제로 쓴다(스크립트마다 뜻이 다름) — 2026-09-09 로그 실측",
}


def check_server_cron_dryrun() -> tuple[str, bool, str]:
    """서버 예약작업이 '등록만 되고 아무 일도 안 하는' 상태인지.

    왜 보나 — 2026-09-07 에 PC 예약작업 5개를 「서버 크론 6개 100% 등록 확인」을 근거로 껐는데,
    그 서버 크론 중 넷이 --dry-run 이라 접수 배선·마케팅 발신·토큰 갱신이 이틀간 아무 일도 안 했다.
    등록됐는지가 아니라 그 일을 실제로 하는지를 세야 한다. 같은 본질이 전날 침묵감시기에서도 났다.
    """
    name = "서버 예약작업 실효"
    code, out, err = _ssh_run("crontab -l 2>/dev/null; sudo grep -h -v '^#' /etc/cron.d/* 2>/dev/null")
    if code != 0 or not out.strip():
        return name, True, f"확인 불가(서버 접속 실패) — {(err or '응답 없음')[:60]}"
    inert = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "--dry-run" not in line:
            continue
        script = next((w.rsplit("/", 1)[-1] for w in line.split() if w.endswith(".py")), line[:40])
        if script not in DRYRUN_OK:
            inert.append(script)
    if inert:
        uniq = sorted(set(inert))
        return name, False, f"--dry-run 으로만 도는 예약작업 {len(uniq)}개 — 등록만 되고 일은 안 한다: {', '.join(uniq)}"
    return name, True, "--dry-run 으로 헛도는 예약작업 없음"


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
        check_server_pushback,
        check_server_cron_dryrun,
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

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = check_bridges()
    ok_n = sum(1 for _, ok, _ in rows if ok)
    print(f"연동 다리 {ok_n}/{len(rows)} ✅")
    for nm, ok, detail in rows:
        print(f"  {'✅' if ok else '⚠️'} {nm}: {detail}")
    sys.exit(0 if ok_n == len(rows) else 1)
