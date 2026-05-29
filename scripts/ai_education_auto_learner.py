#!/usr/bin/env python3
"""AI 교육 자동 학습 시스템 v2.0

Anthropic/Claude 최신 정보 수집 → 요약 → C-Level 텔레그램 배포
기존 education_archive_weekly.py(파일 정리)와 상호 보완.

v2.0 (2026-05-29): 수집 소스를 learning/sources.json(SSOT)에서 로드하도록 확장.
                   3개 → 7개. 파일 없으면 내장 기본 3개로 폴백.

사용법:
  python ai_education_auto_learner.py              # 수집+요약+발송
  python ai_education_auto_learner.py --collect     # 수집만
  python ai_education_auto_learner.py --summary     # 요약만 (이전 수집 결과)
  python ai_education_auto_learner.py --send        # 마지막 요약 발송
  python ai_education_auto_learner.py --status      # 현황
"""
import argparse
import json
import os
import sys
import io
import re
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 경로 상수 ──
BASE_DIR = Path(r"C:\Users\jjky0\welperion-automation")
ENV_FILE = BASE_DIR / "telegram_bot" / ".env"
DATA_DIR = BASE_DIR / "scripts" / "_education_data"
COLLECT_FILE = DATA_DIR / "latest_collect.json"
SUMMARY_FILE = DATA_DIR / "latest_summary.json"
ARCHIVE_DIR = Path(r"C:\Users\jjky0\Desktop\_정리완료\03_교육")
SOURCES_FILE = BASE_DIR / "learning" / "sources.json"

# ── 수집 대상 소스 (기본값) ──
# learning/sources.json 이 있으면 그쪽을 SSOT 로 사용하고,
# 없거나 깨지면 아래 내장 기본 3개로 폴백한다 (load_sources 참조).
DEFAULT_SOURCES = [
    {
        "id": "anthropic_news",
        "label": "Anthropic 공식 뉴스",
        "url": "https://www.anthropic.com/news",
        "parser": "html_title_extract",
    },
    {
        "id": "anthropic_research",
        "label": "Anthropic 리서치",
        "url": "https://www.anthropic.com/research",
        "parser": "html_title_extract",
    },
    {
        "id": "claude_docs_changelog",
        "label": "Claude 문서 변경사항",
        "url": "https://docs.anthropic.com/en/docs/about-claude/models",
        "parser": "html_title_extract",
    },
]


def load_sources() -> list:
    """learning/sources.json 에서 소스 레지스트리를 로드.

    파일이 없거나 형식이 깨지면 DEFAULT_SOURCES(내장 3개)로 폴백한다.
    각 항목 필수 키: id·label·url·parser.
    """
    if not SOURCES_FILE.exists():
        return DEFAULT_SOURCES
    try:
        data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
        items = data.get("sources", []) if isinstance(data, dict) else data
        valid = [
            s for s in items
            if isinstance(s, dict)
            and all(k in s for k in ("id", "label", "url", "parser"))
        ]
        if valid:
            return valid
        print(f"  [WARN] {SOURCES_FILE.name} 유효 소스 없음 — 내장 기본값 폴백")
        return DEFAULT_SOURCES
    except Exception as e:
        print(f"  [WARN] {SOURCES_FILE.name} 로드 실패 ({type(e).__name__}) — 내장 기본값 폴백")
        return DEFAULT_SOURCES


