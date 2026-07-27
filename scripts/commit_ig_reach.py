# scripts/commit_ig_reach.py
# IG 도달·노출 수집 결과(원장+요약) 커밋 (배#588).
# ops/start_ig_reach_collect.bat 이 수집 직후 호출한다.
#
# [배125 · 2026-07-27 시모] 옛 구현은 `git pull --autostash` → 라이브 인덱스 `git add`
# → `git commit` → `git push` 를 직접 했다. 세 가지가 전부 이 저장소에서 금지된 방식이다.
#   · 수동 pull: 공용 작업트리에서 작업트리를 바꾸는 명령(사고 원인). push 는 워처 몫.
#   · 라이브 인덱스 add: 다른 세션이 stage 해둔 파일이 통째로 딸려 커밋된다(2026-07-23 5회 발생).
#   · 그리고 pull 이 실패하면 커밋을 통째로 건너뛰면서도 exit 0 을 냈다 — 예약작업은
#     '성공'으로 보이고 데이터는 안 올라간다(조용한 실패). 실측: 2026-07-22~27 6일 연속
#     'pull failed -> skip commit' + 'commit exit=0'. 그 사이 도달 원장은 매일 수집됐지만
#     저장소에는 2026-07-23 것이 마지막으로 남아, GM 이 보는 화면만 6일 뒤처졌다.
# 이제 커밋 관문 하나(safe_commit)에 넘긴다 — 임시 인덱스(read-tree HEAD)로 지정 경로만
# 담고, HEAD 재검증 + update-ref 원자 커밋, push 연계까지 그 안에서 처리된다(약속 L21).
# 실패는 여전히 비치명(로그만 남기고 exit 0) — 예약작업이 하드 에러로 죽지 않게.
# 단, '건너뜀'은 이제 로그에 이유가 분명히 남는다(조용한 실패 금지).

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

FILES = [
    "status/ig_reach_ledger.json",
    "3. 웰페리온 가이드/cmo/funnel/ig_reach_summary.json",
]


def main() -> int:
    try:
        from safe_commit import safe_commit
    except Exception as exc:
        print("[commit_ig_reach] safe_commit 임포트 실패 -> 커밋 건너뜀: %s" % exc)
        return 0

    try:
        res = safe_commit(
            [str(ROOT / f) for f in FILES],
            "auto(cmo): scheduled IG reach collect (ledger+summary, 배588)",
            holder="commit_ig_reach",
        )
    except Exception as exc:
        print("[commit_ig_reach] 커밋 예외 -> 건너뜀(수집 결과는 로컬에 남음): %s" % exc)
        return 0

    if not res.get("committed"):
        print("[commit_ig_reach] 커밋 없음 — %s" % (res.get("reason") or "사유 미상"))
        return 0

    print("[commit_ig_reach] 커밋 완료 sha=%s · 담긴 파일 %s"
          % (res.get("sha", "")[:9], res.get("changed") or []))
    if res.get("foreign"):
        print("[commit_ig_reach] ⚠️ 무관 경로 혼입 감지: %s" % res["foreign"])
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
