# -*- coding: utf-8 -*-
"""채널 로그인 세션(계정) 자리 — 발행기가 어느 계정으로 나갈지 한 곳에서 정한다.

왜 있나 — 2026-09-09. 4채널 발행기는 계정 개념이 없었다. 인증은 profiles/{채널}_state.json
쿠키 하나를 보고, 그것이 웰페리온 계정이다. 파트너(다이어트캠프 이승기 대표님·조재오 부장님)
계정으로 글을 올리면 웰페리온 이름으로 나간다.

쓰는 법: 환경변수 WP_TENANT 에 파트너 이름을 넣으면 그 계정 자리를 쓴다.
  WP_TENANT 없음  -> profiles/naver-blog        · profiles/naver-blog_state.json  (웰페리온, 종전 그대로)
  WP_TENANT=jo    -> profiles/jo_naver-blog     · profiles/jo_naver-blog_state.json

발행기에서는 --tenant 로 넘긴다. 값을 안 주면 웰페리온 경로로 떨어지므로 기존 발행은 그대로 돈다.

주의: profiles/ 아래는 gitignore 대상이다 — 계정 정보가 저장소에 들어가지 않는다.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_KEY = "WP_TENANT"

_SAFE = re.compile(r"[^A-Za-z0-9_-]")


def tenant_name() -> str:
    """지금 쓰라고 지정된 계정 이름. 없으면 빈 문자열(=웰페리온)."""
    return _SAFE.sub("", (os.environ.get(ENV_KEY) or "").strip())


def profile_paths(channel: str) -> tuple[Path, Path]:
    """(영속 프로필 폴더, 쿠키 파일) 한 쌍. 채널 이름은 종전 폴더명 그대로 넘긴다."""
    t = tenant_name()
    stem = f"{t}_{channel}" if t else channel
    base = ROOT / "profiles"
    return base / stem, base / f"{stem}_state.json"


def demo() -> None:
    """자가점검 — 계정 미지정이면 종전 경로 그대로여야 한다."""
    os.environ.pop(ENV_KEY, None)
    d, s = profile_paths("naver-blog")
    assert d.name == "naver-blog", d
    assert s.name == "naver-blog_state.json", s

    os.environ[ENV_KEY] = "jo"
    d, s = profile_paths("naver-blog")
    assert d.name == "jo_naver-blog", d
    assert s.name == "jo_naver-blog_state.json", s

    os.environ[ENV_KEY] = "../../etc"       # 경로 탈출 시도는 걸러진다
    d, _ = profile_paths("danggn")
    assert d.name == "etc_danggn", d
    assert d.parent.name == "profiles", d

    os.environ.pop(ENV_KEY, None)
    print("tenant_profile 자가점검 통과")


if __name__ == "__main__":
    demo()
