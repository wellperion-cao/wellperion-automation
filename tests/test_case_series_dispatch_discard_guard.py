"""
test_case_series_dispatch_discard_guard.py — 카드 발송 직전 폐기가드 회귀 테스트.
검증 대상: scripts/case_series_dispatch.py _case_discarded_before_send() / send_review_card()

배경(2026-07-22, CASE08 동종 사고): 개인 실전사례 취소(폐기) 결정이 다음 07:30 전에
SSOT/코드에 안 박히면, 그 사이 recover_stalled_cards() 경로로 카드 발송까지 도달할 수
있다. 기존 재선정 가드(pick_next_case)는 폐기편의 '새 등록'만 막을 뿐, 이미 큐에
'폐기'로 올라온 항목에 대해 send_review_card()가 호출되는 경로 자체를 막지 않았다.
이 테스트는 발송 직전 한 겹의 방어(같은 편 CASE{NN}의 폐기 항목 존재 시 카드 자체를
쏘지 않음)를 검증한다. subprocess.run(=실제 send_review_card.py 호출)은 항상 mock —
실제 텔레그램 발송·라이브 review_queue.json 은 절대 건드리지 않는다.
"""

import json
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import case_series_dispatch as csd  # noqa: E402


def _write_queue(path, items):
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


class _FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_discarded_case_detected_by_marker_and_status(tmp_path, monkeypatch):
    queue_path = tmp_path / "review_queue.json"
    monkeypatch.setattr(csd, "REVIEW_QUEUE_PATH", queue_path)
    _write_queue(queue_path, [{"id": "CMO-2026-07-20-CASE08-오래된편", "status": "폐기"}])

    assert csd._case_discarded_before_send("CMO-2026-07-22-CASE08-새편이름") is True


def test_non_discarded_case_not_flagged(tmp_path, monkeypatch):
    queue_path = tmp_path / "review_queue.json"
    monkeypatch.setattr(csd, "REVIEW_QUEUE_PATH", queue_path)
    _write_queue(queue_path, [{"id": "CMO-2026-07-20-CASE08-오래된편", "status": "검수대기"}])

    assert csd._case_discarded_before_send("CMO-2026-07-22-CASE08-새편이름") is False


def test_discarded_other_case_num_does_not_block(tmp_path, monkeypatch):
    """다른 편(CASE09)이 폐기여도 CASE08 발송엔 영향 없음(편 번호 단위 판정)."""
    queue_path = tmp_path / "review_queue.json"
    monkeypatch.setattr(csd, "REVIEW_QUEUE_PATH", queue_path)
    _write_queue(queue_path, [{"id": "CMO-2026-07-20-CASE09-다른편", "status": "폐기"}])

    assert csd._case_discarded_before_send("CMO-2026-07-22-CASE08-새편이름") is False


def test_no_case_marker_in_id_returns_false(tmp_path, monkeypatch):
    """CASE 마커 없는 id(구형/채널별 id 등)는 편 번호를 못 뽑으므로 가드 대상 아님."""
    queue_path = tmp_path / "review_queue.json"
    monkeypatch.setattr(csd, "REVIEW_QUEUE_PATH", queue_path)
    _write_queue(queue_path, [{"id": "CMO-2026-07-20-SOMETHING", "status": "폐기"}])

    assert csd._case_discarded_before_send("CMO-2026-06-03-AI4-역할분담") is False


def test_send_review_card_skips_subprocess_when_case_discarded(tmp_path, monkeypatch):
    """핵심 회귀: 같은 편 폐기 항목이 있으면 send_review_card()가 subprocess.run(실발송)을
    호출하지 않고 True(정상 스킵)를 반환한다."""
    queue_path = tmp_path / "review_queue.json"
    monkeypatch.setattr(csd, "REVIEW_QUEUE_PATH", queue_path)
    _write_queue(queue_path, [{"id": "CMO-2026-07-20-CASE08-오래된편", "status": "폐기"}])

    calls = []
    monkeypatch.setattr(
        csd.subprocess, "run",
        lambda *a, **k: calls.append((a, k)) or _FakeCompletedProcess(returncode=0),
    )

    result = csd.send_review_card("CMO-2026-07-22-CASE08-새편이름")

    assert result is True
    assert calls == []  # 실제 카드 발송(subprocess) 호출 자체가 없어야 함


def test_send_review_card_calls_subprocess_when_not_discarded(tmp_path, monkeypatch):
    """정상경로 무회귀: 폐기 항목이 없으면 기존처럼 subprocess.run 이 호출된다."""
    queue_path = tmp_path / "review_queue.json"
    monkeypatch.setattr(csd, "REVIEW_QUEUE_PATH", queue_path)
    _write_queue(queue_path, [{"id": "CMO-2026-07-22-CASE08-새편이름", "status": "검수대기"}])

    calls = []

    def fake_run(*a, **k):
        calls.append((a, k))
        return _FakeCompletedProcess(returncode=0)

    monkeypatch.setattr(csd.subprocess, "run", fake_run)

    result = csd.send_review_card("CMO-2026-07-22-CASE08-새편이름")

    assert result is True
    assert len(calls) == 1  # 정상적으로 send_review_card.py 서브프로세스 호출됨


def test_recover_stalled_cards_skips_send_for_discarded_queued_item(tmp_path, monkeypatch):
    """recover_stalled_cards() 경로 통합 검증: 큐에 이미 '폐기'로 올라온 편은
    GM확인 플레이스홀더가 없어도 카드 발송(subprocess) 없이 조용히 넘어간다."""
    queue_path = tmp_path / "review_queue.json"
    msgid_store = tmp_path / ".review_card_msgids.json"
    inventory = tmp_path / "_실전사례_2주플랜.md"
    monkeypatch.setattr(csd, "ROOT", tmp_path)
    monkeypatch.setattr(csd, "REVIEW_QUEUE_PATH", queue_path)
    monkeypatch.setattr(csd, "CARD_MSGID_STORE", msgid_store)
    monkeypatch.setattr(csd, "INVENTORY", inventory)
    telegram_calls = []
    monkeypatch.setattr(csd, "telegram", lambda msg: telegram_calls.append(msg))
    calls = []
    monkeypatch.setattr(
        csd.subprocess, "run",
        lambda *a, **k: calls.append((a, k)) or _FakeCompletedProcess(returncode=0),
    )

    folder = tmp_path / "case08"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "ep08_diary_source.html").write_text("확정된 최종 문구", encoding="utf-8")
    (folder / "caption.md").write_text("확정된 최종 문구", encoding="utf-8")
    folder_rel = str(folder.relative_to(tmp_path)).replace("\\", "/")

    row = {
        "num": 8, "num_raw": "8", "track": "주말GM",
        "title": "편8", "folder": folder_rel, "status": csd.STOCK_STATUS,
    }
    item_id = "CMO-2026-07-20-CASE08-오래된편"
    _write_queue(queue_path, [{"id": item_id, "status": "폐기"}])
    inventory.write_text(
        "## 재고 (표)\n| 편 | 트랙 | 제목 | 폴더 | 상태 |\n|---|---|---|---|---|\n"
        f"| 8 | 주말GM | 편8 | {folder_rel} | {csd.STOCK_STATUS} |\n",
        encoding="utf-8",
    )

    csd.recover_stalled_cards([row], "2026-07-22", dry_run=False)

    assert calls == []  # 실제 카드 발송(subprocess) 없음
    assert telegram_calls == []  # 실패 경고도 없음(스킵=정상 처리)
