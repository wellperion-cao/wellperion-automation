"""
GEO 측정기 — AI 검색 인용 주 1회 자동 점검 (배971→배1002, GM 지시 2026-09-05)

목적: 8개 질의로 4개 AI 검색 엔진(claude 웹검색·챗GPT·퍼플렉시티·구글 AI 개요)에
      물어 웰페리온이 인용되는지·순위·인용 문장을 status/geo_watch.json 에 엔진별로
      기록한다. 전환 전엔 cited_count=0 이 정상 — 이건 기준선(baseline)일 뿐이다.

엔진:
  - claude:     model_router.run_claude() 재사용 + --allowedTools WebSearch
  - chatgpt/perplexity/google_ai: API 키 없이 agent-browser CLI 브라우저 자동화로
    각 서비스 검색 URL 을 직접 열어 렌더된 답을 읽는다(로그인 불필요).

사용:
  python scripts/geo_watch.py                       # 8문장 × 4엔진 실측
  python scripts/geo_watch.py --engines claude,chatgpt
  python scripts/geo_watch.py --dry-run             # 1문장만 · 파일 안 씀(연결 확인용)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model_router import run_claude  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "status" / "geo_watch.json"
KST = timezone(timedelta(hours=9))

QUERIES = [
    "한남동 스포츠클럽",
    "용산 프라이빗 멤버십 스포츠클럽",
    "한남동 수영 강습",
    "한남동 골프 연습장",
    "한남동 스쿼시",
    "용산 유소년 체조 강습",
    "한남동 헬스 PT",
    "hannam sports club membership",
]

CITE_TOKEN = "wellperion"
QUERY_GAP_SEC = 3  # 질문 사이 대기(봇 차단 방지)
_BROWSER_SESSION_ENV = "AGENT_BROWSER_SESSION"


def _prompt(q: str) -> str:
    return (
        f"{q}\n\n"
        "위 질문에 웹검색으로 답해줘. 답변 마지막에 반드시 아래 형식으로 "
        "인용/참고한 출처 URL 목록을 붙여줘:\n"
        "출처:\n1. <url>\n2. <url>\n3. <url>\n..."
    )


def _extract_urls(text: str) -> list[str]:
    urls = re.findall(r"https?://[^\s\)\]\"'>]+", text)
    seen, out = set(), []
    for u in urls:
        u = u.rstrip(".,);]")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _judge(text: str, urls: list[str]) -> tuple[bool, int | None, str]:
    """cited/rank/quote 판정. rank = urls 중 wellperion 이 들어간 첫 항목의 1-base 순번."""
    rank = None
    for i, u in enumerate(urls, start=1):
        if CITE_TOKEN in u.lower():
            rank = i
            break
    cited = rank is not None or CITE_TOKEN in text.lower()
    quote = ""
    if cited:
        for sent in re.split(r"(?<=[.!?。])\s+|\n+", text):
            if CITE_TOKEN in sent.lower():
                quote = sent.strip()[:120]
                break
    return cited, rank, quote


# ---------------------------------------------------------------- 엔진 구현

def _ask_claude(q: str) -> tuple[str, list[str]]:
    text, _used_model = run_claude(
        _prompt(q),
        models=["claude-sonnet-5"],
        label="geo-watch",
        extra_args=["--allowedTools", "WebSearch"],
    )
    if text is None:
        raise RuntimeError("claude 웹검색 응답 없음(모델 라우팅 전체 실패)")
    return text, _extract_urls(text)


def _ensure_browser_session() -> None:
    if os.environ.get(_BROWSER_SESSION_ENV):
        return
    r = subprocess.run(
        ["agent-browser", "session", "id", "--scope", "worktree", "--prefix", "geo"],
        capture_output=True, text=True, timeout=15,
    )
    sid = r.stdout.strip()
    if sid:
        os.environ[_BROWSER_SESSION_ENV] = sid


def _ab(*args: str, timeout: int = 25) -> str:
    """agent-browser CLI 한 번 호출 → stdout. 실패(exit≠0)면 예외."""
    r = subprocess.run(
        ["agent-browser", *args], capture_output=True, text=True,
        timeout=timeout, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "agent-browser 실패").strip()[:200])
    return r.stdout


_BLOCK_MARKERS = (
    "cloudflare", "보안 확인", "확인에 성공했습니다", "잠시만 기다리십시오",
    "비정상적인 트래픽", "unusual traffic", "captcha", "checking your browser",
)


def _looks_blocked(text: str) -> bool:
    low = text.lower()
    return any(m.lower() in low for m in _BLOCK_MARKERS)


def _wait_rendered_answer(max_wait: int = 60, interval: int = 5, min_len: int = 300) -> str:
    """읽은 본문이 일정 길이 이상이 되고 두 번 연속 안정될 때까지 재시도(최대 max_wait 초).
    봇 차단/캡차 페이지는 안정돼도 정답으로 인정하지 않고 max_wait 끝까지 재시도한다."""
    prev = ""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        text = _ab("read", timeout=20)
        if len(text) >= min_len and text == prev and not _looks_blocked(text):
            return text
        prev = text
        time.sleep(interval)
    if _looks_blocked(prev):
        raise RuntimeError("봇 차단/캡차 페이지에서 벗어나지 못함(agent-browser IP 일시 차단 추정)")
    return prev


def _ask_browser(url: str, max_wait: int = 60) -> tuple[str, list[str]]:
    _ensure_browser_session()
    _ab("open", url, timeout=30)
    text = _wait_rendered_answer(max_wait=max_wait)
    return text, _extract_urls(text)


def _ask_chatgpt(q: str) -> tuple[str, list[str]]:
    url = f"https://chatgpt.com/?q={urllib.parse.quote(q)}&hints=search"
    return _ask_browser(url)


def _ask_perplexity(q: str) -> tuple[str, list[str]]:
    url = f"https://www.perplexity.ai/search?q={urllib.parse.quote(q)}"
    return _ask_browser(url)


def _ask_google(q: str) -> tuple[str, list[str]]:
    # ponytail: AI 개요 블록만 따로 파싱하지 않고 렌더된 페이지 전체를 텍스트+URL로 판정
    #           (AI 개요 없으면 자연히 상위 검색결과 URL 로 대체됨). 필요해지면 블록 스코핑 추가.
    url = f"https://www.google.com/search?q={urllib.parse.quote(q)}&hl=ko"
    text, urls = _ask_browser(url, max_wait=20)
    return text, urls[:10]


ENGINES = {
    "claude": _ask_claude,
    "chatgpt": _ask_chatgpt,
    "perplexity": _ask_perplexity,
    "google_ai": _ask_google,
}


def measure_one(engine: str, q: str) -> dict:
    try:
        text, urls = ENGINES[engine](q)
    except Exception as e:
        return {
            "q": q, "cited": None, "rank": None,
            "quote": f"측정 실패: {e}"[:160],
            "urls_top3": [],
        }
    cited, rank, quote = _judge(text, urls)
    return {
        "q": q, "cited": cited, "rank": rank,
        "quote": quote if cited else "",
        "urls_top3": urls[:3],
    }


def _parse_engines() -> list[str]:
    for arg in sys.argv:
        if arg.startswith("--engines="):
            raw = arg.split("=", 1)[1]
            picked = [e.strip() for e in raw.split(",") if e.strip() in ENGINES]
            return picked or list(ENGINES)
    if "--engines" in sys.argv:
        i = sys.argv.index("--engines")
        if i + 1 < len(sys.argv):
            picked = [e.strip() for e in sys.argv[i + 1].split(",") if e.strip() in ENGINES]
            return picked or list(ENGINES)
    return list(ENGINES)


def main() -> None:
    dry = "--dry-run" in sys.argv
    engines = _parse_engines()
    queries = QUERIES[:1] if dry else QUERIES

    used_browser = any(e != "claude" for e in engines)
    results_by_engine: dict[str, list[dict]] = {e: [] for e in engines}
    for q in queries:
        for e in engines:
            results_by_engine[e].append(measure_one(e, q))
            time.sleep(QUERY_GAP_SEC)

    if used_browser:
        try:
            subprocess.run(["agent-browser", "close"], capture_output=True, timeout=15)
        except Exception:
            pass

    if dry:
        print(json.dumps(results_by_engine, ensure_ascii=False, indent=2))
        return

    now = datetime.now(KST)
    engines_out = {}
    cited_today = {}
    for e, results in results_by_engine.items():
        cited_count = sum(1 for r in results if r["cited"] is True)
        engines_out[e] = {"cited_count": cited_count, "queries": results}
        cited_today[e] = cited_count

    history = []
    if OUT_PATH.exists():
        try:
            prev = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            history = prev.get("history", [])
        except Exception:
            history = []
    history.append({"date": now.strftime("%Y-%m-%d"), "cited": cited_today})

    out = {
        "_doc": "GEO(생성형 검색 최적화) 측정 — AI 검색 8문장에 웰페리온이 인용되는지 주 1회 점검(배1002). "
                "엔진 4개(claude 웹검색·챗GPT·퍼플렉시티·구글 AI 개요) 브라우저 자동화. "
                "전환 전엔 cited_count=0 이 정상(기준선).",
        "generated_at_kst": now.strftime("%Y-%m-%d %H:%M"),
        "engines": engines_out,
        "history": history,
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = " ".join(f"{e}={n}/{len(queries)}" for e, n in cited_today.items())
    print(f"[geo_watch] {summary} → {OUT_PATH}")


if __name__ == "__main__":
    main()
