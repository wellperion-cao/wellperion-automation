#!/usr/bin/env python3
"""
발산 스캔 가드 v2
캐논 값(canon_values.json "values")이 코드 곳곳에 하드코딩 복사본으로 남았는지 탐지한다.
INC-001 부류(한쪽만 고쳐 회귀) 사전 탐지용. 읽기전용 — incidents 자동등록 없음.

v2(2026-07-20 GM 지시): 값뿐 아니라 "규칙"(canon_values.json "rules")도 같은 파일에서
확장 감시한다 — 채널별 CTA 규칙이 5곳에 따로 서술돼 서로 어긋난 사고 재발방지. 규칙은
값처럼 고정 문자열이 아니라 매번 다른 문장으로 재서술되므로, 리터럴 매칭 대신 신호
동시등장(채널명 2개+ & CTA 신호가 근접 구간에 함께 등장)으로 탐지한다(run_rule_scan).
같은 allow_globs·source 규약을 그대로 재사용 — 새 레지스트리 파일 신설 없음.

사용:
  python ssot/divergence_scan.py           # 사람용 리포트(값+규칙)
  python ssot/divergence_scan.py --json    # 기계용 JSON 출력(값+규칙)
"""

import sys
import io
import json
import argparse
import fnmatch
import re
from pathlib import Path

# stdout을 UTF-8로 강제 (Windows PYTHONIOENCODING 무관)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 스캔 대상 텍스트 확장자 화이트리스트
TEXT_EXTENSIONS = {
    ".py", ".js", ".json", ".md", ".html", ".txt", ".bat", ".gs", ".css",
    ".ts", ".tsx", ".sh", ".yaml", ".yml", ".env", ".toml", ".ini", ".cfg",
}

# 제외 디렉터리 패턴
EXCLUDE_DIRS = {
    ".git", "_archive", "node_modules", ".venv", "venv", "memory",
    "__pycache__", ".mypy_cache", ".pytest_cache",
    # 서브에이전트 격리 작업트리(.claude/worktrees/agent-*) — 레포 전체의 임시 사본이라
    # 스캔 시 진짜 히트를 워크트리 개수만큼 중복 뻥튀기한다(2026-07-20 실측: 값 발산
    # 1319건 중 1179건·규칙 발산 112건 중 90여건이 worktrees 중복). 실사본이 아니므로 제외.
    "worktrees",
}

# 제외 파일 확장자 (바이너리)
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
    ".otf", ".ttf", ".woff", ".woff2",
    ".pdf", ".docx", ".xlsx", ".pptx",
    ".zip", ".tar", ".gz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".bin",
    ".mp3", ".mp4", ".mov", ".avi",
    ".pyc", ".pyo",
}


def load_canon(repo_root: Path) -> dict:
    """canon_values.json 로드"""
    canon_path = repo_root / "ssot" / "canon_values.json"
    with open(canon_path, encoding="utf-8") as f:
        return json.load(f)


def is_excluded_path(path: Path, repo_root: Path) -> bool:
    """제외 대상 경로인지 확인"""
    try:
        rel = path.relative_to(repo_root)
    except ValueError:
        return True

    parts = rel.parts
    for part in parts:
        if part in EXCLUDE_DIRS:
            return True
        # memory/ 경로 패턴 (웰리 메모리)
        if part == "memory":
            return True

    return False


def matches_allow_globs(rel_path_str: str, allow_globs: list[str]) -> bool:
    """파일이 허용 글롭 목록 중 하나에 해당하면 True"""
    # 경로 구분자를 /로 통일
    normalized = rel_path_str.replace("\\", "/")
    for pattern in allow_globs:
        if fnmatch.fnmatch(normalized, pattern):
            return True
    return False


def scan_file(file_path: Path, value: str) -> list[int]:
    """파일에서 캐논 값이 등장하는 라인 번호 목록 반환"""
    hits = []
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if value in line:
                hits.append(lineno)
    except (OSError, PermissionError):
        pass
    return hits


def collect_files(repo_root: Path) -> list[Path]:
    """스캔 대상 파일 목록 수집"""
    result = []
    for p in repo_root.rglob("*"):
        if not p.is_file():
            continue
        if is_excluded_path(p, repo_root):
            continue
        if p.suffix.lower() in BINARY_EXTENSIONS:
            continue
        if p.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        result.append(p)
    return result


