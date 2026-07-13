"""
test_publish_preflight.py — 발행 사전점검(source-side pre-flight) pytest.
검증 대상: scripts/publish_preflight.py
"""

import os
import sys
import tempfile

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from publish_preflight import check_source_preflight  # noqa: E402


def _tmp_existing_file():
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    return path


def test_body_empty_fails():
    v = check_source_preflight("카페", body="", image_paths=[], require_images=False)
    assert v.ok is False
    assert any(c.severity == "FAIL" and "비었음" in c.detail for c in v.checks)


def test_body_too_short_warns():
    v = check_source_preflight("카페", body="짧음", image_paths=[], require_images=False)
    assert v.ok is True
    assert any(c.severity == "WARN" and "짧음" in c.detail for c in v.checks)


def test_images_zero_required_fails():
    v = check_source_preflight(
        "카페", body="충분히 긴 본문입니다 20자 이상 채움용.", image_paths=[], require_images=True
    )
    assert v.ok is False
    assert any(c.severity == "FAIL" and "이미지 0장(필수)" in c.detail for c in v.checks)


def test_images_missing_on_disk_fails():
    existing = _tmp_existing_file()
    try:
        missing_path = existing + "_이건_없는_파일.jpg"
        v = check_source_preflight(
            "카페",
            body="충분히 긴 본문입니다 20자 이상 채움용.",
            image_paths=[existing, missing_path],
            require_images=True,
        )
        assert v.ok is False
        assert any(
            c.severity == "FAIL" and "이미지 파일 없음" in c.detail for c in v.checks
        )
    finally:
        os.remove(existing)


def test_images_all_exist_passes():
    a = _tmp_existing_file()
    b = _tmp_existing_file()
    try:
        v = check_source_preflight(
            "카페",
            body="충분히 긴 본문입니다 20자 이상 채움용.",
            image_paths=[a, b],
            require_images=True,
        )
        assert v.ok is True
        assert any(
            c.severity == "OK" and "실존 확인" in c.detail for c in v.checks
        )
    finally:
        os.remove(a)
        os.remove(b)


def test_tags_over_limit_warns():
    a = _tmp_existing_file()
    try:
        v = check_source_preflight(
            "카페",
            body="충분히 긴 본문입니다 20자 이상 채움용.",
            image_paths=[a],
            tags=["#a", "#b", "#c"],
            max_tags=2,
        )
        assert v.ok is True
        assert any(c.severity == "WARN" and "태그" in c.name for c in v.checks)
    finally:
        os.remove(a)


def test_inquiry_marker_absent_warns():
    a = _tmp_existing_file()
    try:
        v = check_source_preflight(
            "카페",
            body="충분히 긴 본문입니다 20자 이상 채움용.",
            image_paths=[a],
            inquiry_marker_present=False,
        )
        assert v.ok is True
        assert any(c.severity == "WARN" and "문의줄" in c.name for c in v.checks)
    finally:
        os.remove(a)


def test_link_url_format_bad_warns():
    a = _tmp_existing_file()
    try:
        v = check_source_preflight(
            "카페",
            body="충분히 긴 본문입니다 20자 이상 채움용.",
            image_paths=[a],
            link_url="ftp://wrong.example.com",
        )
        assert v.ok is True
        assert any(c.severity == "WARN" and "링크" in c.name for c in v.checks)
    finally:
        os.remove(a)


def test_images_zero_not_required_passes():
    v = check_source_preflight(
        "당근", body="충분히 긴 본문입니다 20자 이상 채움용.", image_paths=[], require_images=False
    )
    assert v.ok is True
    assert v.failures == []


def test_all_normal_passes():
    a = _tmp_existing_file()
    b = _tmp_existing_file()
    try:
        v = check_source_preflight(
            "카페",
            body="충분히 긴 본문입니다 20자 이상 채움용. 정상 케이스입니다.",
            image_paths=[a, b],
            tags=["#한남동", "#골프"],
            max_tags=10,
            inquiry_marker_present=True,
            link_url="https://wellperion.com/ko/inquiry",
        )
        assert v.ok is True
        assert v.failures == []
        assert v.warnings == []
        assert v.summary() == "PASS"
    finally:
        os.remove(a)
        os.remove(b)


def test_properties_accuracy_mixed():
    v = check_source_preflight(
        "카페",
        body="",
        image_paths=["존재하지_않는_파일.jpg"],
        require_images=True,
        tags=["#a", "#b", "#c"],
        max_tags=1,
        inquiry_marker_present=False,
    )
    # 본문 FAIL, 이미지(파일없음) FAIL, 태그 WARN, 문의줄 WARN
    assert len(v.failures) == 2
    assert len(v.warnings) == 2
    assert v.ok is False
    assert "BLOCK(" in v.summary()
    assert "경고" in v.summary()
