"""
test_send_review_card_mark_sent.py — send_review_card._mark_card_sent() 회귀 테스트.
검증 대상: scripts/send_review_card.py _mark_card_sent().

배경(배292, 2026-08-02): G1 '주의 신호'(gm1RenderAlertSignal)가 status='검수대기'
전체를 'GM 승인 대기'로 세는 바람에, 아직 카드조차 안 나간 재고(AI하루 시리즈는 하루
1장만 발송)까지 GM이 방치한 것처럼 보이는 착시를 만들었다. 카드 발송 성공 시에만
review_queue.json 항목에 card_sent_at 을 남겨 화면이 '실제 GM 대기'와 '발송 차례 대기'를
구분하게 한다. 카드 발송 실패 시에는 남기지 않아야 한다(아직 GM에게 안 보였으므로).
"""

import json
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import review_queue_util as rqu  # noqa: E402
import send_review_card as src  # noqa: E402


def _write_queue(path, items):
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def test_mark_card_sent_sets_field_once(tmp_path, monkeypatch):
    queue_path = tmp_path / "review_queue.json"
    _write_queue(queue_path, [
        {"id": "CMO-TEST-A", "status": "검수대기", "title": "A"},
        {"id": "CMO-TEST-B", "status": "검수대기", "title": "B"},
    ])
    monkeypatch.setattr(rqu, "REVIEW_QUEUE_PATH", queue_path)

    src._mark_card_sent(["CMO-TEST-A"])

    items = json.loads(queue_path.read_text(encoding="utf-8"))
    by_id = {it["id"]: it for it in items}
    assert by_id["CMO-TEST-A"].get("card_sent_at"), "카드 발송된 항목은 card_sent_at 이 찍혀야 한다"
    assert not by_id["CMO-TEST-B"].get("card_sent_at"), "카드가 안 나간 항목은 건드리면 안 된다"

    first_ts = by_id["CMO-TEST-A"]["card_sent_at"]
    src._mark_card_sent(["CMO-TEST-A"])  # 재호출해도 기존 값을 덮지 않음(최초 발송 시각 보존)
    items2 = json.loads(queue_path.read_text(encoding="utf-8"))
    assert items2[0]["card_sent_at"] == first_ts


def test_mark_card_sent_missing_id_is_noop(tmp_path, monkeypatch):
    queue_path = tmp_path / "review_queue.json"
    _write_queue(queue_path, [{"id": "CMO-TEST-C", "status": "검수대기"}])
    monkeypatch.setattr(rqu, "REVIEW_QUEUE_PATH", queue_path)

    src._mark_card_sent(["CMO-DOES-NOT-EXIST"])  # 대상 없음 — 예외 없이 조용히 종료(SkipSave)

    items = json.loads(queue_path.read_text(encoding="utf-8"))
    assert "card_sent_at" not in items[0]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
