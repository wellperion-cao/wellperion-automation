"""
test_case_series_dispatch_card_recovery.py — 선등록(카드 보류) 복구 로직 회귀 테스트.
검증 대상: scripts/case_series_dispatch.py recover_stalled_cards()

배경(2026-07-19 CASE13 사고): send_card=False 로 M5 큐에 선등록된 편(GM 확인 대기)이
있으면, _case_already_queued() 가 "review_queue 존재"만 보고 "카드까지 이미 발송됨"으로
오인해 07:30 디스패처가 영영 스킵 — 텔레그램 승인 카드가 끝내 발송되지 않았다.
recover_stalled_cards() 는 실제 카드 발송 SSOT(.review_card_msgids.json)로 판정을
분리해 이 틈을 메운다. 4가지 상태를 각각 검증한다:
  ① 아직 큐에 없음            → 손대지 않음(정상 신규 후보, 다른 흐름 몫)
  ② GM 확인 대기(플레이스홀더) → 보류 유지, 카드 미발송
  ③ GM 확인 완료 + 카드 미발송 → 카드 발송 트리거 + 재고표 마킹
  ④ 카드 이미 발송(SSOT)      → 멱등 — 재발송 안 함, 재고표만 뒤늦게 갱신
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


def _row(num, folder, status=None):
    return {
        "num": num, "num_raw": str(num), "track": "주말GM",
        "title": f"편{num}", "folder": folder,
        "status": status or csd.STOCK_STATUS,
    }


def _write_queue(path, items):
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_inventory(path, num, folder_rel, status):
    path.write_text(
        "## 재고 (표)\n| 편 | 트랙 | 제목 | 폴더 | 상태 |\n|---|---|---|---|---|\n"
        f"| {num} | 주말GM | 편{num} | {folder_rel} | {status} |\n",
        encoding="utf-8",
    )


def _stub_content(folder, num, gm_pending: bool):
    folder.mkdir(parents=True, exist_ok=True)
    text = "여기 [GM 확인: 뭔가] 채워야 함" if gm_pending else "확정된 최종 문구"
    (folder / f"ep{num:02d}_diary_source.html").write_text(text, encoding="utf-8")
    (folder / "caption.md").write_text(text, encoding="utf-8")


def _setup(monkeypatch, tmp_path):
    queue_path = tmp_path / "review_queue.json"
    msgid_store = tmp_path / ".review_card_msgids.json"
    inventory = tmp_path / "_실전사례_2주플랜.md"
    monkeypatch.setattr(csd, "ROOT", tmp_path)
    monkeypatch.setattr(csd, "REVIEW_QUEUE_PATH", queue_path)
    monkeypatch.setattr(csd, "CARD_MSGID_STORE", msgid_store)
    monkeypatch.setattr(csd, "INVENTORY", inventory)
    sent_calls = []
    monkeypatch.setattr(csd, "send_review_card", lambda qid: sent_calls.append(qid) or True)
    telegram_calls = []
    monkeypatch.setattr(csd, "telegram", lambda msg: telegram_calls.append(msg))
    return queue_path, msgid_store, inventory, sent_calls, telegram_calls


def test_not_yet_queued_is_untouched(tmp_path, monkeypatch):
    queue_path, msgid_store, inventory, sent, _tg = _setup(monkeypatch, tmp_path)
    folder = tmp_path / "case20"
    _stub_content(folder, 20, gm_pending=False)
    folder_rel = str(folder.relative_to(tmp_path)).replace("\\", "/")
    row = _row(20, folder_rel)
    _write_inventory(inventory, 20, folder_rel, csd.STOCK_STATUS)
    _write_queue(queue_path, [])  # 아직 등록 안 됨

    csd.recover_stalled_cards([row], "2026-07-19", dry_run=False)

    assert sent == []
    assert csd.STOCK_STATUS in inventory.read_text(encoding="utf-8")  # 표 무변경


def test_gm_confirm_pending_stays_held(tmp_path, monkeypatch):
    """CASE13 이 07-18 실제로 있었던 상태: 큐에는 있지만 [GM 확인] 미완료 → 카드 보류 유지."""
    queue_path, msgid_store, inventory, sent, _tg = _setup(monkeypatch, tmp_path)
    folder = tmp_path / "case14"
    _stub_content(folder, 14, gm_pending=True)
    folder_rel = str(folder.relative_to(tmp_path)).replace("\\", "/")
    row = _row(14, folder_rel)
    _write_inventory(inventory, 14, folder_rel, csd.STOCK_STATUS)
    _write_queue(queue_path, [{"id": "CMO-2026-07-19-CASE14-x", "status": "검수대기"}])

    csd.recover_stalled_cards([row], "2026-07-19", dry_run=False)

    assert sent == []  # 아직 GM 확인 전 — 카드 발송 시도 자체가 없어야 함
    assert csd.STOCK_STATUS in inventory.read_text(encoding="utf-8")  # 표도 그대로


def test_confirmed_and_unsent_triggers_card_and_marks_row(tmp_path, monkeypatch):
    """CASE13 을 오늘(07-19) GM이 확인 완료한 뒤의 실제 상황 재현 — 카드가 나가야 한다."""
    queue_path, msgid_store, inventory, sent, _tg = _setup(monkeypatch, tmp_path)
    folder = tmp_path / "case13"
    _stub_content(folder, 13, gm_pending=False)
    folder_rel = str(folder.relative_to(tmp_path)).replace("\\", "/")
    row = _row(13, folder_rel)
    _write_inventory(inventory, 13, folder_rel, csd.STOCK_STATUS)
    item_id = "CMO-2026-07-19-CASE13-오롯이쉼"
    _write_queue(queue_path, [{"id": item_id, "status": "검수대기"}])

    csd.recover_stalled_cards([row], "2026-07-19", dry_run=False)

    assert sent == [item_id]
    assert "검수발송(2026-07-19)" in inventory.read_text(encoding="utf-8")


def test_already_sent_card_is_idempotent_no_resend(tmp_path, monkeypatch):
    """카드 발송 SSOT(.review_card_msgids.json)에 이미 기록돼 있으면 절대 재발송하지 않음."""
    queue_path, msgid_store, inventory, sent, _tg = _setup(monkeypatch, tmp_path)
    folder = tmp_path / "case13"
    _stub_content(folder, 13, gm_pending=False)
    folder_rel = str(folder.relative_to(tmp_path)).replace("\\", "/")
    row = _row(13, folder_rel)
    _write_inventory(inventory, 13, folder_rel, csd.STOCK_STATUS)
    item_id = "CMO-2026-07-19-CASE13-오롯이쉼"
    _write_queue(queue_path, [{"id": item_id, "status": "검수대기"}])
    msgid_store.write_text(
        json.dumps({item_id: {"msg_id": 123, "sig": "x", "ts": 0}}), encoding="utf-8"
    )

    csd.recover_stalled_cards([row], "2026-07-19", dry_run=False)

    assert sent == []  # 멱등 — 재발송 없음
    assert "검수발송(2026-07-19)" in inventory.read_text(encoding="utf-8")  # 표만 뒤늦게 갱신


def test_dry_run_never_sends_or_writes(tmp_path, monkeypatch):
    """dry_run=True 는 확인 완료+미발송 케이스에서도 절대 발송·쓰기하지 않는다(안전 검증 경로)."""
    queue_path, msgid_store, inventory, sent, _tg = _setup(monkeypatch, tmp_path)
    folder = tmp_path / "case13"
    _stub_content(folder, 13, gm_pending=False)
    folder_rel = str(folder.relative_to(tmp_path)).replace("\\", "/")
    row = _row(13, folder_rel)
    _write_inventory(inventory, 13, folder_rel, csd.STOCK_STATUS)
    item_id = "CMO-2026-07-19-CASE13-오롯이쉼"
    _write_queue(queue_path, [{"id": item_id, "status": "검수대기"}])

    csd.recover_stalled_cards([row], "2026-07-19", dry_run=True)

    assert sent == []
    assert csd.STOCK_STATUS in inventory.read_text(encoding="utf-8")  # dry-run — 표 무변경
