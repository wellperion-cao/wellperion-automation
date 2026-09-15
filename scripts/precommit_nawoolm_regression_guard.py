"""나우열M 이 최근에 넣은 줄을 지우는 커밋 차단 — 공용 파일 낡은 사본 덮어쓰기 사고 가드.

무슨 사고인가(2026-09-14 · 두 번째):
  · 9/11 — CFO 화면 되돌리기에 나우열M 요청분(품의 승인 메뉴 삭제·합침)까지 함께 되돌아감.
  · 9/14 14:08 — 시모가 콘텐츠 접수 창구를 고치며 `wellperion_guide(main).html` 의 낡은 작업트리 사본을
    통째로 올려, 나우열M 이 12:22 에 통합한 구매요청 메뉴(품의 승인 흡수)가 되살아남.
  나우열M: "cmo 가 공용파일을 덮어쓰면서 나오는 사고 … 수정해도 cmo 가 작업하면 계속 문제가 되는 상황이라 조치가 필요합니다".

경로 가드(precommit_nawoolm_domain_guard.py)는 나우열M 라인 폴더만 본다 — 공용 파일(ERP 메인·모듈 목록 등)은
누구나 고치는 곳이라 경로로는 못 막는다. 그래서 이 가드는 경로가 아니라 **줄**을 본다:
  staged 삭제 줄(`git diff --cached -U0` 의 '-') 가운데, 최근 30일 안에 나우열M(author 나우열) 커밋이
  **추가한 줄**과 글자 그대로 같은 줄이 있으면 커밋을 막는다.
  (같은 파일 안에서만 대조 · 공백만 다른 줄은 같은 줄 · 20자 미만 짧은 줄은 뺀다 — `</div>` 같은 줄로 헛경보 금지)

통과 = 커밋 메시지 `[나우열M 요청 YYYY-MM-DD]` 마커(safe_commit._nawoolm_request_marker · 경로 가드와 같은 열쇠)
     또는 GM 열쇠 `[GM 승인 YYYY-MM-DD]` + GM 이 직접 친 「승인」 접수(safe_commit._gm_key · GM 확정 2026-09-15).
우회 env 없음. 가드 오류·git 없음 = fail-open(통과) — 다른 pre-commit 가드와 같은 규약.

막혔을 때 할 일 = 작업트리가 낡은 사본이다. `git show HEAD:<파일>` 로 최신을 읽고, 내 변경만 Edit 로 다시 적용한다
(파일 통째 Write 금지 · 메모리 feedback_never_whole_file_rewrite_use_edit_tool).

실행:  pre-commit 훅 ⑦-3 · safe_commit._HOOK_GUARDS("nawoolm_regression")
       python scripts/precommit_nawoolm_regression_guard.py --selftest      (임시 저장소로 막힘·마커 통과 확인)
       python scripts/precommit_nawoolm_regression_guard.py --audit <sha>   (지난 커밋이 이 가드에 걸렸을지 — 사고 재현)
"""
import os
import subprocess
import sys
import tempfile

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from safe_commit import _nawoolm_request_marker, _committer_is_nawoolm, _gm_key  # noqa: E402
from precommit_nawoolm_domain_guard import _staged_paths, _commit_message  # noqa: E402

ROOT = os.path.dirname(_SCRIPTS_DIR)
AUTHOR = "나우열"
SINCE = "30.days"   # 낡은 사본이 2주 넘게 묵은 경우까지(세션 재시작 전 사본)
MIN_LEN = 20          # 이보다 짧은 줄은 대조하지 않는다(`</div>`·`}` 류 헛경보 방지)
# 기계가 통째로 다시 쓰는 상태 파일은 대조하지 않는다 — 큐·원장·로그는 줄 단위 「덮어쓰기」가 정상 동작이라
#   누가 넣은 줄이든 다음 저장에서 사라진다(2026-09-14 17:48 실측: status/_queue.json 저장이 이 가드에 막혔다).
SKIP_SUFFIX = (".json", ".jsonl", ".log")
SKIP_PREFIX = ("status/", "3. 웰페리온 가이드/status/", "logs/")


