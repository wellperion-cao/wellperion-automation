#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
precommit_incident_guard.py — 커밋 전 사고 교훈 알림 가드

동작:
  staged 변경파일 목록을 읽어, incidents.json 의 각 사건 watch_globs 와 매칭.
  매칭되면 그 사건의 '요약'(쉬운 한 줄)을 경고로 출력.
  gate=warn  → 출력만, exit 0 (커밋 통과)
  gate=block → 출력 후 exit 1 (커밋 차단)

  추가로 ssot/divergence_scan.py 를 호출해 캐논값 하드코딩 복사본 경고(차단 안 함).

안전 원칙:
  - 모든 예외 try/except → fail-open (exit 0). 가드 버그로 커밋 마비 금지.
  - watch_globs 빈 배열 사건 → 트리거 없음(조용히 통과).
  - gate=warn 은 절대 커밋 안 막음.
"""

import subprocess
import sys
import json
import fnmatch
import io
from pathlib import Path

# Windows 콘솔 UTF-8 강제
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def staged_files():
    """staged 파일 경로 목록(str). 실패 시 빈 리스트."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "-z"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            return []
        raw = proc.stdout
        parts = raw.split(b"\x00")
        result = []
        for p in parts:
            if p:
                try:
                    result.append(p.decode("utf-8", "replace"))
                except Exception:
                    pass
        return result
    except Exception:
        return []


def load_incidents(repo_root):
    """incidents.json 로드. 실패 시 빈 리스트."""
    try:
        path = repo_root / "ssot" / "incidents.json"
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("incidents", [])
    except Exception:
        return []


def matches_any_glob(filepath, globs):
    """
    filepath 가 globs 중 하나라도 fnmatch 매칭되면 True.
    경로 구분자 정규화 후 파일명·전체경로 양쪽 시도.
    """
    if not globs:
        return False
    fp_norm = filepath.replace("\\", "/")
    fp_name = Path(filepath).name
    for g in globs:
        g_norm = g.replace("\\", "/")
        if fnmatch.fnmatch(fp_norm, g_norm):
            return True
        # glob 에 경로 구분자 없으면 파일명만으로도 매칭 시도
        if "/" not in g_norm and fnmatch.fnmatch(fp_name, g_norm):
            return True
    return False


def run_divergence_scan(repo_root):
    """
    ssot/divergence_scan.py 호출 — 캐논 복사본 경고(차단 안 함).
    실패·없음 → 조용히 통과.
    """
    try:
        scan_path = repo_root / "ssot" / "divergence_scan.py"
        if not scan_path.exists():
            return
        pybin = sys.executable
        proc = subprocess.run(
            [pybin, str(scan_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(repo_root),
        )
        output = proc.stdout.decode("utf-8", "replace")
        # 복사본 감지 시에만 출력 (✅ 전체 통과라면 출력 생략)
        if "정본 밖 복사본 없음" not in output and "전체 요약" not in output:
            return
        if "정본 밖 복사본 없음" not in output or "0건" not in output.replace(" ", ""):
            # 일부 위반 가능성 — 전체 출력
            lines = [l for l in output.splitlines() if "결과:" in l and "없음" not in l]
            if lines:
                print("\n[incident-guard] ⚠️ 캐논값 복사본 경고 (커밋은 통과):")
                for l in lines[:10]:
                    print("  " + l.strip())
    except Exception:
        pass  # fail-open


def main():
    try:
        # repo root 찾기
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            return 0  # fail-open
        repo_root = Path(proc.stdout.decode("utf-8", "replace").strip())
    except Exception:
        return 0  # fail-open

    try:
        files = staged_files()
        if not files:
            return 0

        incidents = load_incidents(repo_root)
        if not incidents:
            return 0

        block_triggered = False

        for inc in incidents:
            try:
                watch_globs = inc.get("watch_globs", [])
                gate = inc.get("gate", "warn")
                summary = inc.get("요약", inc.get("증상", ""))
                inc_id = inc.get("id", "?")

                if not watch_globs:
                    continue  # 트리거 없음 — 조용히 통과

                # staged 파일 중 매칭 있는지 확인
                matched = [f for f in files if matches_any_glob(f, watch_globs)]
                if not matched:
                    continue

                # 매칭됨 → 교훈 출력
                print(
                    "\n[incident-guard] ⚠️  지난 교훈 ({id}): {summary}".format(
                        id=inc_id, summary=summary
                    )
                )
                print(
                    "  관련 파일: " + ", ".join(matched[:3])
                    + ("..." if len(matched) > 3 else "")
                )

                if gate == "block":
                    print(
                        "  → gate=block: 위 교훈을 확인하고 커밋하려면 git commit --no-verify"
                    )
                    block_triggered = True

            except Exception:
                continue  # 개별 사건 처리 실패 → fail-open

        # 발산 스캔 (warn 전용, 차단 없음)
        try:
            run_divergence_scan(repo_root)
        except Exception:
            pass  # fail-open

        if block_triggered:
            return 1

        return 0

    except Exception:
        return 0  # 전체 실패 → fail-open


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        try:
            sys.stderr.write(
                "[incident-guard][WARN] 가드 내부 오류 — 통과(fail-open): %r\n" % (exc,)
            )
        except Exception:
            pass
        sys.exit(0)