def run_scan(repo_root: Path, canon: dict) -> list[dict]:
    """
    전체 스캔 실행.
    반환: key별 결과 리스트
    [
      {
        "key": ..., "value": ..., "source": ..., "note": ...,
        "hits": [{"file": "상대경로", "lines": [1,2,3]}, ...]
      }
    ]
    """
    files = collect_files(repo_root)
    results = []

    for entry in canon.get("values", []):
        key = entry["key"]
        value = entry["value"]
        source = entry.get("source", "")
        allow_globs = entry.get("allow_globs", [])
        note = entry.get("note", "")

        # source 파일 자체도 allow_globs에 암묵 포함
        source_globs = list(allow_globs)
        if source and source not in source_globs:
            source_globs.append(source)

        hits = []
        for fpath in files:
            try:
                rel_str = str(fpath.relative_to(repo_root)).replace("\\", "/")
            except ValueError:
                continue

            # 허용 글롭에 해당하면 스킵
            if matches_allow_globs(rel_str, source_globs):
                continue

            lines = scan_file(fpath, value)
            if lines:
                hits.append({"file": rel_str, "lines": lines})

        results.append({
            "key": key,
            "value": value,
            "source": source,
            "note": note,
            "hits": hits,
        })

    return results


# ─────────────────────────────────────────────────────────────
# 규칙 SSOT 스캔 (v2 · 2026-07-20) — canon_values.json "rules" 배열 소비.
# 값과 달리 규칙은 고정 문자열이 아니므로 "신호 동시등장" 방식으로 탐지한다:
# 근접한 몇 줄 구간 안에 채널명이 min_channels개 이상 + CTA 신호가 함께 나오면
# "규칙을 다시 서술 중"으로 간주. allow_globs·source 자동허용은 값 스캔과 동일 규약.
# ─────────────────────────────────────────────────────────────

RULE_CHANNEL_TOKENS_DEFAULT = ["블로그", "카페", "당근", "카카오", "인스타그램", "페이스북", "IG"]
RULE_CTA_CUE_DEFAULT = ["CTA"]
RULE_WINDOW_LINES_DEFAULT = 5
RULE_MIN_CHANNELS_DEFAULT = 2


def _cta_cue_pattern(cues: list[str]) -> "re.Pattern":
    """CTA 신호 토큰을 단어경계 매칭 정규식으로 컴파일.
    단순 substring 매칭은 cta_utm.py(정본 파일명 인용)·LINK_CARD_CTA_URL(식별자) 등에서
    대량 오탐을 냈다(2026-07-20 실측) — 앞뒤가 단어문자(\\w, 언더스코어 포함)면 매칭 제외해
    '정본 파일 인용'·'식별자 일부'와 '규칙을 설명하는 단어로서의 CTA'를 구분한다."""
    alt = "|".join(re.escape(c) for c in cues)
    return re.compile(rf"(?<!\w)(?:{alt})(?!\w)")


def scan_file_for_rule(file_path: Path, rule: dict) -> list[dict]:
    """파일에서 규칙 지문(채널명 min_channels개+ & CTA 신호가 window_lines 구간 안에
    동시 등장)이 걸리는 위치를 찾는다. 반환: [{"line": 시작줄, "channels": [...]}]."""
    channels = rule.get("fingerprint_channels") or RULE_CHANNEL_TOKENS_DEFAULT
    cta_cues = rule.get("fingerprint_cta") or RULE_CTA_CUE_DEFAULT
    cta_re = _cta_cue_pattern(cta_cues)
    window = rule.get("window_lines", RULE_WINDOW_LINES_DEFAULT)
    min_channels = rule.get("min_channels", RULE_MIN_CHANNELS_DEFAULT)

    hits: list[dict] = []
    try:
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except (OSError, PermissionError):
        return hits

    n = len(lines)
    i = 0
    while i < n:
        block = "\n".join(lines[i:i + window])
        found_channels = {c for c in channels if c in block}
        has_cta = bool(cta_re.search(block))
        if len(found_channels) >= min_channels and has_cta:
            hits.append({"line": i + 1, "channels": sorted(found_channels)})
            i += window  # 겹치는 구간 중복 카운트 방지 — 매치 구간만큼 건너뜀
        else:
            i += 1
    return hits


def run_rule_scan(repo_root: Path, canon: dict) -> list[dict]:
    """규칙 재서술(발산) 스캔. run_scan()과 동일한 allow_globs·소스 규약 재사용.
    반환 형태는 run_scan()과 동일(key/source/note/hits) — hits[].matches 만 추가."""
    files = collect_files(repo_root)
    results = []

    for rule in canon.get("rules", []):
        key = rule["key"]
        source = rule.get("source", "")
        allow_globs = rule.get("allow_globs", [])
        note = rule.get("note", "")

        source_globs = list(allow_globs)
        if source and source not in source_globs:
            source_globs.append(source)

        hits = []
        for fpath in files:
            try:
                rel_str = str(fpath.relative_to(repo_root)).replace("\\", "/")
            except ValueError:
                continue
            if matches_allow_globs(rel_str, source_globs):
                continue
            matches = scan_file_for_rule(fpath, rule)
            if matches:
                hits.append({"file": rel_str, "matches": matches})

        results.append({"key": key, "source": source, "note": note, "hits": hits})

    return results