def is_state_file(path):
    p = path.replace("\\", "/")
    return p.endswith(SKIP_SUFFIX) and p.startswith(SKIP_PREFIX)


def _git(args, cwd):
    r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, timeout=25)
    return r.stdout.decode("utf-8", "replace")


def _norm(line):
    return " ".join(line.split())


def removed_lines(cwd, path, rev=None):
    """staged(-U0) 에서 지워지는 줄. rev 를 주면 그 커밋이 부모 대비 지운 줄(--audit)."""
    args = ["diff", "-U0", "--no-color"]
    args += [rev + "^", rev] if rev else ["--cached"]
    out = _git(args + ["--", path], cwd)
    res = set()
    for ln in out.splitlines():
        if ln.startswith("-") and not ln.startswith("---"):
            n = _norm(ln[1:])
            if len(n) >= MIN_LEN:
                res.add(n)
    return res


def nawoolm_added_lines(cwd, path, before=None):
    """최근 30일 나우열M 커밋이 이 파일에 추가한 줄 → {줄: 'sha 제목'}. before = --audit 때 그 커밋 이전만."""
    args = ["log", "--author=" + AUTHOR, "--since=" + SINCE, "-p", "-U0", "--no-color",
            "--format=@@commit %h %s"]
    if before:
        args.append(before + "^")
    out = _git(args + ["--", path], cwd)
    added, cur = {}, ""
    for ln in out.splitlines():
        if ln.startswith("@@commit "):
            cur = ln[len("@@commit "):]
        elif ln.startswith("+") and not ln.startswith("+++"):
            n = _norm(ln[1:])
            if len(n) >= MIN_LEN:
                added.setdefault(n, cur)
    return added


def find_hits(cwd, paths, rev=None):
    hits = []
    for p in paths:
        if is_state_file(p):
            continue
        rem = removed_lines(cwd, p, rev)
        if not rem:
            continue
        added = nawoolm_added_lines(cwd, p, before=rev)
        for line in sorted(rem & set(added)):
            hits.append((p, added[line], line))
    return hits


def _report(hits, marker=None):
    if marker:
        print("[WARN] 나우열M 요청 마커 %s — 나우열M 줄 %d개를 지우는 커밋을 통과시킴" % (marker, len(hits)))
        return
    sys.stderr.write(
        "\n============================================================\n"
        "[nawoolm-regression-guard] 커밋 차단 — 나우열M 이 최근에 넣은 줄이 지워집니다\n"
        "  작업트리가 낡은 사본입니다(공용 파일 덮어쓰기 · 2026-09-14 시모 사고와 같은 모양).\n")
    seen = set()
    for p, commit, line in hits[:12]:
        key = (p, commit)
        if key not in seen:
            seen.add(key)
            sys.stderr.write("  · %s ← 나우열M 커밋 %s\n" % (p, commit))
        sys.stderr.write("      - %s\n" % line[:110])
    if len(hits) > 12:
        sys.stderr.write("  … 외 %d줄\n" % (len(hits) - 12))
    sys.stderr.write(
        "  할 일: git show HEAD:<파일> 로 최신을 읽고 내 변경만 Edit 로 다시 적용 → 다시 저장.\n"
        "  나우열M 이 직접 부탁한 되돌리기면 커밋 제목에 [나우열M 요청 YYYY-MM-DD] 마커.\n"
        "============================================================\n")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        return selftest()
    if "--audit" in argv:
        sha = argv[argv.index("--audit") + 1]
        paths = [p for p in _git(["show", "--name-only", "--format=", sha], ROOT).splitlines() if p]
        hits = find_hits(ROOT, paths, rev=sha)
        print("[audit] %s — 나우열M 줄 삭제 %d건" % (sha, len(hits)))
        for p, commit, line in hits:
            print("  %s ← %s\n      - %s" % (p, commit, line[:100]))
        return 1 if hits else 0
    explicit_paths = argv[argv.index("--paths") + 1:] if "--paths" in argv else None
    explicit_message = None
    if "--message" in argv:
        i = argv.index("--message")
        explicit_message = argv[i + 1] if i + 1 < len(argv) else ""
    if _committer_is_nawoolm():       # 나우열M PC = 모든 세션이 「나우열」로 저장 — 자기 줄은 자기가 지운다(통과)
        return 0
    try:
        hits = find_hits(ROOT, _staged_paths(explicit_paths))
    except Exception as e:  # noqa: BLE001 — 가드 오류 = fail-open
        print("[nawoolm-regression-guard][WARN] 가드 오류 — 통과: %s" % e)
        return 0
    if not hits:
        return 0
    # [GM 지시] 마커는 여기서 안 통한다(allow_gm=False) — 2026-09-15 10:39 낡은 사본 커밋이 은퇴 화면 2장을 되살린 사고.
    msg = _commit_message(explicit_message)
    marker = _nawoolm_request_marker(msg, allow_gm=False)
    # GM 열쇠(2026-09-15 GM 확정) — GM 이 직접 「승인」이라 친 접수 + 오늘 날짜 [GM 승인] 마커 둘 다 있을 때만.
    if not marker:
        marker = _gm_key(msg)
    _report(hits, marker)
    return 0 if marker else 1


