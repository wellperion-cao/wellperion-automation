# -*- coding: utf-8 -*-
"""금지어 스캐너 — 대외로 나가는 글에 옛 정체성 낱말이 남았는지 본다.

왜 있나 (2026-09-09 · 배1118·923)
---------------------------------
`ssot/forbidden_terms.json` 의 머리말은 "forbidden_scan.py 가 읽어 … 탐지한다"고
적어 두었지만 **그 파일이 없었다.** 가리키는 곳이 빈 죽은 포인터라, 금지어 검사는
한 번도 돈 적이 없다. 그 사이 페이스북 커버와 새 홈 첫 화면이 나란히
"Premium Lifestyle Club" 을 달고 대외에 떠 있었고, 사람이 눈으로 볼 때까지 아무도 몰랐다.

정본은 여전히 `ssot/forbidden_terms.json` 이다 — 낱말을 여기 코드에 적지 않는다.
새 금지어는 그 JSON 의 terms 에 한 줄 추가하면 이 스캐너가 바로 본다.

쓰는 법
-------
    C:/Python314/python.exe scripts/forbidden_scan.py            # 사람이 읽는 요약
    C:/Python314/python.exe scripts/forbidden_scan.py --json     # 기계 판독
    C:/Python314/python.exe scripts/forbidden_scan.py --self-check

종료코드: 걸린 것 0건이면 0, 1건 이상이면 1.
"""
from __future__ import annotations

import argparse
import json
import sys
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SSOT = ROOT / "ssot" / "forbidden_terms.json"
TEXT_SUFFIXES = {".html", ".htm", ".md", ".txt", ".json", ".js", ".css"}


def load_rules() -> dict:
    return json.loads(SSOT.read_text(encoding="utf-8"))


def _excluded(rel: str, rules: dict) -> bool:
    if any(part in rules.get("exclude_dir_names", []) for part in Path(rel).parts):
        return True
    return any(fnmatch(rel, pat) for pat in rules.get("exclude_globs", []))


def iter_files(rules: dict):
    """scan_globs 가 가리키는 디렉터리 아래의 글 파일만 훑는다."""
    seen = set()
    for pat in rules.get("scan_globs", []):
        base = pat.split("**", 1)[0].rstrip("/")
        root = ROOT / base if base else ROOT
        if not root.exists():
            print(f"[WARN] 검사 범위가 없는 경로를 가리킨다: {base}", file=sys.stderr)
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            if rel in seen or _excluded(rel, rules):
                continue
            seen.add(rel)
            yield path, rel


# 금지어를 "쓰지 마라"고 적어 둔 줄은 위반이 아니다. 규칙을 적은 문서까지 걸리면
# 스캐너가 매번 제 규칙집을 물어뜯고, 그러면 사람이 결과를 안 보게 된다.
# ponytail: 낱말 기반 어림짐작 — 오탐이 늘면 exclude_globs 로 파일을 빼는 편이 낫다.
_RULE_MARKERS = ("금지어", "쓰지 않습니다", "사용 금지", "미사용", "노출 금지", "→ 스포츠클럽")


def _states_the_rule(line: str) -> bool:
    return any(m in line for m in _RULE_MARKERS)


def scan(rules: dict) -> list[dict]:
    terms = rules.get("terms", [])
    hits = []
    for path, rel in iter_files(rules):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lowered = text.lower()
        for t in terms:
            term = t["term"]
            if term.lower() not in lowered:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if term.lower() in line.lower() and not _states_the_rule(line):
                    hits.append(
                        {
                            "file": rel,
                            "line": lineno,
                            "term": term,
                            "replace": t.get("replace", ""),
                            "excerpt": line.strip()[:120],
                        }
                    )
    return hits


def self_check() -> None:
    """검사기가 실제로 잡는지 본다 — '한 번도 작동한 적 없는 장치'를 만들지 않으려는 최소 확인."""
    rules = load_rules()
    assert rules.get("terms"), "금지어 목록이 비었다"
    assert any("home" in g for g in rules.get("scan_globs", [])), (
        "대외 홈이 검사 범위에 없다 — instagram 만 보면 손님이 보는 화면을 영영 못 잡는다"
    )
    probe = {
        "terms": [{"term": "Premium Lifestyle Club", "replace": "Members-only Sports Club"}],
        "scan_globs": ["ssot/**"],
        "exclude_globs": [],
        "exclude_dir_names": [],
    }
    # 금지어 정본 자체에는 term 이 낱말로 적혀 있으므로 최소 1건은 반드시 잡혀야 한다.
    assert scan(probe), "스캐너가 아무것도 못 잡는다 — 범위나 확장자 필터를 보라"
    print("self-check OK · 금지어", len(rules["terms"]), "개 · 범위", rules["scan_globs"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args()
    if a.self_check:
        self_check()
        return 0

    rules = load_rules()
    hits = scan(rules)
    # 금지어 정본 파일 자신은 낱말을 정의하는 곳이라 걸림에서 뺀다.
    hits = [h for h in hits if h["file"] != "ssot/forbidden_terms.json"]
    if a.json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
    elif not hits:
        print("금지어 0건 — 검사 범위:", ", ".join(rules.get("scan_globs", [])))
    else:
        print(f"금지어 {len(hits)}건")
        for h in hits:
            print(f"  {h['file']}:{h['line']}  「{h['term']}」 → {h['replace']}")
            print(f"      {h['excerpt']}")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
