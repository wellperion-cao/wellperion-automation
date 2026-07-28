# scripts/commit_engagement.py
# ASCII-safe git committer for engagement files. Korean paths are handled
# inside Python (subprocess passes UTF-8 args), avoiding the CMD/CP949 .bat
# breakage. Called by ops/start_engagement_collect.bat after collection.
#
# Behavior: delegate to scripts/safe_commit.py (the repo's single commit gate)
# with ONLY the engagement files in scope. Failures are non-fatal (logged,
# exit 0) so the scheduled task never errors hard.
#
# 2026-07-28 (시모 아침 자가점검 #8): 여기 있던 손수 만든 pull->add->commit->push
# 를 safe_commit 호출로 바꿨다. 옛 코드는 맨 앞에서 `git pull --autostash` 를 돌리고
# 실패하면 커밋을 통째로 건너뛰며 exit 0 을 냈다 — 이 저장소는 detached HEAD 로 도는
# 구간이 있어 pull 이 "You are not currently on a branch" 로 죽었고, 그때부터
# 참여도 데이터가 2026-07-23 이후 5일간 로컬에만 쌓인 채 GM 화면은 옛 숫자를 보였다
# (조용한 실패 — 2026-07-27 'IG 도달 6일 미커밋'과 같은 부류).
# safe_commit 은 락 직렬화·임시 인덱스·HEAD 재검증·push 를 이미 다 하고
# detached HEAD 에서도 동작한다. 수동 pull 은 하지 않는다(공용 워크트리 규칙).

import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
FILES = [
    "3. 웰페리온 가이드/cmo/funnel/engagement/engagement_feed.json",
    "3. 웰페리온 가이드/cmo/funnel/engagement/danggn_snapshot.json",
    "3. 웰페리온 가이드/cmo/funnel/engagement/blog_snapshot.json",
    "status/ig_engagement_ledger.json",
]


def main() -> int:
    existing = [f for f in FILES if (ROOT / f).exists()]
    if not existing:
        print("[commit_engagement] no engagement files on disk -> nothing to commit")
        return 0

    try:
        from safe_commit import safe_commit
    except Exception as exc:
        print("[commit_engagement] safe_commit import failed: %s" % exc)
        return 0

    try:
        res = safe_commit(
            existing,
            "auto(cmo): scheduled engagement collect (danggn+blog+ig ledger)",
            holder="commit_engagement",
        )
    except Exception as exc:
        # 비치명 유지(예약작업이 하드 에러로 죽지 않게) — 단 옛 코드와 달리
        # 실패는 반드시 stdout 에 남는다. 조용한 건너뜀 금지.
        print("[commit_engagement] commit FAILED (non-fatal): %s" % exc)
        return 0

    if not isinstance(res, dict):
        print("[commit_engagement] unexpected result: %r" % (res,))
        return 0

    if not res.get("ok"):
        print("[commit_engagement] commit FAILED: %s" % (res.get("reason") or res))
    elif not res.get("committed"):
        print("[commit_engagement] no engagement changes -> nothing committed")
    else:
        print("[commit_engagement] committed sha=%s (%d files)"
              % (str(res.get("sha") or "")[:9], len(res.get("changed") or [])))
    for f in res.get("foreign") or []:
        print("[commit_engagement] ! 혼입 %s" % f)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
