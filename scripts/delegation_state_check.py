# scripts/delegation_state_check.py
# 웰리(AI CEO) 위임 전 상태확인 게이트 — "아직 안 됐다"고 담당을 헛돌리기 전에
# 로컬 HEAD·origin·라이브(배포된 실제 파일)를 한 번에 대조해 "지금 진짜 상태"를 보여준다.
#
# 배경(2026-07-20): 웰리가 담당 커밋·배포 직전 시점에 확인해 "아직 안 됐다"고 오판,
# 담당을 3회 헛돌린 사고. 원인은 "커밋됨/푸시됨/라이브 반영됨"을 구분하지 못한 것.
# GitHub Pages 배포는 지연이 있어 이 3단이 동시에 일치하지 않는 게 정상 — 어느 단계에
# 있는지를 기계로 판정해 보여주면, 웰리가 근거 없이 "안 됐다"고 단정하는 걸 막는다.
#
# 두 번째 사고(유휴 알림→중복 배정 3회)는 dup 서브커맨드로 같은 파일에서 함께 막는다:
# 새 담당을 붙이기 전 status/_queue.json에 이미 PENDING·IN_PROGRESS인 같은 건이
# 있는지 기계로 대조한다.
#
# 사용법:
#   python scripts/delegation_state_check.py state --path <레포상대경로> [--string "찾을 문자열"] [--live <URL>] [--branch master]
#   python scripts/delegation_state_check.py dup --keyword "검색어" [--status PENDING,IN_PROGRESS,STANDBY]
#
# 예시:
#   python scripts/delegation_state_check.py state --path "3. 웰페리온 가이드/cmo/en/topstrip.html" \
#       --string "top-strip-v2" --live "https://wellperion-cao.github.io/wellperion-automation/..."
#   python scripts/delegation_state_check.py dup --keyword "WPML"
#
# 종료코드:
#   state: --string 지정 시 = 요청한 모든 계층(HEAD·도달 가능한 origin·지정된 live)에
#          문자열이 있으면 0, 하나라도 없으면 1(=아직 전 계층 반영 안 됨). --string 없으면
#          정보 출력만 하고 항상 0.
#   dup:   기존 배정(PENDING·IN_PROGRESS 등) 매치가 있으면 1(=중복 배정 위험), 없으면 0.

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
QUEUE_PATH = ROOT / "status" / "_queue.json"
FETCH_TIMEOUT = 15
LIVE_TIMEOUT = 20

OK, NG, WARN = "✅", "❌", "⚠️"


