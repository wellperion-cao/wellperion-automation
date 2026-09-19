#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""배포 직후 화면 자동 검수 관문 (배 2851 · 웰리 요청 · 시토 소관).

왜 있나
    화면을 저장·배포한 뒤 "열어 보면 바로 아는 흠"(로그인 벽·깨진 css/js·빈 화면·명암 부족)을
    GM 이 직접 발견하기 전에 기계가 먼저 잡는다. 잡히면 그 저장을 한 C-Level 에게 배로
    되돌린다(GM 방 금지) — coo_page_guard.py 와 같은 사상, 다른 시점(정기 순회가 아니라
    "방금 배포된 커밋" 단위)·다른 관문(safe_commit 이 push 직후 호출).

쓰는 법
    python scripts/post_deploy_check.py [커밋해시]   # 기본 HEAD
    python scripts/post_deploy_check.py <sha> --dry-run   # 되돌림 명령 출력만, 실제 배 안 띄움
    python scripts/post_deploy_check.py --selfcheck        # 가짜 데이터로 판정 로직만 검증

무엇을 보나 (한 화면당)
    ① 문서 상태코드 200(로그인 벽으로 튕기면 실패)
    ② 그 페이지가 요청한 같은 도메인 css/js 중 4xx
    ③ 로드 완료 뒤 body 보이는 글자 수 < 20(빈 화면)
    ④ 명암비 4.5 미만(WCAG) 글자 요소 수 — design_audit.py 와 같은 방식의 축약판
       (design_audit 자체는 로그인 쿠키 없이 도는 독립 도구라 로그인 벽 뒤 화면을 못 연다 —
       여기서는 이미 인증된 같은 페이지에서 바로 잰다)

실패하면 커밋 제목(`push_lock.requester_from_message`)으로 요청 역할을 읽어
scripts/queue_dispatch.py 로 배를 띄운다. 같은 파일·같은 항목은 6시간에 1번만 되돌린다
(status/post_deploy_check.json 이력으로 판단). 텔레그램 GM 방으로는 절대 보내지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE_PREFIX = "3. 웰페리온 가이드/"
LIVE_BASE = "https://erp.wellperion.com/"
OUT = ROOT / "status" / "post_deploy_check.json"
KST = timezone(timedelta(hours=9))
_NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
_GIT = ["git", "-c", "core.quotepath=false"]  # 한글 경로가 \355\201.. 로 인용되지 않게

sys.path.insert(0, str(ROOT / "scripts"))
import push_lock  # noqa: E402

_WAIT_SEC = int(os.environ.get("POST_DEPLOY_WAIT_SEC", "90"))  # 서버 매분 pull 반영 대기
_THROTTLE_HOURS = 6
_HISTORY_CAP = 200

# 명암비 4.5:1(WCAG) — design_audit.py JS 의 같은 계산을 축약(로그인 쿠키 있는 이 페이지에서 바로 잰다).
CONTRAST_JS = r"""
(() => {
  const lum = c => { const m = c.match(/\d+(\.\d+)?/g); if (!m) return null;
    const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); };
    return .2126 * f(+m[0]) + .7152 * f(+m[1]) + .0722 * f(+m[2]); };
  const bgOf = el => { while (el) { const cs = getComputedStyle(el); const c = cs.backgroundColor;
    if (c && !/rgba\(\s*\d+,\s*\d+,\s*\d+,\s*0\s*\)/.test(c) && c !== 'transparent') return c;
    if (cs.backgroundImage !== 'none') return null;
    el = el.parentElement; } return 'rgb(255,255,255)'; };
  let low = 0;
  document.querySelectorAll('p,a,span,li,h1,h2,h3,h4,button,label,td,th,div').forEach(e => {
    const r = e.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return;
    const own = [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!own) return;
    const cs = getComputedStyle(e);
    if (+cs.opacity === 0) return;
    const bg = bgOf(e); if (!bg) return;
    const L1 = lum(cs.color), L2 = lum(bg);
    if (L1 == null || L2 == null) return;
    const ratio = (Math.max(L1, L2) + .05) / (Math.min(L1, L2) + .05);
    const fs = parseFloat(cs.fontSize);
    const big = fs >= 24 || (fs >= 18.66 && +cs.fontWeight >= 700);
    if (ratio < (big ? 3 : 4.5)) low++;
  });
  return low;
})()
"""


def _git_out(args: list[str]) -> str:
    r = subprocess.run(_GIT + args, cwd=str(ROOT), capture_output=True, text=True,
                        encoding="utf-8", errors="replace", **_NOWIN)
    return r.stdout


def changed_html_files(sha: str) -> list[str]:
    """그 커밋이 바꾼(추가·수정) 「3. 웰페리온 가이드/**.html」 목록. 삭제·조각파일(_ 로 시작)은 뺀다."""
    out = _git_out(["diff-tree", "--no-commit-id", "--name-only", "-r", "--diff-filter=ACMR", sha])
    files = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return [f for f in files
            if f.startswith(GUIDE_PREFIX) and f.endswith(".html") and not Path(f).name.startswith("_")]


