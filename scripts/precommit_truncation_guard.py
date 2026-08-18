#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
precommit_truncation_guard.py — 커밋 전 truncation(대량 라인 유실) 차단 가드

배경 (2026-06-13 AI CTO):
  운영부 체계.html 이 stale 사본으로 덮어써져 3394→1908 줄(약 1486줄 유실)이
  검증 없이 커밋된 사고 재발 방지. 모든 커밋 경로(clevel.bat 자동커밋 + 에이전트
  직접 git commit)를 .git/hooks/pre-commit 에서 본 스크립트를 호출해 보호한다.

동작:
  staged 된 *.html · *.js 파일에 대해, HEAD 버전 대비 라인수가
  급감(30% 이상 AND 200줄 이상 감소)하면 커밋을 중단(exit 1)하고
  어느 파일이 몇 줄 → 몇 줄인지 한글로 경고한다.

안전 규칙 (fail-open):
  - 신규 파일(HEAD에 없음)          → 통과
  - 전체 삭제(staged 에서 제거됨)    → 통과 (의도적 삭제)
  - HEAD 가 200줄 미만인 작은 파일   → 통과 (소형 파일 비율 노이즈 방지)
  - 가드 자체가 에러나면             → 통과(exit 0). 가드 버그로 전 커밋이
                                       막히면 안 됨.
  - 의도적 대량삭제 우회             → git commit --no-verify

  ※ exit 1 = 차단(truncation 감지). exit 0 = 통과(정상/에러 fail-open).