SOURCES = load_sources()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def load_env() -> dict:
    out = {}
    if not ENV_FILE.exists():
        return out
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ═══════════════════════════════════════════
#  수집 (Collect)
# ═══════════════════════════════════════════
def fetch_page(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [WARN] 페이지 로드 실패 ({url}): {type(e).__name__}")
        return ""


def extract_titles_from_html(html: str) -> list:
    titles = []
    for pattern in [
        r'<h[1-3][^>]*>([^<]+)</h[1-3]>',
        r'<title>([^<]+)</title>',
        r'<a[^>]*class="[^"]*(?:post|article|card|entry)[^"]*"[^>]*>([^<]+)</a>',
    ]:
        for match in re.findall(pattern, html, re.IGNORECASE):
            clean = match.strip()
            if clean and len(clean) > 5 and len(clean) < 200:
                titles.append(clean)
    return titles[:20]


def collect_sources() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    results = {
        "collected_at": now_str(),
        "sources": [],
    }

    for src in SOURCES:
        print(f"  수집 중: {src['label']} ({src['url']})")
        html = fetch_page(src["url"])

        if src["parser"] == "html_title_extract":
            items = extract_titles_from_html(html)
        else:
            items = []

        entry = {
            "id": src["id"],
            "label": src["label"],
            "url": src["url"],
            "items_count": len(items),
            "items": items,
        }
        results["sources"].append(entry)
        print(f"    -> {len(items)}건 추출")

    COLLECT_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n[수집 완료] {sum(s['items_count'] for s in results['sources'])}건 → {COLLECT_FILE}")
    return results


# ═══════════════════════════════════════════
#  요약 (Summary)
# ═══════════════════════════════════════════
def generate_summary(collect_data: dict = None) -> dict:
    if collect_data is None:
        if not COLLECT_FILE.exists():
            print("[ERROR] 수집 데이터 없음. --collect 먼저 실행")
            return {}
        collect_data = json.loads(COLLECT_FILE.read_text(encoding="utf-8"))

    summary_lines = []
    summary_lines.append(f"AI 교육 자동 학습 요약 ({today_str()})")
    summary_lines.append("=" * 40)
    summary_lines.append(f"수집 시각: {collect_data.get('collected_at', '?')}")
    summary_lines.append("")

    for src in collect_data.get("sources", []):
        summary_lines.append(f"[{src['label']}]")
        if src["items"]:
            for i, item in enumerate(src["items"][:5], 1):
                summary_lines.append(f"  {i}. {item}")
        else:
            summary_lines.append("  (수집 항목 없음)")
        summary_lines.append("")

    # 로컬 교육 자료 현황
    education_files = scan_local_education_files()
    if education_files:
        summary_lines.append("[로컬 교육 자료 현황]")
        summary_lines.append(f"  총 {len(education_files)}건")
        for f in education_files[:5]:
            summary_lines.append(f"  - {f['name']} ({f['modified']})")
        summary_lines.append("")

    summary_text = "\n".join(summary_lines)
    summary = {
        "generated_at": now_str(),
        "text": summary_text,
        "source_count": len(collect_data.get("sources", [])),
        "total_items": sum(s["items_count"] for s in collect_data.get("sources", [])),
        "local_files": len(education_files),
    }

    SUMMARY_FILE.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(summary_text)
    return summary


def scan_local_education_files() -> list:
    files = []
    search_dirs = [
        ARCHIVE_DIR,
        Path.home() / "Desktop",
        Path.home() / "Downloads",
    ]
    keywords = [
        "claude", "gpt", "llm", "anthropic", "gemini",
        "prompt", "ai", "에이전트", "튜토리얼",
    ]
    extensions = {".pdf", ".docx", ".md", ".txt", ".html", ".epub"}

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for f in search_dir.iterdir():
            if not f.is_file():
                continue
            if f.suffix.lower() not in extensions:
                continue
            name_lower = f.name.lower()
            if any(kw in name_lower for kw in keywords):
                files.append({
                    "name": f.name,
                    "path": str(f),
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d"),
                })

    files.sort(key=lambda x: x["modified"], reverse=True)
    return files


# ═══════════════════════════════════════════
#  발송 (Send via Telegram)
# ═══════════════════════════════════════════
def send_summary(summary_data: dict = None) -> bool:
    if summary_data is None:
        if not SUMMARY_FILE.exists():
            print("[ERROR] 요약 데이터 없음. --summary 먼저 실행")
            return False
        summary_data = json.loads(SUMMARY_FILE.read_text(encoding="utf-8"))

    text = summary_data.get("text", "")
    if not text:
        print("[ERROR] 요약 텍스트 비어있음")
        return False

    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("[WARN] 텔레그램 설정 없음 — 발송 생략")
        print("[OUTPUT] 요약 내용:")
        print(text)
        return False

    # 텔레그램 메시지 4096자 제한
    if len(text) > 4000:
        text = text[:3990] + "\n...(잘림)"

    payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = json.loads(resp.read().decode()).get("ok", False)
            print(f"[발송 {'성공' if ok else '실패'}]")
            return ok
    except Exception as e:
        print(f"[ERROR] 발송 실패: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════
#  현황 조회
# ═══════════════════════════════════════════
def show_status():
    print(f"=== AI 교육 자동 학습 시스템 현황 ({now_str()}) ===\n")

    origin = "learning/sources.json" if SOURCES_FILE.exists() else "내장 기본값(폴백)"
    print(f"[수집 소스] {len(SOURCES)}개 (출처: {origin})")
    for src in SOURCES:
        print(f"  - {src['label']}: {src['url']}")

    if COLLECT_FILE.exists():
        data = json.loads(COLLECT_FILE.read_text(encoding="utf-8"))
        total = sum(s["items_count"] for s in data.get("sources", []))
        print(f"\n[마지막 수집] {data.get('collected_at', '?')} — {total}건")
    else:
        print("\n[마지막 수집] 없음")

    if SUMMARY_FILE.exists():
        data = json.loads(SUMMARY_FILE.read_text(encoding="utf-8"))
        print(f"[마지막 요약] {data.get('generated_at', '?')}")
    else:
        print("[마지막 요약] 없음")

    files = scan_local_education_files()
    print(f"\n[로컬 교육 자료] {len(files)}건")

    archive_script = BASE_DIR / "scripts" / "education_archive_weekly.py"
    print(f"[정리 스크립트] {'존재' if archive_script.exists() else '없음'} ({archive_script.name})")
    print(f"[정리 폴더] {ARCHIVE_DIR}")


# ═══════════════════════════════════════════
#  전체 파이프라인 (수집 → 요약 → 발송)
# ═══════════════════════════════════════════
def run_full_pipeline():
    print(f"[시작] AI 교육 자동 학습 파이프라인 ({now_str()})\n")

    print("=== 1/3: 수집 ===")
    collect_data = collect_sources()

    print("\n=== 2/3: 요약 ===")
    summary = generate_summary(collect_data)

    print("\n=== 3/3: 발송 ===")
    send_summary(summary)

    print(f"\n[완료] 파이프라인 종료 ({now_str()})")


# ═══════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="AI 교육 자동 학습 시스템 v2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "예시:\n"
            "  %(prog)s                # 전체 파이프라인 (수집→요약→발송)\n"
            "  %(prog)s --collect      # 수집만\n"
            "  %(prog)s --summary      # 요약 생성\n"
            "  %(prog)s --send         # 마지막 요약 발송\n"
            "  %(prog)s --status       # 현황 조회\n"
        ),
    )
    parser.add_argument("--collect", action="store_true", help="웹 소스에서 최신 정보 수집")
    parser.add_argument("--summary", action="store_true", help="수집 결과 요약 생성")
    parser.add_argument("--send", action="store_true", help="마지막 요약을 텔레그램 발송")
    parser.add_argument("--status", action="store_true", help="현황 조회")

    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.collect:
        collect_sources()
    elif args.summary:
        generate_summary()
    elif args.send:
        send_summary()
    else:
        run_full_pipeline()


if __name__ == "__main__":
    main()
