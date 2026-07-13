"""
test_publish_integrity_gate.py — 발행 무결성 게이트 pytest.
검증 대상: scripts/publish_integrity_gate.py
"""

import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from publish_integrity_gate import evaluate_integrity  # noqa: E402


def test_body_missing_fails():
    v = evaluate_integrity("블로그", body_text_len=0, img_count=-1)
    assert v.ok is False
    assert any(c.severity == "FAIL" and "비었음" in c.detail for c in v.checks)


def test_body_too_short_warns():
    v = evaluate_integrity("블로그", body_text_len=5, img_count=-1)
    assert v.ok is True
    assert any(c.severity == "WARN" and "짧음" in c.detail for c in v.checks)


def test_images_all_missing_fails():
    v = evaluate_integrity(
        "카페", body_text_len=100, img_count=0, expected_img=3
    )
    assert v.ok is False
    assert any(c.severity == "FAIL" and "전체 소실" in c.detail for c in v.checks)


def test_images_partial_missing_fails():
    v = evaluate_integrity(
        "카페", body_text_len=100, img_count=2, expected_img=3
    )
    assert v.ok is False
    assert any(c.severity == "FAIL" and "누락 2/3" in c.detail for c in v.checks)


def test_images_satisfied_passes():
    v = evaluate_integrity(
        "카페", body_text_len=100, img_count=3, expected_img=3
    )
    assert v.ok is True
    assert any(c.severity == "OK" and "이미지" in c.name for c in v.checks)


def test_unmeasurable_warns_not_blocks():
    v = evaluate_integrity(
        "당근", body_text_len=-1, img_count=-1, expected_img=3
    )
    assert v.ok is True
    assert any(c.severity == "WARN" and "본문" in c.name for c in v.checks)
    assert any(c.severity == "WARN" and "이미지" in c.name for c in v.checks)


def test_tags_missing_warns():
    v = evaluate_integrity(
        "블로그",
        body_text_len=100,
        img_count=-1,
        tag_count=0,
        expected_tags=5,
    )
    assert v.ok is True
    assert any(c.severity == "WARN" and "태그" in c.name for c in v.checks)


def test_link_missing_warns():
    v = evaluate_integrity(
        "블로그",
        body_text_len=100,
        img_count=-1,
        expect_link=True,
        link_present=False,
    )
    assert v.ok is True
    assert any(c.severity == "WARN" and "링크카드 없음" in c.detail for c in v.checks)


def test_all_normal_passes():
    v = evaluate_integrity(
        "블로그",
        body_text_len=500,
        img_count=3,
        expected_img=3,
        tag_count=5,
        expected_tags=5,
        expect_link=True,
        link_present=True,
    )
    assert v.ok is True
    assert v.failures == []
    assert v.warnings == []
    assert v.summary() == "PASS"


def test_no_args_gives_single_ok_check():
    v = evaluate_integrity("블로그", body_text_len=100, img_count=-1)
    # 이미지는 expected_img 미지정이라 체크 생략 -> 본문 체크 1건만 존재
    assert len(v.checks) == 1


def test_properties_accuracy_mixed():
    v = evaluate_integrity(
        "카페",
        body_text_len=0,
        img_count=1,
        expected_img=3,
        tag_count=1,
        expected_tags=5,
    )
    # 본문 FAIL, 이미지 FAIL, 태그 WARN
    assert len(v.failures) == 2
    assert len(v.warnings) == 1
    assert v.ok is False
    assert "BLOCK(" in v.summary()
    assert "경고" in v.summary()