"""

import subprocess
import sys

# PASS/WARN/BLOCK 판정 로그 — 여러 가드 공용(2026-08-17, scripts/precommit_
# phantom_delete_guard.py 참조). import 실패해도 가드는 그대로 동작(fail-soft).
try:
    from precommit_phantom_delete_guard import log_guard_decision
except Exception:
    def log_guard_decision(*_a, **_kw):
        pass

# ── 임계값 (둘 다 충족해야 차단) ──────────────────────────────────────────
SHRINK_RATIO = 0.30      # 30% 이상 감소
SHRINK_LINES = 200       # AND 200줄 이상 감소
MIN_HEAD_LINES = 200     # HEAD 가 이보다 작으면 비율 판정 스킵(소형파일 노이즈)
WATCH_SUFFIXES = (".html", ".js")

# ── 충돌 다발 파일 — 기준을 낮춰 잡는다 (2026-08-18 시우) ──────────────────────
# 위 30%/200줄 기준은 '파일이 통째로 잘린' 사고용이다. 종합접수처 두 파일에서
# 실제로 난 사고는 그보다 작다: 여러 세션이 같은 파일을 각자 들고 있던 옛 전체본으로
# 덮어써 기능 단위(70~90줄)만 조용히 사라졌다. 2026-08-16 41480f4 가 이미 한 번
# 재적용이었고, 2026-08-18 cd50bb4(76줄 삭제)·630bf0f(86줄 삭제)에서 또 났다.
# 두 번 같은 자리에서 났으므로 문서가 아니라 이 관문에서 잡는다(약속 L02·L21 —
# 새 가드 파일을 만들지 않고 이미 모든 커밋이 지나가는 여기에 조건 하나만 얹는다).
# 우회는 기존과 동일: git commit --no-verify
HOT_PREFIXES = ("3. 웰페리온 가이드/coo/reception/",)
HOT_SHRINK_RATIO = 0.02   # 2% 이상 감소
HOT_SHRINK_LINES = 40     # AND 40줄 이상 감소 (실사고 76·86줄보다 낮게)


def _is_hot(disp: str) -> bool:
    """충돌 다발 경로인지(경로 구분자는 git 출력 기준 '/')."""
    return disp.startswith(HOT_PREFIXES)


def over_threshold(disp: str, head_lines: int, dropped: int) -> bool:
    """이 감소폭을 차단으로 볼지. 순수함수 — git 미의존이라 그대로 자가검사한다."""
    if head_lines < MIN_HEAD_LINES or dropped <= 0:
        return False
    ratio = dropped / head_lines
    if _is_hot(disp):
        return ratio >= HOT_SHRINK_RATIO and dropped >= HOT_SHRINK_LINES
    return ratio >= SHRINK_RATIO and dropped >= SHRINK_LINES


# ── 최근 작업 삭제 차단 (2026-08-18 시우 · 위 줄수 기준의 구멍을 메운다) ────────
# 줄수 기준만으로는 '옛 사본으로 덮기'를 다 못 잡는다. 옛 사본 위에 자기 수정을 얹어
# 커밋하면 순 삭제가 작아져 그대로 통과한다(실제로 그렇게 두 번 통과했다). 사고의 본질은
# 줄이 몇 개 줄었느냐가 아니라 **며칠 전 남이 넣은 것을 지웠느냐**다. 그래서 지워지는
# 줄이 언제 들어온 줄인지를 본다 — 최근 것을 여러 줄 지우면 차단한다.
# safe_commit 도 같은 이름의 가드를 재실행하므로 커밋 경로 둘 다 이 판정을 지난다.
# 우회: git commit --no-verify (의도적 되돌리기·리팩터)
RECENT_DAYS = 7            # 이 기간 안에 들어온 줄을 '최근 작업'으로 본다
RECENT_DELETE_LINES = 10   # 최근 줄을 이만큼 지우면 차단(오탐 방지용 하한)


def _blame_times(path: str, rev: str = "HEAD"):
    """rev 시점 파일의 각 줄이 언제 들어왔는지(epoch 초) 리스트로. 실패하면 None."""
    out = subprocess.run(
        ["git", "blame", "--line-porcelain", rev, "--", path],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    if out.returncode != 0 or not out.stdout:
        return None
    times = []
    for line in out.stdout.split(b"\n"):
        if line.startswith(b"author-time "):
            try:
                times.append(int(line.split(b" ", 1)[1]))
            except Exception:
                times.append(0)
    return times or None


def removed_line_numbers(head_text: str, new_text: str):
    """HEAD 에는 있는데 새 내용에선 사라진 줄의 번호(1부터). 순수함수 — 자가검사 대상."""
    import difflib
    a = head_text.splitlines()
    b = new_text.splitlines()
    gone = []
    for tag, i1, i2, _j1, _j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("delete", "replace"):
            gone.extend(range(i1 + 1, i2 + 1))
    return gone


def recent_deletions(path: str, head_text: str, new_text: str, now: int, rev: str = "HEAD") -> int:
    """이번 변경이 지우는 줄 중 최근 RECENT_DAYS 안에 들어온 줄의 개수."""
    gone = removed_line_numbers(head_text, new_text)
    if len(gone) < RECENT_DELETE_LINES:
        return 0  # 애초에 하한 미만이면 blame 비용도 쓰지 않는다
    times = _blame_times(path, rev)
    if not times:
        return 0  # blame 실패 = fail-open
    cutoff = now - RECENT_DAYS * 86400
    return sum(1 for n in gone if n <= len(times) and times[n - 1] >= cutoff)


def selfcheck() -> int:
    """실사고 값으로 판정을 확인한다: python precommit_truncation_guard.py --selfcheck"""
    hot_html = "3. 웰페리온 가이드/coo/reception/종합접수처_현황.html"
    hot_js = "3. 웰페리온 가이드/coo/reception/apps_script_reception.js"
    other = "3. 웰페리온 가이드/cpo/member/membership.html"
    # 2026-08-18 실사고 두 건 — 반드시 잡혀야 한다
    assert over_threshold(hot_html, 1602, 76), "cd50bb4(76줄)을 못 잡는다"
    assert over_threshold(hot_js, 2740, 86), "630bf0f(86줄)을 못 잡는다"
    # 같은 파일의 정상 소폭 편집은 통과해야 한다
    assert not over_threshold(hot_html, 1602, 12), "12줄 정리까지 막으면 오탐이다"
    # 다발 경로가 아닌 파일은 옛 기준 그대로
    assert not over_threshold(other, 2000, 86), "다발 경로 밖 기준이 바뀌었다"
    assert over_threshold(other, 2000, 700), "옛 기준(30%·200줄)이 깨졌다"

    # 지워지는 줄 번호 뽑기 — 순수함수라 그대로 확인한다
    assert removed_line_numbers("a\nb\nc\n", "a\nc\n") == [2], "사라진 줄 번호를 못 짚는다"
    assert removed_line_numbers("a\nb\n", "a\nb\nc\n") == [], "추가만 했는데 삭제로 본다"

    # 실사고 재생 — 그때 그 커밋을 지금 이 가드에 다시 통과시켜 본다
    replays = [
        ("cd50bb4", "3. 웰페리온 가이드/coo/reception/종합접수처_현황.html"),
        ("630bf0f", "3. 웰페리온 가이드/coo/reception/apps_script_reception.js"),
    ]
    replayed = 0
    for sha, path in replays:
        got = subprocess.run(["git", "show", "-s", "--format=%ct", sha],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if got.returncode != 0:
            continue  # 이력이 없는 사본 저장소 — 건너뜀(fail-open)
        when = int(got.stdout.strip())
        old = subprocess.run(["git", "show", sha + "^:" + path], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL).stdout.decode("utf-8", "replace")
        newv = subprocess.run(["git", "show", sha + ":" + path], stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL).stdout.decode("utf-8", "replace")
        n = recent_deletions(path, old, newv, when, rev=sha + "^")
        assert n >= RECENT_DELETE_LINES, f"{sha} 를 여전히 통과시킨다(최근 삭제 {n}줄)"
        replayed += 1
        print(f"  재생 {sha}: 최근 {RECENT_DAYS}일 내 줄 {n}개 삭제 → 차단 확인")

    print(f"[truncation-guard] 자가검사 7항목 통과 (실사고 재생 {replayed}/2)")
    return 0


def run(args):
    """git 명령 실행 → (returncode, stdout_bytes)."""
    proc = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.returncode, proc.stdout


def count_lines(blob_bytes):
    """blob 바이트의 라인 수. 빈 내용=0."""
    if not blob_bytes:
        return 0
    # 마지막 줄에 개행이 없어도 1줄로 카운트되도록 splitlines 사용.
    return len(blob_bytes.splitlines())


def staged_files():
    """
    staged 파일 목록을 (status, path) 로 반환.
    -z 로 NUL 구분 → 한글/공백 경로 안전. 이름변경(R)은 새 경로만.
    """
    rc, out = run([
        "git", "diff", "--cached", "--name-status", "-z",
        "--diff-filter=ACMRT",
    ])
    if rc != 0:
        return []
    tokens = out.split(b"\x00")
    files = []
    i = 0
    while i < len(tokens):
        status = tokens[i].decode("utf-8", "replace") if tokens[i] else ""
        if not status:
            i += 1
            continue
        code = status[0]
        if code == "R":
            # R<score>\told\tnew  → -z 에서는 status, old, new 가 분리 토큰
            # tokens[i]=Rxxx, tokens[i+1]=old, tokens[i+2]=new
            if i + 2 < len(tokens):
                path = tokens[i + 2]
                files.append((code, path))
            i += 3
        else:
            if i + 1 < len(tokens):
                path = tokens[i + 1]
                files.append((code, path))
            i += 2
    return files


def head_blob(path_bytes):
    """HEAD:<path> blob 바이트. 없으면 None."""
    # path 를 그대로 인자로 전달하기 위해 bytes 경로 사용.
    rc, out = run(["git", "cat-file", "-p", b"HEAD:" + path_bytes])
    if rc != 0:
        return None
    return out


def staged_blob(path_bytes):
    """staged(인덱스) blob 바이트. 없으면 None."""
    rc, out = run(["git", "cat-file", "-p", b":" + path_bytes])
    if rc != 0:
        return None
    return out


def main():
    import time
    files = staged_files()
    violations = []
    recent_hits = []   # (경로, 지워지는 최근 줄 수)
    now = int(time.time())

    for code, path_bytes in files:
        try:
            disp = path_bytes.decode("utf-8", "replace")
            low = disp.lower()
            if not low.endswith(WATCH_SUFFIXES):
                continue

            # 신규 파일(HEAD에 없음) → 통과
            head = head_blob(path_bytes)
            if head is None:
                continue

            new = staged_blob(path_bytes)
            # 전체 삭제(인덱스에 없음) → 통과(의도적)
            if new is None:
                continue

            head_lines = count_lines(head)
            new_lines = count_lines(new)

            # 소형 파일 → 비율 노이즈 방지, 스킵
            if head_lines < MIN_HEAD_LINES:
                continue

            dropped = head_lines - new_lines
            if dropped <= 0:
                continue  # 증가/동일 → OK

            ratio = dropped / head_lines
            if over_threshold(disp, head_lines, dropped):
                violations.append((disp, head_lines, new_lines, dropped, ratio))
        except Exception:
            # 개별 파일 처리 실패 → 그 파일만 건너뜀(fail-open).
            continue

    # ── 최근 작업 삭제 판정(충돌 다발 경로만) ─────────────────────────────
    # 줄수 기준을 통과해도, 며칠 안에 들어온 줄을 여러 개 지우면 옛 사본으로 덮은 것이다.
    for code, path_bytes in files:
        try:
            disp = path_bytes.decode("utf-8", "replace")
            if not _is_hot(disp) or not disp.lower().endswith(WATCH_SUFFIXES):
                continue
            head = head_blob(path_bytes)
            new = staged_blob(path_bytes)
            if head is None or new is None:
                continue
            n = recent_deletions(
                disp,
                head.decode("utf-8", "replace"),
                new.decode("utf-8", "replace"),
                now,
            )
            if n >= RECENT_DELETE_LINES:
                recent_hits.append((disp, n))
        except Exception:
            # 개별 파일 처리 실패 → 그 파일만 건너뜀(fail-open).
            continue

    if recent_hits:
        sys.stderr.write(
            "\n"
            "============================================================\n"
            "[truncation-guard] 커밋 차단 — 최근에 들어온 작업이 지워집니다\n"
            "------------------------------------------------------------\n"
        )
        for disp, n in recent_hits:
            sys.stderr.write(
                "  - %s\n"
                "      최근 %d일 안에 추가된 줄 %d개가 이번 커밋에서 사라집니다\n"
                % (disp, RECENT_DAYS, n)
            )
        sys.stderr.write(
            "------------------------------------------------------------\n"
            "  들고 있던 옛 전체본으로 파일을 통째로 다시 쓰면 이렇게 됩니다.\n"
            "  파일을 다시 읽어 최신 내용 위에 고쳐 올리세요.\n"
            "  되돌리기가 의도라면 우회:  git commit --no-verify\n"
            "============================================================\n"
        )
        log_guard_decision(
            "truncation", "BLOCK",
            "최근 작업 삭제 %d개 파일" % len(recent_hits),
            [disp for disp, _ in recent_hits],
        )
        return 1

    if violations:
        sys.stderr.write(
            "\n"
            "============================================================\n"
            "[truncation-guard] 커밋 차단 — 대량 라인 유실 감지\n"
            "------------------------------------------------------------\n"
        )
        for disp, hl, nl, dr, ratio in violations:
            sys.stderr.write(
                "  - %s\n"
                "      %d줄 → %d줄  (%d줄 / %.0f%% 감소)\n"
                % (disp, hl, nl, dr, ratio * 100)
            )
        sys.stderr.write(
            "------------------------------------------------------------\n"
            "  stale 사본 덮어쓰기로 인한 유실일 수 있습니다. 확인하세요.\n"
            "  의도적 대량 삭제라면 우회:  git commit --no-verify\n"
            "============================================================\n"
        )
        log_guard_decision(
            "truncation", "BLOCK",
            "%d개 파일 대량 라인 유실" % len(violations),
            [disp for disp, *_ in violations],
        )
        return 1

    log_guard_decision("truncation", "PASS")
    return 0


if __name__ == "__main__":
    try:
        if "--selfcheck" in sys.argv:
            sys.exit(selfcheck())
        sys.exit(main())
    except Exception as exc:
        # 가드 자체 오류 → fail-open(커밋 통과). 진단 메시지만 출력.
        sys.stderr.write(
            "[truncation-guard][WARN] 가드 내부 오류 — 통과(fail-open): %r\n" % (exc,)
        )
        log_guard_decision("truncation", "WARN", "내부 오류 fail-open: %r" % (exc,))
        sys.exit(0)
