#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_chatid_drift.py — 텔레그램 방번호 폴백 리터럴 어긋남 가드

동작:
  telegram_bot/.env 에서 방번호 정본(canonical)을 읽는다.
  staged 파일에 추적 대상이 포함되면(또는 .env 자체가 staged 이면 전체)
  해당 소스 파일의 폴백·고정 리터럴을 정본과 대조한다.
  어긋남이 있으면 경고(warn) 출력 후 exit 0(fail-open).

추적 대상 파일 & 규칙:
  telegram_bot/daily_scheduler.py          — CHECK/INQUIRY/RECEPTION or-폴백 3종
  scripts/ig_review_publish_watcher.py     — RECEPTION 최종 리터럴 폴백
  scripts/telegram_health_check.py         — CHECK/INQUIRY/RECEPTION dict-기본값 3종
  .deploy-check/지원팀 일일점검.js         — CHECK CHAT_ID 고정값
  .deploy-funnel/Survey.js                 — INQUIRY _INQUIRY_CHAT_ID_FALLBACK

안전 원칙:
  모든 예외 → fail-open(exit 0). 가드 버그로 커밋·watcher 자동push 마비 금지.
  warn 전용 — exit 1 없음. watcher 5분 자동커밋 보호 필수.
"""

import re
import subprocess
import sys
import io
from pathlib import Path

try:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _REPO_ROOT / "telegram_bot" / ".env"

# 추적 규칙: (레포 상대경로, 정규식 group1=리터럴, .env 키, 설명)
_RULES = [
    (
        "telegram_bot/daily_scheduler.py",
        re.compile(r'ENV\.get\("TELEGRAM_CHECK_CHAT_ID"\)\s+or\s+(-?\d+)'),
        "TELEGRAM_CHECK_CHAT_ID",
        "daily_scheduler CHECK 폴백",
    ),
    (
        "telegram_bot/daily_scheduler.py",
        re.compile(r'ENV\.get\("TELEGRAM_INQUIRY_CHAT_ID"\)\s+or\s+(-?\d+)'),
        "TELEGRAM_INQUIRY_CHAT_ID",
        "daily_scheduler INQUIRY 폴백",
    ),
    (
        "telegram_bot/daily_scheduler.py",
        re.compile(r'ENV\.get\("TELEGRAM_RECEPTION_CHAT_ID"\)\s+or\s+(-?\d+)'),
        "TELEGRAM_RECEPTION_CHAT_ID",
        "daily_scheduler RECEPTION 폴백",
    ),
    (
        "scripts/ig_review_publish_watcher.py",
        re.compile(r'or\s+"(-\d{9,})"'),
        "TELEGRAM_RECEPTION_CHAT_ID",
        "ig_review_publish_watcher RECEPTION 최종 폴백",
    ),
    (
        "scripts/telegram_health_check.py",
        re.compile(r"env\.get\('TELEGRAM_CHECK_CHAT_ID',\s*'(-?\d+)'\)"),
        "TELEGRAM_CHECK_CHAT_ID",
        "telegram_health_check CHECK 기본값",
    ),
    (
        "scripts/telegram_health_check.py",
        re.compile(r"env\.get\('TELEGRAM_INQUIRY_CHAT_ID',\s*'(-?\d+)'\)"),
        "TELEGRAM_INQUIRY_CHAT_ID",
        "telegram_health_check INQUIRY 기본값",
    ),
    (
        "scripts/telegram_health_check.py",
        re.compile(r"env\.get\('TELEGRAM_RECEPTION_CHAT_ID',\s*'(-?\d+)'\)"),
        "TELEGRAM_RECEPTION_CHAT_ID",
        "telegram_health_check RECEPTION 기본값",
    ),
    (
        ".deploy-check/지원팀 일일점검.js",
        re.compile(r"CHAT_ID\s*=\s*'(-?\d+)'"),
        "TELEGRAM_CHECK_CHAT_ID",
        "지원팀 일일점검.js CHECK 고정값",
    ),
    (
        ".deploy-funnel/Survey.js",
        re.compile(r"_INQUIRY_CHAT_ID_FALLBACK\s*=\s*'(-?\d+)'"),
        "TELEGRAM_INQUIRY_CHAT_ID",
        "Survey.js INQUIRY 폴백",
    ),
]

_ALL_TRACKED = {rel for rel, _, _, _ in _RULES}
# staged 체크 시 .env 매칭 접미사 (forward-slash, git 출력 형식)
_ENV_SUFFIXES = ("telegram_bot/.env",)


def _staged_files() -> set:
    """staged 파일 레포 상대경로 집합(forward-slash). 실패 시 빈 집합."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "-z"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            return set()
        parts = proc.stdout.split(b"\x00")
        return {p.decode("utf-8", "replace") for p in parts if p}
    except Exception:
        return set()


def _load_env(path: Path) -> dict:
    """KEY=VALUE 단순 파싱(주석·빈줄 무시). 실패 시 빈 딕트."""
    result = {}
    try:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    result[k.strip()] = v.strip()
    except Exception:
        pass
    return result


def _read_file(path: Path):
    """파일 텍스트 읽기. 실패 시 None."""
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return None


def main() -> int:
    try:
        staged = _staged_files()
        if not staged:
            return 0

        env = _load_env(_ENV_PATH)
        if not env:
            # .env 읽기 실패 → 판단 불가, fail-open
            sys.stderr.write("[chatid-drift][WARN] .env 로드 실패 — 가드 skip(통과)\n")
            return 0

        # .env 자체가 staged 이면 전체 추적파일 스캔, 그 외 staged 된 추적파일만
        env_is_staged = any(s.replace("\\", "/").endswith(suf) for s in staged for suf in _ENV_SUFFIXES)
        if env_is_staged:
            scan_targets = _ALL_TRACKED
        else:
            scan_targets = {rel.replace("\\", "/") for rel in _ALL_TRACKED if rel in staged}

        if not scan_targets:
            return 0

        drifts = []

        for rel, pattern, env_key, label in _RULES:
            if rel not in scan_targets:
                continue
            canonical = env.get(env_key)
            if not canonical:
                # 키 없음 → 판단 불가, skip
                continue
            file_path = _REPO_ROOT / rel
            content = _read_file(file_path)
            if content is None:
                continue
            for m in pattern.finditer(content):
                literal = m.group(1)
                if literal != canonical:
                    lineno = content[: m.start()].count("\n") + 1
                    drifts.append(
                        f"  [{label}]\n"
                        f"    파일: {rel}:{lineno}\n"
                        f"    리터럴={literal!r}  ←  .env {env_key}={canonical!r}"
                    )

        if drifts:
            sys.stdout.write(
                "\n[chatid-drift][WARN] 텔레그램 방번호 폴백 리터럴이 .env 정본과 어긋납니다!\n"
            )
            for d in drifts:
                sys.stdout.write(d + "\n")
            sys.stdout.write(
                "  → telegram_bot/.env 또는 각 파일의 폴백 리터럴을 일치시키세요.\n"
                "  → 커밋은 통과합니다(warn 모드). 의도적 변경이면 무시 가능.\n\n"
            )

        return 0

    except Exception as exc:
        try:
            sys.stderr.write(f"[chatid-drift][WARN] 가드 내부 오류 — fail-open: {exc!r}\n")
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
