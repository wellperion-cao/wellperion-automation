#!/usr/bin/env python3
"""
외부 콘텐츠 금지어 스캔 가드 v1
forbidden_terms.json 에 정의된 금지어가 외부 발행 콘텐츠(instagram/ 등)에
사용됐는지 탐지한다. warn 전용 — 커밋 차단 없음.

사용:
  python ssot/forbidden_scan.py           # 사람용 리포트
  python ssot/forbidden_scan.py --json    # 기계용 JSON 출력
"""

import sys
import io
import json
import argparse
import fnmatch
from pathlib import Path

# stdout을 UTF-8로 강제 (Windows PYTHONIOENCODING 무관)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 스캔 대상 텍스트 확장자 화이트리스트 (콘텐츠 캡션 중심)
TEXT_EXTENSIONS = {
    ".md", ".txt", ".json", ".html", ".csv",
}

# 제외 파일 확장자 (바이너리) — divergence_scan 동일
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
    ".otf", ".ttf", ".woff", ".woff2",
    ".pdf", ".docx", ".xlsx", ".pptx",
    ".zip", ".tar", ".gz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".bin",
    ".mp3", ".mp4", ".mov", ".avi",
    ".pyc", ".pyo",
}


def load_terms(repo_root: Path) -> dict:
    """forbidden_terms.json 로드"""
    terms_path = repo_root / "ssot" / "forbidden_terms.json"
    with open(terms_path, encoding="utf-8") as f:
        return json.load(f)


def matches_glob_list(rel_path_str: str, patterns: list) -> bool:
    """rel_path_str 이 patterns 중 하나에 fnmatch 매칭되면 True"""
    normalized = rel_path_str.replace("\\", "/")
    for pattern in patterns:
        if fnmatch.fnmatch(normalized, pattern):
            return True
    return False


def is_excluded(path: Path, repo_root: Path, exclude_globs: list, exclude_dir_names: list) -> bool:
    """제외 대상 경로인지 확인"""
    try:
        rel = path.relative_to(repo_root)
    except ValueError:
        return True

    # 제외 디렉터리 이름 체크
    for part in rel.parts:
        if part in exclude_dir_names:
            return True

    # 제외 글롭 체크
    rel_str = str(rel).replace("\\", "/")
    return matches_glob_list(rel_str, exclude_globs)


def collect_files(repo_root: Path, scan_globs: list, exclude_globs: list, exclude_dir_names: list) -> list:
    """스캔 대상 파일 목록 수집"""
    result = []
    for p in repo_root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in BINARY_EXTENSIONS:
            continue
        if p.suffix.lower() not in TEXT_EXTENSIONS:
            continue

        try:
            rel_str = str(p.relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            continue

        # scan_globs 에 해당하는지
        if not matches_glob_list(rel_str, scan_globs):
            continue

        # 제외 대상이면 스킵
        if is_excluded(p, repo_root, exclude_globs, exclude_dir_names):
            continue

        result.append(p)
    return result


def scan_file_for_term(file_path: Path, term: str) -> list:
    """파일에서 term 이 등장하는 (lineno, line_text) 목록 반환"""
    hits = []
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if term in line:
                hits.append((lineno, line.rstrip()))
    except (OSError, PermissionError):
        pass
    return hits


def run_scan(repo_root: Path, config: dict) -> list:
    """
    전체 스캔 실행.
    반환: term별 결과 리스트
    [
      {
        "term": ..., "replace": ..., "note": ...,
        "hits": [{"file": "상대경로", "lines": [(lineno, text), ...]}, ...]
      }
    ]
    """
    scan_globs = config.get("scan_globs", [])
    exclude_globs = config.get("exclude_globs", [])
    exclude_dir_names = config.get("exclude_dir_names", [])
    terms = config.get("terms", [])

    files = collect_files(repo_root, scan_globs, exclude_globs, exclude_dir_names)
    results = []

    for entry in terms:
        term = entry["term"]
        replace = entry.get("replace", "")
        note = entry.get("note", "")

        hits = []
        for fpath in files:
            try:
                rel_str = str(fpath.relative_to(repo_root)).replace("\\", "/")
            except ValueError:
                continue

            line_hits = scan_file_for_term(fpath, term)
            if line_hits:
                hits.append({"file": rel_str, "lines": line_hits})

        results.append({
            "term": term,
            "replace": replace,
            "note": note,
            "hits": hits,
        })

    return results


def print_report(results: list) -> int:
    """사람용 리포트 출력. 반환값=총 위반 파일 수"""
    print("=" * 60)
    print("  웰페리온 외부 콘텐츠 금지어 스캔 v1")
    print("=" * 60)
    print()

    total_violation_files = 0

    for r in results:
        term = r["term"]
        replace = r["replace"]
        note = r["note"]
        hits = r["hits"]
        file_count = len(hits)
        total_violation_files += file_count

        if file_count == 0:
            status = "✅"
            summary = "위반 없음"
        else:
            hit_count = sum(len(h["lines"]) for h in hits)
            status = "⚠️"
            summary = f"{hit_count}건 / {file_count}개 파일"

        print(f"[{term!r}]  {status}  {summary}")
        print(f"  대안: {replace}")
        print(f"  규칙: {note}")

        if hits:
            for h in hits:
                print(f"    파일: {h['file']}")
                for lineno, line_text in h["lines"]:
                    print(f"      L{lineno}: {line_text.strip()}")
                    print(f"        → '{term}' 대신 '{replace}'")

        print()

    print("-" * 60)
    if total_violation_files == 0:
        print("✅ 외부 콘텐츠 금지어 없음 — 브랜드 용어 정합")
    else:
        print(f"⚠️ 전체 요약: 금지어 위반 {total_violation_files}개 파일 — 수정 필요")
    print()

    return total_violation_files


def print_json_output(results: list) -> int:
    """기계용 JSON 출력"""
    total_violation_files = sum(len(r["hits"]) for r in results)
    # JSON 직렬화를 위해 hits 내부 lines를 딕셔너리로 변환
    serializable_results = []
    for r in results:
        hits_out = []
        for h in r["hits"]:
            hits_out.append({
                "file": h["file"],
                "lines": [{"lineno": ln, "text": txt} for ln, txt in h["lines"]],
            })
        serializable_results.append({
            "term": r["term"],
            "replace": r["replace"],
            "note": r["note"],
            "hits": hits_out,
        })

    output = {
        "scan_version": "v1",
        "total_violation_files": total_violation_files,
        "clean": total_violation_files == 0,
        "results": serializable_results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return total_violation_files


def main():
    parser = argparse.ArgumentParser(
        description="웰페리온 외부 콘텐츠 금지어 스캔 v1 — 브랜드 용어 위반 탐지"
    )
    parser.add_argument(
        "--json", action="store_true", help="기계용 JSON 출력 모드"
    )
    args = parser.parse_args()

    # 리포 루트 = 이 파일 기준 상위 디렉터리
    repo_root = Path(__file__).resolve().parent.parent

    try:
        config = load_terms(repo_root)
    except FileNotFoundError:
        print("오류: ssot/forbidden_terms.json 를 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"오류: forbidden_terms.json 로드 실패 — {e}", file=sys.stderr)
        sys.exit(1)

    try:
        results = run_scan(repo_root, config)
    except Exception as e:
        print(f"오류: 스캔 실패 — {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print_json_output(results)
    else:
        print_report(results)


if __name__ == "__main__":
    main()
