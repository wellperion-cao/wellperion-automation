# -*- coding: utf-8 -*-
"""종합접수처 최종본 잠금 가드 (GM 지시 2026-09-05 · 시우).

정본 = status/reception_freeze.json 한 파일. locked=true 인 동안 그 파일의 paths 에 걸리는 스테이징 변경은
커밋을 막는다(exit 1). 같은 판정을 safe_commit(_HOOK_GUARDS)·.git/hooks/pre-commit 이 부르고,
wordpress_admin_playwright(주입·교체)·build_public_pages(공개 페이지 빌드)는 is_locked()/blocked_post() 를 부른다.
잠금 파일이 없거나 깨졌으면 통과(fail-open) — 가드 버그로 전 커밋이 막히면 안 된다.

시험: python scripts/precommit_reception_freeze_guard.py --paths "3. 웰페리온 가이드/coo/reception/reception_block.html"
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK = os.path.join(ROOT, "status", "reception_freeze.json")


def load():
    try:
        with open(LOCK, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def is_locked(d=None):
    d = d if d is not None else load()
    return bool(d.get("locked"))


def blocked_paths(paths, d=None):
    d = d if d is not None else load()
    if not is_locked(d):
        return []
    fr = [p.replace("\\", "/") for p in d.get("paths", [])]
    out = []
    for p in paths:
        q = p.replace("\\", "/")
        if any(q == f or (f.endswith("/") and q.startswith(f)) for f in fr):
            out.append(p)
    return out


def blocked_post(post_id, d=None):
    d = d if d is not None else load()
    try:
        return is_locked(d) and int(post_id) in set(d.get("wp_post_ids", []))
    except (TypeError, ValueError):
        return False


def message(hits):
    d = load()
    return ("[접수처 잠금] 종합접수처 최종본은 GM 지시(%s)로 잠겨 있습니다 — GM 외 수정 금지.\n  막힌 경로: %s\n"
            "  푸는 법: GM 이 '접수처 잠금 해제' 지시 → status/reception_freeze.json locked=false + unlocked_by 기록"
            % (d.get("by", ""), ", ".join(hits)))


def main():
    if "--paths" in sys.argv:
        staged = sys.argv[sys.argv.index("--paths") + 1:]
    else:
        try:
            r = subprocess.run(["git", "diff", "--cached", "--name-only", "-z"], cwd=ROOT,
                               capture_output=True, timeout=20)
            staged = [s for s in r.stdout.decode("utf-8", "replace").split("\0") if s]
        except Exception:
            return 0
    hits = blocked_paths(staged)
    if hits:
        print(message(hits), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
