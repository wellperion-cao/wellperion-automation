# scripts/commit_engagement.py
# ASCII-safe git committer for engagement files. Korean paths are handled
# inside Python (subprocess passes UTF-8 args), avoiding the CMD/CP949 .bat
# breakage. Called by ops/start_engagement_collect.bat after collection.
#
# Behavior: git pull --autostash -> add ONLY the 3 engagement files
# (never -A) -> commit if staged changes exist -> push. All git failures
# are non-fatal (logged, exit 0) so the scheduled task never errors hard.

import subprocess
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
FILES = [
    "3. 웰페리온 가이드/cmo/funnel/engagement/engagement_feed.json",
    "3. 웰페리온 가이드/cmo/funnel/engagement/danggn_snapshot.json",
    "3. 웰페리온 가이드/cmo/funnel/engagement/blog_snapshot.json",
    "status/ig_engagement_ledger.json",
]


def _run(args):
    return subprocess.run(
        args, cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )


def main() -> int:
    pull = _run(["git", "pull", "--autostash"])
    print("[commit_engagement] pull rc=%s %s" % (pull.returncode, ((pull.stderr or pull.stdout) or "").strip()[-200:]))
    if pull.returncode != 0:
        print("[commit_engagement] pull failed -> skip commit")
        return 0

    _run(["git", "add"] + FILES)
    staged = _run(["git", "diff", "--cached", "--quiet"])
    if staged.returncode == 0:
        print("[commit_engagement] no engagement changes -> skip commit")
        return 0

    commit = _run(["git", "commit", "-m", "auto(cmo): scheduled engagement collect (danggn+blog+ig ledger)"])
    print("[commit_engagement] commit rc=%s %s" % (commit.returncode, ((commit.stdout or commit.stderr) or "").strip()[-200:]))
    if commit.returncode != 0:
        print("[commit_engagement] commit failed -> skip push")
        return 0

    push = _run(["git", "push"])
    print("[commit_engagement] push rc=%s %s" % (push.returncode, ((push.stderr or push.stdout) or "").strip()[-200:]))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