def _run(args: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _worktree_status(path: str) -> tuple[bool, str]:
    """작업트리(디스크) 상태 — 커밋 안 된 변경이 있는지. (dirty, porcelain 원문)"""
    r = _run(["status", "--porcelain", "--", path])
    out = (r.stdout or "").strip()
    return bool(out), out


def _head_info(path: str) -> tuple[bool, str, str]:
    """로컬 HEAD에 해당 경로가 있는지 + 마지막 커밋 요약. (exists, hash_date_msg, content)"""
    exists = _run(["cat-file", "-e", f"HEAD:{path}"]).returncode == 0
    if not exists:
        return False, "(HEAD에 파일 없음)", ""
    log = _run(["log", "-1", "--format=%h|%ci|%s", "--", path])
    summary = (log.stdout or "").strip() or "(커밋 이력 조회 실패)"
    show = _run(["show", f"HEAD:{path}"])
    content = show.stdout if show.returncode == 0 else ""
    return True, summary, content


def _fetch_origin(branch: str) -> bool:
    try:
        r = _run(["fetch", "origin", branch, "--quiet"], timeout=FETCH_TIMEOUT)
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def _origin_info(path: str, branch: str, fetched: bool) -> dict:
    """origin 상태 — ahead/behind 커밋수 + 해당 경로 내용. fetch 실패 시 확인불가로 표시."""
    if not fetched:
        return {"reachable": False}
    ahead = _run(["rev-list", f"origin/{branch}..HEAD", "--count"])
    behind = _run(["rev-list", f"HEAD..origin/{branch}", "--count"])
    exists = _run(["cat-file", "-e", f"origin/{branch}:{path}"]).returncode == 0
    content = ""
    summary = "(origin에 파일 없음)"
    if exists:
        show = _run(["show", f"origin/{branch}:{path}"])
        content = show.stdout if show.returncode == 0 else ""
        log = _run(["log", "-1", "--format=%h|%ci|%s", f"origin/{branch}", "--", path])
        summary = (log.stdout or "").strip() or "(커밋 이력 조회 실패)"
    return {
        "reachable": True,
        "ahead": int((ahead.stdout or "0").strip() or 0),
        "behind": int((behind.stdout or "0").strip() or 0),
        "exists": exists,
        "summary": summary,
        "content": content,
    }


def _nfc_url(url: str) -> str:
    """한글 경로 NFD→NFC 정규화 (GitHub Pages 가짜404 방지, reference_pages_url_no_guide_prefix)."""
    parsed = urllib.parse.urlparse(url)
    path_decoded = urllib.parse.unquote(parsed.path)
    path_nfc = unicodedata.normalize("NFC", path_decoded)
    path_encoded = urllib.parse.quote(path_nfc, safe="/")
    return urllib.parse.urlunparse(parsed._replace(path=path_encoded))


def _live_fetch(url: str) -> dict:
    """라이브 URL 캐시버스팅 GET (stdlib만 사용 — playwright 불필요한 가벼운 상태확인).
    주의: GitHub Pages CDN은 쿼리스트링으로 캐시가 안 깨진다(경로 기준 캐싱) — 아래 _cb
    파라미터는 프록시·중간 캐시 대비용일 뿐, Cache-Control 헤더가 실제 방어선이다."""
    url = _nfc_url(url)
    ts = int(datetime.now().timestamp())
    sep = "&" if "?" in url else "?"
    busted = f"{url}{sep}_cb={ts}"
    req = urllib.request.Request(
        busted,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "User-Agent": "Mozilla/5.0 (delegation_state_check)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=LIVE_TIMEOUT) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
            return {"reachable": True, "status": status, "content": body}
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return {"reachable": True, "status": e.code, "content": body}
    except Exception as e:
        return {"reachable": False, "error": str(e)}


def cmd_state(args: argparse.Namespace) -> int:
    path = args.path
    string = args.string
    branch = args.branch

    dirty, raw_status = _worktree_status(path)
    head_exists, head_summary, head_content = _head_info(path)
    fetched = _fetch_origin(branch)
    origin = _origin_info(path, branch, fetched)
    live = _live_fetch(args.live) if args.live else None

    print(f"🔍 위임 상태확인 — {path}")
    if string:
        print(f"   대조 문자열: \"{string}\"")
    print()

    rows: list[tuple[str, str, str]] = []

    # 1) 작업트리(디스크)
    wt_icon = WARN if dirty else OK
    wt_note = "커밋 안 된 변경 있음(디스크≠HEAD)" if dirty else "클린(디스크=HEAD)"
    rows.append(("작업트리(디스크)", f"{wt_icon} {wt_note}", raw_status[:200] if dirty else "-"))

    # 2) 로컬 HEAD(커밋됨)
    if not head_exists:
        rows.append(("로컬 HEAD(커밋됨)", f"{NG} 파일 없음", head_summary))
        head_has_string = False
    else:
        if string is not None:
            head_has_string = string in head_content
            icon = OK if head_has_string else NG
            note = f"{icon} 문자열 {'있음' if head_has_string else '없음'}"
        else:
            head_has_string = None
            note = f"{OK} 커밋됨"
        rows.append(("로컬 HEAD(커밋됨)", note, head_summary))

    # 3) origin(푸시됨)
    if not origin.get("reachable"):
        rows.append(("origin(푸시됨)", f"{WARN} fetch 실패 — 확인불가", "네트워크·인증 확인 필요"))
        origin_has_string = None
    else:
        ahead, behind = origin["ahead"], origin["behind"]
        sync_note = f"ahead {ahead} / behind {behind}"
        if not origin.get("exists"):
            rows.append(("origin(푸시됨)", f"{NG} 파일 없음 ({sync_note})", origin["summary"]))
            origin_has_string = False
        else:
            if string is not None:
                origin_has_string = string in origin["content"]
                icon = OK if origin_has_string else NG
                note = f"{icon} 문자열 {'있음' if origin_has_string else '없음'} ({sync_note})"
            else:
                origin_has_string = None
                icon = OK if ahead == 0 else WARN
                note = f"{icon} {sync_note}"
            rows.append(("origin(푸시됨)", note, origin["summary"]))

    # 4) 라이브(배포 반영)
    if live is None:
        rows.append(("라이브(배포반영)", f"{WARN} --live 미지정 — 확인 안 함", "-"))
        live_has_string = None
    elif not live.get("reachable"):
        rows.append(("라이브(배포반영)", f"{NG} 도달 실패", live.get("error", "")))
        live_has_string = False
    else:
        status = live["status"]
        reached = status < 400
        if string is not None:
            live_has_string = reached and (string in live["content"])
            icon = OK if live_has_string else NG
            note = f"{icon} 문자열 {'있음' if live_has_string else '없음'} (HTTP {status})"
        else:
            live_has_string = None
            icon = OK if reached else NG
            note = f"{icon} HTTP {status}"
        rows.append(("라이브(배포반영)", note, args.live))

    for label, note, detail in rows:
        print(f"  [{label}]")
        print(f"    {note}")
        if detail and detail != "-":
            print(f"    └ {detail}")
    print()

    # 종합 판정 — string 지정 시에만 pass/fail 게이트로 쓴다.
    if string is not None:
        checked = [v for v in (head_has_string, origin_has_string, live_has_string) if v is not None]
        all_ok = bool(checked) and all(checked)
        if all_ok:
            print(f"{OK} 결론: 확인된 모든 계층에 반영됨 — '아직 안 됐다' 판단 근거 없음")
            return 0
        else:
            missing = []
            if head_has_string is False:
                missing.append("로컬 HEAD")
            if origin_has_string is False:
                missing.append("origin")
            if live_has_string is False:
                missing.append("라이브")
            print(f"{NG} 결론: 미반영 계층 = {', '.join(missing) if missing else '판정 불가'} — 이 계층만 콕 집어 담당에게 재확인 요청할 것(전체 재작업 지시 금지)")
            return 1
    else:
        print("ℹ️ --string 미지정 — 정보 출력만(게이트 판정 없음)")
        return 0


def _queue_items() -> list[dict]:
    if not QUEUE_PATH.exists():
        return []
    with open(QUEUE_PATH, encoding="utf-8") as f:
        return json.load(f)


def cmd_dup(args: argparse.Namespace) -> int:
    keyword = args.keyword.strip()
    statuses = {s.strip().upper() for s in args.status.split(",") if s.strip()}
    items = _queue_items()

    kw_low = keyword.lower()
    matches = []
    for it in items:
        if (it.get("status") or "").upper() not in statuses:
            continue
        haystack = " ".join(
            str(it.get(k, "")) for k in ("title", "note", "artifact", "next")
        ).lower()
        if kw_low in haystack:
            matches.append(it)

    print(f"🔍 중복 배정 확인 — 키워드 \"{keyword}\" (대상 상태: {', '.join(sorted(statuses))})")
    print()

    if not matches:
        print(f"{OK} 매치 없음 — 신규 배정해도 안전(기존 담당 없음)")
        return 0

    print(f"{WARN} 기존 배정 {len(matches)}건 발견 — 신규 배정 전 아래를 먼저 확인할 것:")
    print()
    for it in matches:
        ship = it.get("ship_no", "-")
        clevel = it.get("clevel", "-")
        status = it.get("status", "-")
        title = it.get("title", "-")
        print(f"  ・ [{clevel} 배{ship}] {status} — {title}")
        note = it.get("note") or ""
        if note:
            print(f"    └ {note[:200]}{'...' if len(note) > 200 else ''}")
    print()
    print("👉 위 배가 이미 이 대상을 다루고 있다면 새 담당을 붙이지 말고 기존 배에 이어서 지시할 것(배 중복생성 금지).")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="위임 전 상태확인 게이트 — 커밋됨/푸시됨/라이브반영 구분 + 중복배정 확인"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_state = sub.add_parser("state", help="파일/문자열 기준 로컬HEAD·origin·라이브 3계층 대조")
    p_state.add_argument("--path", required=True, help="레포 상대 경로 (예: status/_queue.json)")
    p_state.add_argument("--string", default=None, help="각 계층에서 찾을 문자열(선택)")
    p_state.add_argument("--live", default=None, help="라이브 URL(선택, 캐시버스팅 GET)")
    p_state.add_argument("--branch", default="master", help="origin 브랜치(기본 master)")
    p_state.set_defaults(func=cmd_state)

    p_dup = sub.add_parser("dup", help="status/_queue.json에서 같은 대상 기존 배정 검색")
    p_dup.add_argument("--keyword", required=True, help="검색어(제목·note·artifact·next 대상)")
    p_dup.add_argument(
        "--status", default="PENDING,IN_PROGRESS,STANDBY", help="검사할 상태 목록(콤마구분)"
    )
    p_dup.set_defaults(func=cmd_dup)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
