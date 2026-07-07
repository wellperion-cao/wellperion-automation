# scripts/commit_ig_reach.py
# ASCII-safe git committer for IG reach/impressions files (배#588).
# Mirrors scripts/commit_engagement.py pattern: git pull --autostash -> add
# ONLY the reach ledger + summary (never -A) -> commit if staged -> push.
# All git failures are non-fatal (logged, exit 0) so the scheduled task
# never errors hard. Called by ops/start_ig_reach_collect.bat after collection.

import subprocess
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
FILES = [
    "status/ig_reach_ledger.json",
    "3. 웰페리온 가이드/cmo/funnel/ig_reach_summary.json",
]


def _run(args):
    return subprocess.run(
        args, cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )


def main() -> int:
    pull = _run(["git", "pull", "--autostash"])
    print("[commit_ig_reach] pull rc=%s %s" % (pull.returncode, ((pull.stderr or pull.stdout) or "").strip()[-200:]))
    if pull.returncode != 0:
        print("[commit_ig_reach] pull failed -> skip commit")
        return 0

    _run(["git", "add"] + FILES)
    staged = _run(["git", "diff", "--cached", "--quiet"])
    if staged.returncode == 0:
        print("[commit_ig_reach] no reach changes -> skip commit")
        return 0

    commit = _run(["git", "commit", "-m", "auto(cto): scheduled IG reach collect (ledger+summary, 배588)"])
    print("[commit_ig_reach] commit rc=%s %s" % (commit.returncode, ((commit.stdout or commit.stderr) or "").strip()[-200:]))
    if commit.returncode != 0:
        print("[commit_ig_reach] commit failed -> skip push")
        return 0

    push = _run(["git", "push"])
    print("[commit_ig_reach] push rc=%s %s" % (push.returncode, ((push.stderr or push.stdout) or "").strip()[-200:]))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
