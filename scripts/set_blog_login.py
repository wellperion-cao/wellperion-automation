# -*- coding: utf-8 -*-
"""파트너 블로그 네이버 로그인 정보(아이디·비밀번호)를 GM PC 로컬 비밀 파일에 넣는다.

GM 결재 2026-09-15: 자동 재로그인을 위해 두 파트너 계정(jo·dc) 아이디·비밀번호를
저장소 밖 취급인 profiles/(gitignore 대상) 에 평문으로 둔다.

쓰는 법: python scripts/set_blog_login.py jo   (또는 dc)
저장 위치: profiles/{tenant}_naver_login.env  (NAVER_ID=… / NAVER_PW=… 두 줄)
"""
from __future__ import annotations

import argparse
import getpass
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TENANTS = {"jo": "조재오 부장님 · 고척골프", "dc": "이승기 대표님 · 다이어트캠프"}


def env_path(tenant: str) -> Path:
    return ROOT / "profiles" / f"{tenant}_naver_login.env"


def is_gitignored(path: Path) -> bool:
    r = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=str(ROOT))
    return r.returncode == 0


def mask(value: str) -> str:
    return value[:2] + "*" * max(len(value) - 2, 0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tenant", nargs="?", choices=sorted(TENANTS),
                     help="jo=고척골프 조재오부장님 · dc=다이어트캠프 이승기대표님")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        assert mask("hong1234") == "ho******"
        assert mask("ab") == "ab"
        print("set_blog_login 자가점검 통과")
        return 0
    if not args.tenant:
        ap.error("tenant 가 필요하다 (jo 또는 dc)")

    path = env_path(args.tenant)
    if not is_gitignored(path):
        print(f"[ERROR] {path} 가 gitignore 대상이 아니다 — 저장하지 않는다.")
        return 1

    print(f"=== {TENANTS[args.tenant]} 네이버 로그인 정보 ===")
    nid = input("아이디: ").strip()
    npw = getpass.getpass("비밀번호(화면에 안 보임): ")
    if not nid or not npw:
        print("[ERROR] 아이디·비밀번호가 비어 있다 — 저장하지 않는다.")
        return 1

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"NAVER_ID={nid}\nNAVER_PW={npw}\n", encoding="utf-8")
    print(f"저장했다 · 아이디 = {mask(nid)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
