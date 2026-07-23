"""
test_send_review_card_sibling_group.py — 공식 IG 승인카드 형제 4채널 자동그룹핑 회귀 테스트.
검증 대상: scripts/send_review_card.py _find_sibling_group_ids() / main() --id 자동그룹핑 배선.

배경(2026-07-22, 배9573 계열): 공식 L시리즈 승인카드가 IG 단독 id 카드로만 나가서, GM
[승인]이 IG 하나만 '승인'으로 바꾸고 블로그·카페·카카오·당근은 '검수대기'에 남아
자동발행·다이제스트가 끊겼다. 자동생산기(ig_series_producer.py)는
`send_review_card.py --id <id>` 단독 호출만 하므로, send_review_card.py 스스로
형제(검수대기/승인 상태)를 찾아 group_ids 를 구성해 pub:grp 그룹카드를 내야 한다.

두 축을 검증한다:
  ① 공식(account=='wellperion') IG + 형제 4채널(검수대기) → group_ids 5개(대표+형제4) 구성,
     실제 카드도 pub:grp:<hash> 콜백으로 나감.
  ② 개인(namuk.wellperion) IG 단독 → 형제가 있어도(가정) 그룹핑 대상 아님 → pub:<id> 단일 유지.
"""

import json
import os
import sys

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import send_review_card as src  # noqa: E402


def _official_ig_item(item_id="CMO-TEST-01"):
    return {
        "id": item_id,
        "title": "테스트편 — 인스타그램(공식)",
        "channel": "인스타그램 (wellperion 공식)",
        "account": "wellperion",
        "folder": "instagram/260101_테스트편",
        "status": "검수대기",
    }


def _sibling(item_id, suffix_channel, status="검수대기"):
    return {
        "id": item_id,
        "title": f"테스트편 — {suffix_channel}",
        "channel": suffix_channel,
        "account": "wellperion",
        "folder": "instagram/260101_테스트편/output(x)",
        "status": status,
    }


def _namuk_ig_item(item_id="CMO-TEST-02"):
    return {
        "id": item_id,
        "title": "개인 실전사례",
        "channel": "인스타그램 (namuk.wellperion)",
        "account": "namuk.wellperion",
        "folder": "instagram/namuk.wellperion/case02",
        "status": "검수대기",
    }


# ─────────────────────────────────────────────────────────────────────────────
# ① _find_sibling_group_ids 단위 검증
# ─────────────────────────────────────────────────────────────────────────────
def test_official_ig_collects_pending_and_approved_siblings():
    ig = _official_ig_item("CMO-TEST-01")
    items = [
        ig,
        _sibling("CMO-TEST-01-BLOG", "네이버 블로그", status="검수대기"),
        _sibling("CMO-TEST-01-CAFE", "네이버 카페 (동부이촌동)", status="검수대기"),
        _sibling("CMO-TEST-01-KAKAO", "카카오 채널", status="승인"),
        _sibling("CMO-TEST-01-DANGGN", "당근채널", status="검수대기"),
    ]
    sibling_ids = src._find_sibling_group_ids(ig, items)
    assert sibling_ids == [
        "CMO-TEST-01-BLOG", "CMO-TEST-01-CAFE", "CMO-TEST-01-KAKAO", "CMO-TEST-01-DANGGN",
    ]
    full_group = [ig["id"], *sibling_ids]
    assert len(full_group) == 5


def test_official_ig_id_with_ig_suffix_strips_base_correctly():
    ig = _official_ig_item("CMO-TEST-03-IG")
    items = [ig, _sibling("CMO-TEST-03-BLOG", "네이버 블로그")]
    sibling_ids = src._find_sibling_group_ids(ig, items)
    assert sibling_ids == ["CMO-TEST-03-BLOG"]


def test_siblings_not_pending_or_approved_are_excluded():
    """발행완료·폐기 상태 형제는 그룹핑 대상에서 제외(이미 처리됐거나 취소됨)."""
    ig = _official_ig_item("CMO-TEST-04")
    items = [
        ig,
        _sibling("CMO-TEST-04-BLOG", "네이버 블로그", status="발행완료"),
        _sibling("CMO-TEST-04-CAFE", "네이버 카페 (동부이촌동)", status="폐기"),
    ]
    sibling_ids = src._find_sibling_group_ids(ig, items)
    assert sibling_ids == []


def test_no_siblings_present_returns_empty_list():
    ig = _official_ig_item("CMO-TEST-05")
    sibling_ids = src._find_sibling_group_ids(ig, [ig])
    assert sibling_ids == []


def test_personal_namuk_account_excluded_even_with_matching_siblings():
    """개인계정은 그룹핑 대상 아님 — 형제 후보가 있어도(가정) 무시하고 빈 리스트."""
    namuk = _namuk_ig_item("CMO-TEST-06")
    items = [
        namuk,
        _sibling("CMO-TEST-06-BLOG", "네이버 블로그", status="검수대기"),
    ]
    sibling_ids = src._find_sibling_group_ids(namuk, items)
    assert sibling_ids == []