def url_for(rel: str) -> str:
    """저장소 경로 「3. 웰페리온 가이드/X」 → https://erp.wellperion.com/X"""
    tail = rel[len(GUIDE_PREFIX):]
    return LIVE_BASE + urllib.parse.quote(tail)


def role_for_commit(sha: str) -> str:
    """커밋 제목에서 요청 역할을 읽는다. 못 읽으면 시토(cto) 앞으로(spec 고정)."""
    message = _git_out(["log", "-1", "--format=%B", sha])
    return push_lock.requester_from_message(message, fallback="cto")


def _session_token() -> str:
    sys.path.insert(0, str(ROOT / "scripts" / "collectors"))
    try:
        from ops_shared import _env_line  # type: ignore
        return _env_line("ERP_SESSION_TOKEN")
    except Exception:
        return ""


def judge(metrics: dict) -> list[tuple[str, str]]:
    """(항목명, 실패상세) 목록 — 통과 항목은 안 담는다(순수함수 · 브라우저 없이 테스트 가능)."""
    out: list[tuple[str, str]] = []
    if metrics.get("status") != 200 or "/auth/login" in (metrics.get("final_url") or ""):
        out.append(("상태코드", f"status={metrics.get('status')} final={str(metrics.get('final_url', ''))[:80]}"))
    bad = metrics.get("static_4xx") or []
    if bad:
        out.append(("정적파일404", ", ".join(bad[:5])))
    if (metrics.get("body_text_len") or 0) < 20:
        out.append(("빈화면", f"본문 글자수 {metrics.get('body_text_len')}"))
    if (metrics.get("low_contrast") or 0) > 0:
        out.append(("명암", f"{metrics['low_contrast']}개 요소 4.5:1 미달(추정)"))
    return out


def check_page(context, url: str) -> dict:
    """헤드리스로 한 화면을 열어 4항목 원재료를 잰다(부수효과 있음 — judge() 는 따로 순수하게 둔다)."""
    static_4xx: list[str] = []
    page_netloc = urllib.parse.urlparse(url).netloc
    page = context.new_page()

    def _on_resp(resp):
        u = resp.url
        if (u.endswith(".css") or u.endswith(".js")) and resp.status >= 400 \
                and urllib.parse.urlparse(u).netloc == page_netloc:
            static_4xx.append(f"{resp.status} {u[:90]}")

    page.on("response", _on_resp)
    metrics = {"status": None, "final_url": "", "body_text_len": 0, "low_contrast": 0, "static_4xx": []}
    try:
        resp = page.goto(url, wait_until="load", timeout=45000)
        page.wait_for_timeout(1500)
        metrics["status"] = resp.status if resp else None
        metrics["final_url"] = page.url
        metrics["body_text_len"] = page.evaluate("document.body.innerText.trim().length")
        metrics["low_contrast"] = page.evaluate(CONTRAST_JS)
    except Exception as e:
        metrics["status"] = 0
        metrics["final_url"] = f"열기 실패: {str(e)[:100]}"
    finally:
        metrics["static_4xx"] = static_4xx
        page.close()
    return metrics


def _load_history() -> list[dict]:
    try:
        return json.loads(OUT.read_text(encoding="utf-8")).get("rows", [])
    except Exception:
        return []


def _save_history(rows: list[dict]) -> None:
    rows = rows[-_HISTORY_CAP:]
    OUT.write_text(json.dumps({
        "_doc": "배포 직후 화면 자동 검수 이력(최근 200건) — 시토 소관(배 2851). 만드는 스크립트 = scripts/post_deploy_check.py",
        "updated_at_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S%z"),
        "rows": rows,
    }, ensure_ascii=False, indent=1), encoding="utf-8")


def _recently_dispatched(history: list[dict], file: str, item: str, now: datetime) -> bool:
    cutoff = now - timedelta(hours=_THROTTLE_HOURS)
    for row in history:
        if row.get("file") == file and row.get("item") == item and row.get("dispatched"):
            try:
                ts = datetime.strptime(row["ts"], "%Y-%m-%d %H:%M:%S%z")
            except Exception:
                continue
            if ts >= cutoff:
                return True
    return False


def build_dispatch_cmd(role: str, file: str, item: str, detail: str, url: str) -> list[str]:
    title = f"[자동 검수 실패] {Path(file).name} — {item}"
    note = f"{detail} · {url}"
    return [sys.executable, str(ROOT / "scripts" / "queue_dispatch.py"),
            "--to", role, "--sender", "cto", "--title", title, "--note", note,
            "--next", "고쳐서 다시 저장", "--gm-needed", "no", "--audience", "ai",
            "--reversible", "yes", "--work-type", "update"]


