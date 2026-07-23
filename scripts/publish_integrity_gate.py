# -*- coding: utf-8 -*-
"""발행 무결성 게이트 — 발행 요새화 §2 무결성 게이트: 블로그·카페·당근 3채널 공유 판정 프레임.

목적: 본문 소실·이미지 누락 등 '깨진 글'을 발행 직전에 잡아 차단(FAIL)하거나
경고(WARN)만 하고 통과시킨다. 브라우저·파일 IO 의존성 없는 순수 판정 로직.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Check:
    """개별 판정 항목 1건."""

    name: str
    severity: str  # "FAIL" | "WARN" | "OK"
    detail: str


@dataclass
class IntegrityVerdict:
    """전체 판정 결과 묶음."""

    checks: List[Check] = field(default_factory=list)

    @property
    def failures(self) -> List[Check]:
        return [c for c in self.checks if c.severity == "FAIL"]

    @property
    def warnings(self) -> List[Check]:
        return [c for c in self.checks if c.severity == "WARN"]

    @property
    def ok(self) -> bool:
        return len(self.failures) == 0

    def summary(self) -> str:
        """사람이 읽는 한 줄 요약: PASS 또는 BLOCK(사유; 사유) + 경고 별첨."""
        if not self.ok:
            reasons = "; ".join(f"{c.name}:{c.detail}" for c in self.failures)
            line = f"BLOCK({reasons})"
        else:
            line = "PASS"
        if self.warnings:
            warn_part = "; ".join(f"{c.name}:{c.detail}" for c in self.warnings)
            line += f" [경고: {warn_part}]"
        return line


def evaluate_integrity(
    channel: str,
    *,
    body_text_len: int,
    img_count: int,
    expected_img: Optional[int] = None,
    tag_count: Optional[int] = None,
    expected_tags: Optional[int] = None,
    link_present: Optional[bool] = None,
    expect_link: Optional[bool] = None,
    min_body_len: int = 20,
    tag_severity: str = "WARN",
    link_severity: str = "WARN",
) -> IntegrityVerdict:
    """채널별 발행 직전 무결성 판정.

    channel 은 로그·표기용(예: "블로그"/"카페"/"당근")이며 판정 로직에는
    영향을 주지 않는다.
    """

    checks: List[Check] = []

    # 1) 본문 체크
    if body_text_len == -1:
        checks.append(Check("본문", "WARN", "본문 측정 불가"))
    elif body_text_len == 0:
        checks.append(Check("본문", "FAIL", "본문 비었음(소실)"))
    elif body_text_len < min_body_len:
        checks.append(Check("본문", "WARN", f"본문 매우 짧음({body_text_len}자)"))
    else:
        checks.append(Check("본문", "OK", f"본문 {body_text_len}자 확인"))

    # 2) 이미지 체크 (expected_img 가 int 이고 > 0 일 때만 비교)
    if isinstance(expected_img, int) and expected_img > 0:
        if img_count == -1:
            checks.append(Check("이미지", "WARN", "이미지 측정 불가"))
        elif img_count == 0:
            checks.append(
                Check("이미지", "FAIL", f"이미지 전체 소실(기대 {expected_img}장)")
            )
        elif img_count < expected_img:
            checks.append(
                Check(
                    "이미지",
                    "FAIL",
                    f"이미지 누락 {img_count}/{expected_img}장",
                )
            )
        else:
            checks.append(Check("이미지", "OK", f"이미지 {img_count}장 확인"))

    # 3) 태그 체크 (expected_tags 가 int 이고 > 0, tag_count 가 실제 측정(int)됐을 때만)
    if isinstance(expected_tags, int) and expected_tags > 0 and isinstance(tag_count, int):
        if tag_count == 0:
            checks.append(
                Check("태그", tag_severity, f"태그 전체 누락(기대 {expected_tags})")
            )
        elif isinstance(tag_count, int) and tag_count < expected_tags:
            checks.append(
                Check(
                    "태그",
                    tag_severity,
                    f"태그 부족 {tag_count}/{expected_tags}",
                )
            )
        else:
            checks.append(Check("태그", "OK", f"태그 {tag_count}개 확인"))

    # 4) 링크 체크 (expect_link 가 True 일 때만)
    if expect_link is True:
        if not link_present:
            checks.append(Check("링크", link_severity, "링크카드 없음"))
        else:
            checks.append(Check("링크", "OK", "링크카드 확인"))

    # 항상 최소 1개 Check 반환
    if not checks:
        checks.append(Check("검증", "OK", "검증 항목 없음"))

    return IntegrityVerdict(checks=checks)