# ─────────────────────────────────────────────────────────────────────────────
# ② main() --id 자동그룹핑 배선 + 실제 카드 콜백데이터 검증 (네트워크는 모두 mock)
# ─────────────────────────────────────────────────────────────────────────────
def _isolate_card_stores(monkeypatch, tmp_path):
    monkeypatch.setattr(src, "CARD_LOCK", tmp_path / ".review_card.lock")
    monkeypatch.setattr(src, "CARD_MSGID_STORE", tmp_path / ".review_card_msgids.json")
    monkeypatch.setattr(src, "CARD_GROUPS_STORE", tmp_path / ".review_card_groups.json")
    monkeypatch.setattr(src, "_token", lambda: "FAKE-TOKEN")
    monkeypatch.setattr(src, "_preview_photo", lambda item: None)  # 텍스트 카드 폴백 강제


def test_main_id_flag_auto_groups_official_siblings(tmp_path, monkeypatch):
    ig = _official_ig_item("CMO-TEST-07")
    items = [
        ig,
        _sibling("CMO-TEST-07-BLOG", "네이버 블로그"),
        _sibling("CMO-TEST-07-CAFE", "네이버 카페 (동부이촌동)"),
        _sibling("CMO-TEST-07-KAKAO", "카카오 채널"),
        _sibling("CMO-TEST-07-DANGGN", "당근채널"),
    ]
    queue_path = tmp_path / "review_queue.json"
    queue_path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(src, "QUEUE", queue_path)
    _isolate_card_stores(monkeypatch, tmp_path)

    captured = {}

    def fake_send_text_card(token, caption, keyboard, item_id):
        captured["keyboard"] = keyboard
        captured["item_id"] = item_id
        return 999

    monkeypatch.setattr(src, "_send_text_card", fake_send_text_card)
    monkeypatch.setattr(sys, "argv", ["send_review_card.py", "--id", "CMO-TEST-07"])

    with pytest.raises(SystemExit) as exc:
        src.main()
    assert exc.value.code == 0

    cb = captured["keyboard"]["inline_keyboard"][0][0]["callback_data"]
    assert cb.startswith("pub:grp:"), cb
    grp_hash = cb.split(":")[2]
    stored_groups = json.loads((tmp_path / ".review_card_groups.json").read_text(encoding="utf-8"))
    assert stored_groups[grp_hash] == [
        "CMO-TEST-07", "CMO-TEST-07-BLOG", "CMO-TEST-07-CAFE",
        "CMO-TEST-07-KAKAO", "CMO-TEST-07-DANGGN",
    ]
    assert len(stored_groups[grp_hash]) == 5


def test_main_id_flag_personal_account_stays_single_card(tmp_path, monkeypatch):
    namuk = _namuk_ig_item("CMO-TEST-08")
    queue_path = tmp_path / "review_queue.json"
    queue_path.write_text(json.dumps([namuk], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(src, "QUEUE", queue_path)
    _isolate_card_stores(monkeypatch, tmp_path)

    captured = {}

    def fake_send_text_card(token, caption, keyboard, item_id):
        captured["keyboard"] = keyboard
        captured["item_id"] = item_id
        return 999

    monkeypatch.setattr(src, "_send_text_card", fake_send_text_card)
    monkeypatch.setattr(sys, "argv", ["send_review_card.py", "--id", "CMO-TEST-08"])

    with pytest.raises(SystemExit) as exc:
        src.main()
    assert exc.value.code == 0

    cb = captured["keyboard"]["inline_keyboard"][0][0]["callback_data"]
    assert cb == "pub:CMO-TEST-08:approve"


def test_main_id_flag_explicit_group_ids_not_overridden(tmp_path, monkeypatch):
    """--group-ids 를 사용자가 명시하면 자동그룹핑 로직이 끼어들지 않는다(기존 수동경로 무회귀)."""
    ig = _official_ig_item("CMO-TEST-09")
    other = _sibling("CMO-TEST-09-BLOG", "네이버 블로그")
    queue_path = tmp_path / "review_queue.json"
    queue_path.write_text(json.dumps([ig, other], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(src, "QUEUE", queue_path)
    _isolate_card_stores(monkeypatch, tmp_path)

    captured = {}

    def fake_send_text_card(token, caption, keyboard, item_id):
        captured["keyboard"] = keyboard
        return 999

    monkeypatch.setattr(src, "_send_text_card", fake_send_text_card)
    # 사용자가 명시적으로 형제 없이 자기 자신만 지정 — 자동탐지가 개입해 형제를 덧붙이면 안 됨.
    monkeypatch.setattr(
        sys, "argv",
        ["send_review_card.py", "--id", "CMO-TEST-09", "--group-ids", "CMO-TEST-09"],
    )

    with pytest.raises(SystemExit) as exc:
        src.main()
    assert exc.value.code == 0

    cb = captured["keyboard"]["inline_keyboard"][0][0]["callback_data"]
    grp_hash = cb.split(":")[2]
    stored_groups = json.loads((tmp_path / ".review_card_groups.json").read_text(encoding="utf-8"))
    assert stored_groups[grp_hash] == ["CMO-TEST-09"]  # 형제 자동추가 없음(명시값 그대로 존중)
