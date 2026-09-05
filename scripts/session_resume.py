#!/usr/bin/env python3
"""역할별 최근 Claude 세션 id 찾기 — Resume-AI.bat 가 부른다 (GM 지시 2026-09-05: 계정 바꿔도 세션 이어서 + 원격제어 자동).

세션 기록(~/.claude/projects/<repo>/*.jsonl)은 로그인 계정과 무관하게 이 PC 한 곳에 쌓인다.
역할 판정은 상태줄(scripts/wellperion_hud.mjs roleOf)과 같은 규칙 — 기록 첫 60,000자에서 부팅 문구 `ai-<role>.md` 를 찾는다.

사용: python scripts/session_resume.py --role cmo   → 세션 id 한 줄 출력(없으면 빈 줄 · 종료코드 1)
"""
import argparse, glob, os, re, sys

ROLES = ("ceo", "cmo", "cto", "coo", "cpo", "cfo", "chro", "cbo")
PROJECT_DIR = os.path.join(os.path.expanduser("~"), ".claude", "projects", "C--Users-jjky0-welperion-automation")


def role_of(path: str):
    try:
        with open(path, encoding="utf-8", errors="replace") as h:
            head = h.read(60000)
    except OSError:
        return None
    m = re.search(r"ai-(ceo|cmo|cto|coo|cpo|cfo|chro|cbo)\.md", head)
    return m.group(1) if m else None


def latest_session(role: str, min_kb: int = 50):
    files = sorted(glob.glob(os.path.join(PROJECT_DIR, "*.jsonl")), key=os.path.getmtime, reverse=True)
    for f in files:
        if os.path.getsize(f) < min_kb * 1024:      # 서브에이전트·빈 세션 건너뜀
            continue
        if role_of(f) == role:
            return os.path.splitext(os.path.basename(f))[0]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True, choices=ROLES)
    ap.add_argument("--list", action="store_true", help="최근 10개 세션의 역할을 보여준다")
    a = ap.parse_args()
    if a.list:
        for f in sorted(glob.glob(os.path.join(PROJECT_DIR, "*.jsonl")), key=os.path.getmtime, reverse=True)[:10]:
            print(os.path.basename(f)[:8], f"{os.path.getsize(f)//1024:>6}KB", role_of(f) or "-")
        return
    sid = latest_session(a.role)
    print(sid or "")
    sys.exit(0 if sid else 1)


if __name__ == "__main__":
    main()
