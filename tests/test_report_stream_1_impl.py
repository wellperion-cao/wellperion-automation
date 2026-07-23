"""
test_report_stream_1_impl.py — 22:30 '문의 및 컨택&등록 현황 보고' 정합성 pytest.
검증 대상: scripts/report_stream_1_impl.py (GM 2026-07-23 지적 3건 수리)

★ 실제 네트워크 호출·텔레그램 발송은 절대 하지 않는다 — _fetch_list 를 monkeypatch 로
  가로채고, build_digest() 만 직접 호출한다(main()·send_test() 는 테스트에서 부르지 않음).
"""

import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import report_stream_1_impl as R  # noqa: E402

TODAY = "2026-07-22"


def _row(name, kind_field, value, owner="", status="신규", contacts=None, ts=None, days_ago=0):
    """공통 문의행 팩토리. kind_field: membership="program", lesson="sport"."""
    from datetime import datetime, timedelta

    if ts is None:
        d = datetime.strptime(TODAY, "%Y-%m-%d") - timedelta(days=days_ago)
        ts = d.strftime("%Y-%m-%d") + "T09:00:00"
    row = {
        "name": name,
        "owner": owner,
        "status": status,
        "contacts": contacts or [],
        "timestamp": ts,
    }
    row[kind_field] = value
    return row


def _install_fetch(monkeypatch, mem_rows, adult_rows=None, youth_rows=None):
    data = {
        "member_inquiry_list": mem_rows,
        "lesson_inquiry_list": {"성인강습": adult_rows or [], "유소년강습": youth_rows or []},
    }

    def fake_fetch(action, **params):
        if action == "member_inquiry_list":
            return data["member_inquiry_list"]
        if action == "lesson_inquiry_list":
            return data["lesson_inquiry_list"].get(params.get("type"), [])
        return []

    monkeypatch.setattr(R, "_fetch_list", fake_fetch)


# ---------------------------------------------------------------------------
# ① owner="웹 자동접수" 행이 담당배정 필요로 분류됨
# ---------------------------------------------------------------------------
def test_web_auto_owner_counts_as_unassigned():
    row = _row("서혜진", "program", "플래티넘", owner="웹 자동접수", status="신규")
    assert R._is_unassigned_active(row, is_lesson=False) is True


def test_web_auto_owner_row_appears_in_digest_unassigned_section(monkeypatch):
    mem_rows = [
        _row("서혜진", "program", "플래티넘", owner="웹 자동접수", status="신규"),
        _row("임동균", "program", "플래티넘", owner="웹 자동접수", status="신규"),
    ]
    _install_fetch(monkeypatch, mem_rows)
    text = R.build_digest(today=TODAY)
    assert "서혜진(멤버십)" in text
    assert "임동균(멤버십)" in text
    assert "담당배정 필요 2건" in text


# ---------------------------------------------------------------------------
# ② 세 분류(진전/담당배정 필요/기타) 합 == 총 신규(테스트행 제외)
# ---------------------------------------------------------------------------
def test_three_way_classification_sums_to_total(monkeypatch):
    mem_rows = [
        _row("진전1", "program", "플래티넘", owner="김실장", status="상담중", contacts=[{"note": "통화"}]),
        _row("미배정1", "program", "노블레스", owner="웹 자동접수", status="신규"),
        _row("테스트더미_1700000000", "program", "플래티넘", owner="", status="신규"),  # 제외 대상
        _row("기타1", "program", "플래티넘", owner="박팀장", status="신규"),  # 배정됐지만 진전없음
    ]
    _install_fetch(monkeypatch, mem_rows)
    text = R.build_digest(today=TODAY)
    # 테스트행 제외 총 3건: 진전1 + 담당배정필요1 + 기타1
    assert "총 3건" in text
    assert "진전 1건" in text
    assert "담당배정 필요 1건" in text
    assert "기타 1건" in text


# ---------------------------------------------------------------------------
# ③④⑤ 쏠림 기준선 비교
# ---------------------------------------------------------------------------
def _make_baseline_platinum(n_platinum, n_noblesse, days_ago=15):
    rows = []
    for i in range(n_platinum):
        rows.append(_row(f"기준플1_{i}", "program", "플래티넘", days_ago=days_ago))
    for i in range(n_noblesse):
        rows.append(_row(f"기준노1_{i}", "program", "노블레스", days_ago=days_ago))
    return rows


def test_no_spike_note_when_within_baseline_ratio(monkeypatch):
    # 최근 30일: 플래티넘 33 · 노블레스 31 (총 64, 플래티넘 비중 51.6%)
    baseline = _make_baseline_platinum(33, 31)
    today_rows = [
        _row("당일플1", "program", "플래티넘"),
        _row("당일플2", "program", "플래티넘"),
        _row("당일플3", "program", "플래티넘"),
        _row("당일노1", "program", "노블레스"),
    ]
    mem_rows = baseline + today_rows
    _install_fetch(monkeypatch, mem_rows)
    text = R.build_digest(today=TODAY)
    assert "플래티넘" not in text.split("특이사항:")[1].split("\n")[0]
    assert "특이사항: 없음" in text


def test_spike_note_when_ratio_exceeds_1_5x_baseline(monkeypatch):
    # 최근 30일: 플래티넘 10 · 노블레스 40 (총 50, 플래티넘 비중 20%)
    baseline = _make_baseline_platinum(10, 40)
    # 당일: 멤버십 총 5건 중 플래티넘 4건 = 80% (>= 20%*1.5=30%)
    today_rows = [
        _row("당일플1", "program", "플래티넘"),
        _row("당일플2", "program", "플래티넘"),
        _row("당일플3", "program", "플래티넘"),
        _row("당일플4", "program", "플래티넘"),
        _row("당일노1", "program", "노블레스"),
    ]
    mem_rows = baseline + today_rows
    _install_fetch(monkeypatch, mem_rows)
    text = R.build_digest(today=TODAY)
    assert "멤버십 플래티넘 4건 쏠림" in text


def test_no_spike_note_when_baseline_sample_below_10(monkeypatch):
    # 최근 30일 표본 총 9건(<10) → 기준선 불신, 쏠림 판정 보류
    baseline = _make_baseline_platinum(6, 3)
    today_rows = [
        _row("당일플1", "program", "플래티넘"),
        _row("당일플2", "program", "플래티넘"),
        _row("당일플3", "program", "플래티넘"),
    ]
    mem_rows = baseline + today_rows
    _install_fetch(monkeypatch, mem_rows)
    text = R.build_digest(today=TODAY)
    assert "특이사항: 없음" in text


# ---------------------------------------------------------------------------
# ⑥ 담당배정 필요 줄 위치 — 신규 문의 섹션 안, 컨택&등록 섹션에는 없음
# ---------------------------------------------------------------------------
def test_unassigned_line_in_new_section_not_contact_section(monkeypatch):
    mem_rows = [
        _row("미배정A", "program", "플래티넘", owner="웹 자동접수", status="신규"),
    ]
    _install_fetch(monkeypatch, mem_rows)
    text = R.build_digest(today=TODAY)
    new_section, _, contact_section = text.partition("━━━━━━━━━━")
    assert "🆕 담당배정 필요 1건" in new_section
    assert "🆕 담당배정 필요" not in contact_section
