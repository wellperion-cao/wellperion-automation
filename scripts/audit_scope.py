#!/usr/bin/env python3
"""차등 점검(Differential Audit) 산출 스크립트.

status/audit_registry.json(안정 대장)과 git 커밋 이력을 대조해
가이드 html 페이지를 new(신규) / changed(변경) / stable_skipped(안정·제외)로 분류한다.
읽기 전용(라이브 부작용 0) — --seed 를 줄 때만 레지스트리에 신규 항목을 추가한다.

사용:
  python scripts/audit_scope.py           # 사람이 읽는 요약
  python scripts/audit_scope.py --json    # {"new":[...], "changed":[...], "stable_skipped":N}
  python scripts/audit_scope.py --seed    # registry에 없는 파일만 stable@HEAD로 신규 등록(기존 항목 불변)

판정 기준 (.omc/specs/differential-audit-autonomy.md):
  신규 = 안정 대장에 없음 → 딥 점검 대상
  변경 = 대장 등록(audited_commit) 이후 그 파일이 다시 커밋됨 → 좁은 점검 대상
  안정 = 대장 등록 + 이후 무변경 → 제외
"""
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "status" / "audit_registry.json"
GUIDE_PATTERN = "3. 웰페리온 가이드/*.html"  # git wildmatch: * 가 디렉터리 경계 없이 재귀 매치(하위 전부 포함)


def _git(args):
    out = subprocess.run(["git", "-C", str(REPO_ROOT)] + args, capture_output=True, check=True)
    return out.stdout


def tracked_guide_pages():
    raw = _git(["ls-files", "-z", GUIDE_PATTERN])
    return sorted(p for p in raw.decode("utf-8").split("\0") if p)


def head_sha():
    return _git(["rev-parse", "HEAD"]).decode().strip()


def load_registry():
    if not REGISTRY_PATH.exists():
        return {"_doc": "차등 점검 안정 대장 — audited_commit 이후 변경분만 재점검 대상", "pages": []}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def save_registry(registry):
    REGISTRY_PATH.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def has_commits_since(audited_commit, path):
    """audited_commit 이후 그 파일을 건드린 커밋이 있으면 True."""
    out = _git(["log", "--oneline", f"{audited_commit}..HEAD", "--", path])
    return bool(out.strip())


def classify(registry):
    by_path = {p["path"]: p for p in registry.get("pages", [])}
    new, changed = [], []
    stable_skipped = 0
    for path in tracked_guide_pages():
        entry = by_path.get(path)
        if entry is None:
            new.append(path)
        elif entry.get("status") == "stable" and has_commits_since(entry["audited_commit"], path):
            changed.append(path)
        else:
            stable_skipped += 1
    return {"new": new, "changed": changed, "stable_skipped": stable_skipped}


def seed():
    registry = load_registry()
    existing = {p["path"] for p in registry.get("pages", [])}
    sha = head_sha()
    added = 0
    for path in tracked_guide_pages():
        if path in existing:
            continue
        registry.setdefault("pages", []).append(
            {"path": path, "audited_commit": sha, "status": "stable", "note": "baseline seed 2026-07-03"}
        )
        added += 1
    save_registry(registry)
    return added


def main():
    args = sys.argv[1:]
    if "--seed" in args:
        added = seed()
        print(f"seeded {added} new page(s) into {REGISTRY_PATH}")
        return
    result = classify(load_registry())
    if "--json" in args:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"신규(딥점검 대상): {len(result['new'])}")
        for p in result["new"]:
            print(f"  + {p}")
        print(f"변경(좁은점검 대상): {len(result['changed'])}")
        for p in result["changed"]:
            print(f"  ~ {p}")
        print(f"안정(제외): {result['stable_skipped']}")


if __name__ == "__main__":
    main()
