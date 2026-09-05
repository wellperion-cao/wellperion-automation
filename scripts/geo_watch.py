"""
GEO 측정기 — AI 검색 인용 주 1회 자동 점검 (배971, GM 지시 2026-09-05)

목적: 8개 질의로 AI 검색(claude 웹검색)에 물어 웰페리온이 인용되는지·
      순위·인용 문장을 status/geo_watch.json 에 기록한다. 전환 전엔
      cited_count=0 이 정상 — 이건 기준선(baseline)일 뿐이다.

엔진: model_router.run_claude() 재사용(재시도·타임아웃 정책 그대로) +
      --allowedTools WebSearch 로 claude CLI 에 실제 웹검색을 시킨다.
      챗GPT·퍼플렉시티는 API 키가 없어 미구현 — engines_pending 에만 표기.

사용:
  python scripts/geo_watch.py            # 8문장 실측 → status/geo_watch.json 갱신
  python scripts/geo_watch.py --dry-run  # 1문장만 · 파일 안 씀(연결 확인용)
"""
from __future__ import annotations

import json
import re
import sys
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
    "한남동 수영 레슨",
    "한남동 골프 연습장",
    "한남동 스쿼시",
    "용산 키즈 체조 수업",
    "한남동 헬스 PT",
    "hannam sports club membership",
]

CITE_TOKEN = "wellperion"


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


def measure_one(q: str) -> dict:
    text, used_model = run_claude(
        _prompt(q),
        models=["claude-sonnet-5"],
        label="geo-watch",
        extra_args=["--allowedTools", "WebSearch"],
    )
    if text is None:
        return {
            "q": q, "cited": None, "rank": None,
            "quote": "측정 실패: claude 웹검색 응답 없음(모델 라우팅 전체 실패)",
            "urls_top3": [],
        }
    urls = _extract_urls(text)
    cited, rank, quote = _judge(text, urls)
    return {
        "q": q, "cited": cited, "rank": rank,
        "quote": quote if cited else "",
        "urls_top3": urls[:3],
    }


def main() -> None:
    dry = "--dry-run" in sys.argv
    queries = QUERIES[:1] if dry else QUERIES
    results = [measure_one(q) for q in queries]

    if dry:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    cited_count = sum(1 for r in results if r["cited"] is True)
    now = datetime.now(KST)

    history = []
    if OUT_PATH.exists():
        try:
            prev = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            history = prev.get("history", [])
        except Exception:
            history = []
    history.append({"date": now.strftime("%Y-%m-%d"), "cited_count": cited_count})

    out = {
        "_doc": "GEO(생성형 검색 최적화) 측정 — AI 검색 8문장에 웰페리온이 인용되는지 주 1회 점검(배971). "
                "전환 전엔 cited_count=0 이 정상(기준선). engine=claude 웹검색만 구현, "
                "chatgpt/perplexity 는 API 키 없어 미구현(engines_pending).",
        "generated_at_kst": now.strftime("%Y-%m-%d %H:%M"),
        "engine": "claude-websearch",
        "engines_pending": ["chatgpt", "perplexity"],
        "queries": results,
        "cited_count": cited_count,
        "history": history,
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[geo_watch] cited_count={cited_count}/{len(results)} → {OUT_PATH}")


if __name__ == "__main__":
    main()
