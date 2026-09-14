# -*- coding: utf-8 -*-
"""나우열M 라인(CHRO·CFO) 절대 접촉 금지 pre-commit 가드 (GM 지시 2026-09-14 · 웰리).

GM 원문(2026-09-14 12:5x): "일단 CHRO + CFO건은 건드리지말고, 나우열M 요청해서
진행하게끔 박제시켜줘 이건 절대 건드리지못하게해줘".

정본 = scripts/safe_commit.py 의 CHRO_DOMAIN_PATHS·CFO_DOMAIN_PATHS·_path_matches_any·
_nawoolm_request_marker(그대로 import — 로직 복제 금지). 두 경로에서 이 스크립트를 쓴다:
  ① safe_commit(commit-tree/update-ref)은 git 훅이 안 걸려 scripts/safe_commit.py
     _HOOK_GUARDS 로 이식 — 이땐 GIT_INDEX_FILE 로 임시 인덱스가 넘어오고, 실제 커밋
     메시지는 env WP_COMMIT_MESSAGE 로 넘어온다(§safe_commit._run_hook_guards 주석 —
     .git/COMMIT_EDITMSG 는 "이번" 메시지를 담고 있지 않을 수 있어서 안 씀).
  ② 맨손 `git commit` 경로는 .git/hooks/pre-commit 이 이 스크립트를 직접 부른다. 이땐
     WP_COMMIT_MESSAGE 가 없고, pre-commit 훅 시점엔 git 이 아직 커밋 메시지를
     COMMIT_EDITMSG 에 확정해 두지 않은 경우가 많다(prepare-commit-msg 가 그 뒤에
     돈다) — 그래서 이 경로는 사실상 마커를 못 읽는 편이 정상이고, 그러면 항상
     차단이 뜬다. 나우열M 요청 건은 **safe_commit 경유로 진행**하라고 안내한다
     (safe_commit 은 message 인자를 그대로 받아 마커를 정확히 본다).

통과 조건: 걸린 경로가 없거나, 커밋 메시지에 [나우열M 요청 YYYY-MM-DD](오늘 이내 날짜)
마커가 있을 것. WP_DOMAIN_FORCE 는 더 이상 안 먹는다(2026-09-14 GM 지시로 폐지 — 이
가드는 애초에 그 env 를 아예 읽지 않는다).

시험: python scripts/precommit_nawoolm_domain_guard.py --selftest
"""
import os
import subprocess
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from safe_commit import (  # noqa: E402
    CHRO_DOMAIN_PATHS,
    CFO_DOMAIN_PATHS,
    _path_matches_any,
    _nawoolm_request_marker,
    _domain_guard_log,
    _committer_is_nawoolm,
)

ROOT = os.path.dirname(_SCRIPTS_DIR)


def _staged_paths(explicit=None):
    if explicit is not None:
        return list(explicit)
    try:
        r = subprocess.run(["git", "diff", "--cached", "--name-only", "-z"],
                            cwd=ROOT, capture_output=True, timeout=20)
        return [p for p in r.stdout.decode("utf-8", "replace").split("\0") if p]
    except Exception:
        return []


