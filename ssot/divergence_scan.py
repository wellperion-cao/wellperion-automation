#!/usr/bin/env python3
"""
발산 스캔 가드 v1
캐논 값(canon_values.json)이 코드 곳곳에 하드코딩 복사본으로 남았는지 탐지한다.
INC-001 부류(한쪽만 고쳐 회귀) 사전 탐지용. 읽기전용 — incidents 자동등록 없음.

사용:
  python ssot/divergence_scan.py           # 사람용 리포트
  python ssot/divergence_scan.py --json    # 기계용 JSON 출력
"""

import sys
import io
import json
import argparse
import fnmatch
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


def print_json(results: list[dict]) -> int:
    """기계용 JSON 출력"""
    total_files = sum(len(r["hits"]) for r in results)
    output = {
        "scan_version": "v1",
        "total_copycandidate_files": total_files,
        "clean": total_files == 0,
        "results": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return total_files


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

    if args.json:
        print_json(results)
    else:
        print_report(results)


if __name__ == "__main__":
    main()