def selftest():
    """임시 저장소 — 나우열 커밋이 넣은 줄을 낡은 사본이 지우면 막히고, 마커가 있으면 통과."""
    with tempfile.TemporaryDirectory() as d:
        def g(*a, **env):
            e = dict(os.environ, **env)
            subprocess.run(["git"] + list(a), cwd=d, check=True, capture_output=True, env=e)
        g("init", "-q")
        g("config", "user.email", "t@t"); g("config", "user.name", "Wellperion GM")
        f = os.path.join(d, "main.html")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write('<a href="cfo/finance/지출품의.html">구매요청</a>\n<div>\n</div>\n')
        g("add", "."); g("commit", "-q", "-m", "base")
        with open(f, "w", encoding="utf-8") as fh:      # 나우열M 이 메뉴를 통합
            fh.write('<a href="cfo/finance/매출지출현황.html?req=1">구매요청 — 통합 메뉴</a>\n<div>\n</div>\n')
        g("add", "."); g("commit", "-q", "-m", "구매요청 통합",
                         GIT_AUTHOR_NAME="나우열", GIT_AUTHOR_EMAIL="n@w")
        with open(f, "w", encoding="utf-8") as fh:      # 다른 세션이 낡은 사본을 통째로 올림
            fh.write('<a href="cfo/finance/지출품의.html">구매요청</a>\n<div>\n</div>\n<!-- 시모 콘텐츠 -->\n')
        g("add", ".")
        hits = find_hits(d, ["main.html"])
        assert len(hits) == 1 and "통합 메뉴" in hits[0][2] and "구매요청 통합" in hits[0][1], hits
        # 짧은 줄(<div>)은 대조 안 함 · 나우열 줄을 안 지우는 커밋은 통과
        with open(f, "w", encoding="utf-8") as fh:
            fh.write('<a href="cfo/finance/매출지출현황.html?req=1">구매요청 — 통합 메뉴</a>\n<div>\n</div>\n<!-- 시모 콘텐츠 -->\n')
        g("add", ".")
        assert find_hits(d, ["main.html"]) == []
        assert _nawoolm_request_marker("복구 [나우열M 요청 2026-09-14]") is not None
    assert is_state_file("status/_queue.json") and is_state_file("3. 웰페리온 가이드/status/token_usage.json") and is_state_file("logs/x.log")
    assert not is_state_file("scripts/a.py") and not is_state_file("status/briefs/x.md") and not is_state_file("3. 웰페리온 가이드/cfo/finance/x.html")
    os.environ["GIT_COMMITTER_NAME"] = "나우열"      # 나우열M 본인 저장은 판정 없이 통과
    try:
        assert main([]) == 0
    finally:
        os.environ.pop("GIT_COMMITTER_NAME", None)
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