def _commit_message(explicit=None):
    """실제 커밋 메시지 — env WP_COMMIT_MESSAGE(safe_commit 경유) > explicit(--message)
    > .git/COMMIT_EDITMSG(맨손 git commit, 위 모듈 docstring 의 한계 그대로)."""
    env_msg = os.environ.get("WP_COMMIT_MESSAGE")
    if env_msg:
        return env_msg
    if explicit is not None:
        return explicit
    path = os.path.join(ROOT, ".git", "COMMIT_EDITMSG")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def hits_and_role(paths):
    """[(경로, 역할표기), ...] — 나우열M 라인에 걸린 경로만(없으면 빈 리스트)."""
    out = []
    for p in paths:
        q = p.replace("\\", "/")
        if _path_matches_any(q, CHRO_DOMAIN_PATHS):
            out.append((q, "CHRO(시로)"))
        elif _path_matches_any(q, CFO_DOMAIN_PATHS):
            out.append((q, "CFO(시뽀)"))
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    explicit_paths = argv[argv.index("--paths") + 1:] if "--paths" in argv else None
    explicit_message = None
    if "--message" in argv:
        i = argv.index("--message")
        explicit_message = argv[i + 1] if i + 1 < len(argv) else ""

    hits = hits_and_role(_staged_paths(explicit_paths))
    if not hits:
        return 0

    hit_paths = [p for p, _ in hits]
    if _committer_is_nawoolm():       # 나우열M PC(user.name 나우열) = 자기 라인 — 통과(CHRO 요청 2026-09-14)
        _domain_guard_log("nawoolm_domain_precommit_self", hit_paths, ROOT)
        print(f"[INFO] 나우열M 본인 저장 — pre-commit 나우열M 라인 가드 통과: {', '.join(hit_paths)}")
        return 0
    marker = _nawoolm_request_marker(_commit_message(explicit_message))
    if marker:
        _domain_guard_log("nawoolm_domain_precommit_marker", hit_paths, ROOT)
        print(f"[WARN] 나우열M 요청 마커 {marker} — pre-commit 나우열M 라인 가드 통과: "
              f"{', '.join(hit_paths)}")
        return 0

    _domain_guard_log("nawoolm_domain_precommit_block", hit_paths, ROOT)
    shown = ", ".join(hit_paths[:10])
    extra = f" 외 {len(hit_paths) - 10}건" if len(hit_paths) > 10 else ""
    sys.stderr.write(
        "\n"
        "============================================================\n"
        "[nawoolm-domain-guard] 커밋 차단 — 나우열M 라인(인사·재무) 파일입니다\n"
        "------------------------------------------------------------\n"
        f"  막힌 경로: {shown}{extra}\n"
        "------------------------------------------------------------\n"
        "  AI 는 이 경로를 직접 수정하지 않습니다(GM 확정 2026-09-14).\n"
        "  나우열M 이 업무관리(텔레그램) 방에서 요청한 건이면 커밋 제목에\n"
        "  [나우열M 요청 YYYY-MM-DD](오늘 날짜)를 붙여 scripts/safe_commit.py 로\n"
        "  커밋하세요 — 우회 스위치는 없습니다(WP_DOMAIN_FORCE 폐지).\n"
        "============================================================\n"
    )
    return 1


def _selftest() -> None:
    from datetime import datetime
    cfo_path = "3. 웰페리온 가이드/cfo/finance/매출현황.html"
    today = datetime.now().date().isoformat()

    os.environ.pop("WP_COMMIT_MESSAGE", None)
    os.environ.pop("WP_DOMAIN_FORCE", None)
    os.environ["GIT_COMMITTER_NAME"] = "Wellperion GM"   # 나우열M PC(user.name 나우열)에서도 ①~④ 가 같은 답을 내게 고정(2026-09-14 CFO 발견) · ⑤ 가 끝에 지운다
    try:
        # ① cfo 파일 수정 → 차단
        assert main(["--paths", cfo_path, "--message", "그냥 수정"]) == 1, "① cfo 파일 수정이 안 막혔다"
        # ② 마커 있으면 통과
        assert main(["--paths", cfo_path, "--message",
                     f"[나우열M 요청 {today}] 재무 화면 수정"]) == 0, "② 마커가 있는데도 막혔다"
        # ③ WP_DOMAIN_FORCE=CFO 로도 차단(우회 폐지 확인)
        os.environ["WP_DOMAIN_FORCE"] = "CFO"
        assert main(["--paths", cfo_path, "--message", "그냥 수정"]) == 1, \
            "③ WP_DOMAIN_FORCE 로 우회됐다(폐지됐어야 함)"
    finally:
        os.environ.pop("WP_DOMAIN_FORCE", None)
        os.environ.pop("WP_COMMIT_MESSAGE", None)

    # ④ chro 밖 파일은 통과
    assert main(["--paths", "scripts/some_unrelated_tool.py", "--message", "그냥 수정"]) == 0, \
        "④ 무관 파일이 막혔다"
    # ⑤ 나우열M 본인(user.name 나우열) 저장은 마커 없이 통과 — 나우열M PC 의 CHRO·CFO 세션 전부
    os.environ["GIT_COMMITTER_NAME"] = "나우열"
    try:
        assert main(["--paths", cfo_path, "--message", "그냥 수정"]) == 0, "⑤ 나우열M 본인 저장이 막혔다"
    finally:
        os.environ.pop("GIT_COMMITTER_NAME", None)
    print("[selftest] nawoolm_domain_guard 5케이스 OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
        sys.exit(0)
    sys.exit(main())
