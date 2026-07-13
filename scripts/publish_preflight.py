# -*- coding: utf-8 -*-
"""발행 사전점검(source-side pre-flight) — 발행 요새화 §1 사전점검.

목적: 브라우저를 띄우기 전에 입력(본문·이미지 파일·태그·문의줄·링크)의 온전성을
검사해, 깨진 입력으로 발행을 시도해 임시저장함을 오염시키는 사이클을 원천 차단한다.
판정 자료구조는 publish_integrity_gate 의 Check/IntegrityVerdict 를 재사용(DRY) —
브라우저 실행 후 결과를 확인하는 무결성 게이트(§2)와 대칭되는 발행 전(§1) 단계다.
"""

import os
from typing import List, Optional, Sequence, Union

try:
    from publish_integrity_gate import Check, IntegrityVerdict
except ImportError:
    import sys as _sys
    import os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from publish_integrity_gate import Check, IntegrityVerdict


def check_source_preflight(
    channel: str,
    *,
    body: str,
    image_paths: Sequence[Union[str, "os.PathLike"]],
    tags: Optional[List[str]] = None,
    require_images: bool = True,
    max_tags: Optional[int] = None,
    inquiry_marker_present: Optional[bool] = None,
    link_url: Optional[str] = None,
    min_body_len: int = 20,
) -> IntegrityVerdict:
    """발행 직전(브라우저 실행 전) 입력 온전성 판정.

    channel 은 로그·표기용(예: "블로그"/"카페"/"당근")이며 판정 로직에는
    영향을 주지 않는다.
    """

    checks: List[Check] = []

    # 1) 본문 체크
    stripped_len = len(body.strip()) if body else 0
    if stripped_len == 0:
        checks.append(Check("본문", "FAIL", "본문 비었음"))
    elif stripped_len < min_body_len:
        checks.append(Check("본문", "WARN", f"본문 매우 짧음({stripped_len}자)"))
    else:
        checks.append(Check("본문", "OK", f"본문 {stripped_len}자 확인"))

    # 2) 이미지 개수 체크
    if require_images and len(image_paths) == 0:
        checks.append(Check("이미지", "FAIL", "이미지 0장(필수)"))
    else:
        # 3) 이미지 실존 체크 (개수 체크와 별개 — 0장 필수 위반이 아니어도 실존은 확인)
        missing = [str(p) for p in image_paths if not os.path.exists(p)]
        if missing:
            names = ", ".join(os.path.basename(m) for m in missing)
            checks.append(
                Check("이미지", "FAIL", f"이미지 파일 없음 {len(missing)}장: {names}")
            )
        elif image_paths:
            checks.append(Check("이미지", "OK", f"이미지 {len(image_paths)}장 실존 확인"))

    # 4) 태그 한도 체크
    if isinstance(max_tags, int) and tags and len(tags) > max_tags:
        checks.append(
            Check(
                "태그",
                "WARN",
                f"태그 {len(tags)}개 > 한도 {max_tags}(초과분 발행시 잘림)",
            )
        )

    # 5) 문의줄 체크 (None 이면 검사 생략)
    if inquiry_marker_present is False:
        checks.append(Check("문의줄", "WARN", "문의줄 없음(스티커·링크 위치 폴백 동작)"))

    # 6) 링크 형식 체크
    if link_url is not None and not str(link_url).startswith(("http://", "https://")):
        checks.append(Check("링크", "WARN", "링크 URL 형식 이상"))

    # 항상 최소 1개 Check 반환
    if not checks:
        checks.append(Check("검사", "OK", "검사 항목 없음"))

    return IntegrityVerdict(checks=checks)