def print_rule_report(results: list[dict]) -> int:
    """규칙 재서술 사람용 리포트 출력. 반환값=총 재서술 후보 파일 수"""
    print("=" * 60)
    print("  웰페리온 규칙 SSOT 감시 — 규칙 재서술(중복 서술) 탐지")
    print("=" * 60)
    print()

    total_files = 0
    for r in results:
        key = r["key"]
        note = r["note"]
        hits = r["hits"]
        file_count = len(hits)
        total_files += file_count

        if file_count == 0:
            status = "✅"
            summary = "정본 밖 재서술 없음"
        else:
            status = "⚠️"
            summary = f"정본 밖 재서술 후보 {file_count}개 파일"

        print(f"[{key}]  {status}  {summary}")
        print(f"  설명: {note}")
        print(f"  정본: {r['source']}")

        if hits:
            for h in hits:
                lines_str = ", ".join(str(m["line"]) for m in h["matches"])
                print(f"    - {h['file']}  (줄 {lines_str})")

        print()

    print("-" * 60)
    if total_files == 0:
        print("✅ 규칙 요약: 재서술 후보 없음 — 규칙 단일출처 정합")
    else:
        print(f"⚠️ 규칙 요약: 재서술 후보 {total_files}개 파일 — 웰리 판단 필요")
    print()

    return total_files


def print_report(results: list[dict]) -> int:
    """사람용 리포트 출력. 반환값=총 복사본 파일 수"""
    print("=" * 60)
    print("  웰페리온 발산 스캔 가드 v1 — 하드코딩 복사본 탐지")
    print("=" * 60)
    print()

    total_files = 0

    for r in results:
        key = r["key"]
        value = r["value"]
        note = r["note"]
        hits = r["hits"]
        hit_count = sum(len(h["lines"]) for h in hits)
        file_count = len(hits)
        total_files += file_count

        if file_count == 0:
            status = "✅"
            summary = "정본 밖 복사본 없음"
        else:
            status = "⚠️"
            summary = f"정본 밖 {hit_count}건 / {file_count}개 파일"

        print(f"[{key}]  {status}  {value!r}")
        print(f"  설명: {note}")
        print(f"  정본: {r['source']}")
        print(f"  결과: {summary}")

        if hits:
            for h in hits:
                lines_str = ", ".join(str(ln) for ln in h["lines"])
                print(f"    - {h['file']}  (라인 {lines_str})")

        print()

    print("-" * 60)
    if total_files == 0:
        print("✅ 전체 요약: 하드코딩 복사본 없음 — 캐논 값 단일출처 정합")
    else:
        print(f"⚠️ 전체 요약: 복사본 후보 {total_files}개 파일 — 웰리 판단 필요")
    print()

    return total_files


def print_json(results: list[dict], rule_results: list[dict] | None = None) -> int:
    """기계용 JSON 출력. rule_results 는 하위호환 위해 선택 인자(생략 시 값만 출력)."""
    total_files = sum(len(r["hits"]) for r in results)
    output = {
        "scan_version": "v2",
        "total_copycandidate_files": total_files,
        "clean": total_files == 0,
        "results": results,
    }
    total = total_files
    if rule_results is not None:
        total_rule_files = sum(len(r["hits"]) for r in rule_results)
        output["total_rule_copycandidate_files"] = total_rule_files
        output["rule_clean"] = total_rule_files == 0
        output["rule_results"] = rule_results
        total += total_rule_files
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return total


def main():
    parser = argparse.ArgumentParser(
        description="웰페리온 발산 스캔 가드 v1 — 캐논 값 하드코딩 복사본 탐지"
    )
    parser.add_argument(
        "--json", action="store_true", help="기계용 JSON 출력 모드"
    )
    args = parser.parse_args()

    # 리포 루트 = 이 파일 기준 상위 디렉터리
    repo_root = Path(__file__).resolve().parent.parent

    try:
        canon = load_canon(repo_root)
    except FileNotFoundError:
        print("오류: ssot/canon_values.json 를 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)

    results = run_scan(repo_root, canon)
    rule_results = run_rule_scan(repo_root, canon)

    if args.json:
        print_json(results, rule_results)
    else:
        print_report(results)
        print_rule_report(rule_results)


if __name__ == "__main__":
    main()