def run(sha: str, dry_run: bool) -> int:
    files = changed_html_files(sha)
    if not files:
        print(f"[검수] {sha[:9]} — 화면(html) 변경 없음. 조용히 종료.")
        return 0
    print(f"[검수] {sha[:9]} — 대상 {len(files)}개: " + ", ".join(Path(f).name for f in files))
    print(f"[검수] 서버 반영 대기 {_WAIT_SEC}초…")
    time.sleep(_WAIT_SEC)

    role = role_for_commit(sha)
    tok = _session_token()

    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    history = _load_history()
    now = datetime.now(KST)
    new_rows: list[dict] = []
    any_fail = False

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1400, "height": 1000}, locale="ko-KR",
                                   timezone_id="Asia/Seoul")
        ctx.add_init_script("try{sessionStorage.setItem('welp_gate_ok','1')}catch(e){}")
        if tok:
            ctx.add_cookies([{"name": "erp_session", "value": tok, "domain": "erp.wellperion.com", "path": "/"}])
        for f in files:
            url = url_for(f)
            metrics = check_page(ctx, url)
            items = judge(metrics)
            ok = not items
            print(("  OK  " if ok else "  걸림 ") + Path(f).name + (f" — {items[0][0]}" if items else ""))
            if ok:
                new_rows.append({"commit": sha[:9], "file": f, "url": url, "item": "", "detail": "",
                                  "passed": True, "dispatched": False,
                                  "ts": now.strftime("%Y-%m-%d %H:%M:%S%z")})
                continue
            any_fail = True
            for item, detail in items:
                dispatched = False
                if _recently_dispatched(history + new_rows, f, item, now):
                    print(f"    (6시간 내 이미 되돌림 — 재발송 안 함) {item}: {detail[:80]}")
                else:
                    cmd = build_dispatch_cmd(role, f, item, detail, url)
                    if dry_run:
                        print("    [dry-run 되돌림 명령] " + " ".join(cmd))
                    else:
                        subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                                        encoding="utf-8", errors="replace", timeout=30, **_NOWIN)
                        dispatched = True
                new_rows.append({"commit": sha[:9], "file": f, "url": url, "item": item,
                                  "detail": detail[:200], "passed": False, "dispatched": dispatched,
                                  "ts": now.strftime("%Y-%m-%d %H:%M:%S%z")})
        browser.close()

    _save_history(history + new_rows)
    return 1 if any_fail else 0


def _selfcheck() -> None:
    """가짜 결과로 판정·되돌림 명령 조립·중복 억제만 검증 — 실제 dispatch·브라우저 없음."""
    ok_metrics = {"status": 200, "final_url": "https://erp.wellperion.com/a.html",
                  "body_text_len": 500, "low_contrast": 0, "static_4xx": []}
    assert judge(ok_metrics) == [], "통과해야 할 값이 걸렸다"

    bad_metrics = {"status": 200, "final_url": "https://erp.wellperion.com/auth/login?next=/a.html",
                   "body_text_len": 3, "low_contrast": 2,
                   "static_4xx": ["404 https://erp.wellperion.com/x.css"]}
    names = [n for n, _ in judge(bad_metrics)]
    assert set(names) == {"상태코드", "정적파일404", "빈화면", "명암"}, names

    assert push_lock.requester_from_message("[시토] fix(cto): 화면 수정", fallback="cto") == "cto"
    assert push_lock.requester_from_message("이상한 제목", fallback="cto") == "cto"

    cmd = build_dispatch_cmd("cmo", "3. 웰페리온 가이드/x.html", "빈화면", "본문 글자수 3",
                             "https://erp.wellperion.com/x.html")
    assert cmd[cmd.index("--to") + 1] == "cmo"
    assert "빈화면" in cmd[cmd.index("--title") + 1]
    assert "queue_dispatch.py" in cmd[1]

    now = datetime.now(KST)
    old_row = {"file": "a.html", "item": "빈화면", "dispatched": True,
               "ts": (now - timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S%z")}
    recent_row = {"file": "a.html", "item": "빈화면", "dispatched": True,
                  "ts": (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S%z")}
    assert _recently_dispatched([old_row], "a.html", "빈화면", now) is False, "6시간 지난 것도 막혔다"
    assert _recently_dispatched([recent_row], "a.html", "빈화면", now) is True, "6시간 내인데 안 막혔다"
    assert _recently_dispatched([recent_row], "b.html", "빈화면", now) is False, "다른 파일까지 막혔다"

    print("[selfcheck] post_deploy_check 판정·되돌림조립·중복억제 OK")


def main() -> int:
    ap = argparse.ArgumentParser(description="배포 직후 화면 자동 검수 관문")
    ap.add_argument("sha", nargs="?", default="HEAD", help="검사할 커밋(기본 HEAD)")
    ap.add_argument("--dry-run", action="store_true", help="되돌림 명령 출력만, 실제 배 안 띄움")
    ap.add_argument("--selfcheck", action="store_true", help="가짜 데이터로 로직만 검증")
    args = ap.parse_args()

    if args.selfcheck:
        _selfcheck()
        return 0

    sha = _git_out(["rev-parse", args.sha]).strip()
    if not sha:
        print(f"[검수] 커밋을 못 찾음: {args.sha}")
        return 1
    return run(sha, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
