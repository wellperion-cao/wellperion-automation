"""
test_publish_digest.py — 발행완료→문의방 통합요약 자동발신 pytest.
검증 대상: scripts/publish_digest.py (+ ig_review_publish_watcher.py 배선)

★ 실제 텔레그램 전송은 절대 하지 않는다 — 전송 함수(_send)는 항상 monkeypatch로
  가로채거나, dry_run=True 로만 호출한다.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import publish_digest as pd  # noqa: E402


# ---------------------------------------------------------------------------
# 실제 L1 수영 5항목 (review_queue.json 실데이터 축약) — IG 루트 + output(채널) 4종
# ---------------------------------------------------------------------------
def _l1_swim_items() -> list[dict]:
    return [
        {
            "id": "CMO-2026-07-14-LSERIES-L1-SWIM",
            "title": "L시리즈 성인강습 1/6 — 수영(디지털 디톡스)",
            "digest_title": "성인 수영 강습(디지털 디톡스)",
            "digest_intro": "하루 30분, 휴대폰이 멈추는 시간. 한남동에서 성인도 0에서 천천히 시작하는 수영 강습을 소개했습니다.",
            "folder": "instagram/260715_L1_수영",
            "channel": "인스타그램 (wellperion 공식)",
            "status": "발행완료",
            "post_url": "https://www.instagram.com/p/Day7fIBEphf/",
            "published_at": "2026-07-15T10:53:13",
        },
        {
            "id": "CMO-2026-07-15-LSERIES-L1-SWIM-BLOG",
            "title": "하루 30분, 휴대폰이 멈추는 시간 — 한남동 성인 수영",
            "folder": "instagram/260715_L1_수영/output(블로그)",
            "channel": "네이버 블로그",
            "status": "발행완료",
            "post_url": "https://blog.naver.com/PostView.naver?blogId=wellperion&logNo=224347229166",
            "published_at": "2026-07-15T11:36:45",
        },
        {
            "id": "CMO-2026-07-15-LSERIES-L1-SWIM-CAFE",
            "title": "한남동에서 30분, 수영으로 디지털 디톡스",
            "folder": "instagram/260715_L1_수영/output(카페)",
            "channel": "네이버 카페 (동부이촌동)",
            "status": "발행완료",
            "post_url": "https://cafe.naver.com/ichon1dong?iframe_url_utf8=x",
            "published_at": "2026-07-15T11:37:26",
        },
        {
            "id": "CMO-2026-07-15-LSERIES-L1-SWIM-KAKAO",
            "title": "한남동 성인 수영 — 디지털 디톡스 (카카오 채널)",
            "folder": "instagram/260715_L1_수영/output(카카오 채널)",
            "channel": "카카오 채널",
            "status": "발행완료",
            "post_url": "https://business.kakao.com/_cgxiKj/posts/113972104",
            "published_at": "2026-07-15T11:38:02",
        },
        {
            "id": "CMO-2026-07-15-LSERIES-L1-SWIM-DANGGN",
            "title": "한남동 성인 수영 강습 — 0에서 천천히 시작해요 (당근)",
            "folder": "instagram/260715_L1_수영/output(당근)",
            "channel": "당근채널",
            "status": "발행완료",
            "post_url": "https://www.daangn.com/kr/business-posts/6a56f6bbfdb9c12e29b2676a",
            "published_at": None,
        },
    ]


def _tmp_ledger_path() -> Path:
    fd, path = tempfile.mkstemp(prefix="publish_digest_sent_", suffix=".json")
    os.close(fd)
    os.remove(path)  # 시작은 파일 없음(첫 발신) 상태로
    return Path(path)


# ---------------------------------------------------------------------------
# ① 그룹핑 — 5항목 → 1그룹, 메시지에 5개 채널 링크 전부 포함
# ---------------------------------------------------------------------------
def test_group_published_merges_5_channels_into_1_content():
    items = _l1_swim_items()
    groups = pd.group_published(items)
    assert len(groups) == 1, f"1콘텐츠로 묶여야 함, 실제 그룹키: {list(groups.keys())}"
    key, group = next(iter(groups.items()))
    assert key == "instagram/260715_L1_수영"
    assert len(group) == 5

    msg = pd.build_digest(group)
    urls = [it["post_url"] for it in items]
    for url in urls:
        assert url in msg, f"메시지에 채널 링크 누락: {url}"

    # 리치 포맷 헤더 — 📢 웰페리온 공식 · {digest_title} 발행 완료 — 응원 부탁드려요!
    assert msg.startswith("📢 웰페리온 공식 · 성인 수영 강습(디지털 디톡스) 발행 완료 — 응원 부탁드려요!")
    # digest_intro 반영
    assert "하루 30분, 휴대폰이 멈추는 시간. 한남동에서 성인도 0에서 천천히 시작하는 수영 강습을 소개했습니다." in msg
    # 좋아요·댓글 유도 문구
    assert "아래 링크에서 ❤️ 좋아요 · 💬 댓글 남겨주시면 큰 힘이 됩니다 🙏" in msg
    assert msg.rstrip().endswith("좋아요·댓글로 응원 부탁드립니다 🙏")

    # 채널 5종 모두 이모지 라벨로 포함 + 고정 순서(인스타→블로그→카페→카카오→당근)
    labels = ["📷 인스타그램", "📝 네이버 블로그", "☕ 네이버 카페", "💬 카카오채널", "🥕 당근"]
    for label in labels:
        assert label in msg, f"메시지에 채널 이모지 라벨 누락: {label}"
    positions = [msg.index(label) for label in labels]
    assert positions == sorted(positions), "채널 순서가 인스타→블로그→카페→카카오→당근 고정 순서를 위반함"


# ---------------------------------------------------------------------------
# ② 대상방 — chat_id == TELEGRAM_INQUIRY_CHAT_ID (GM채널 아님)
# ---------------------------------------------------------------------------
def test_sends_to_inquiry_chat_id_not_gm_channel(monkeypatch):
    captured = {}

    def fake_send(token, chat_id, text, preview_url=""):
        captured["token"] = token
        captured["chat_id"] = chat_id
        captured["text"] = text
        captured["preview_url"] = preview_url
        return True

    monkeypatch.setattr(pd, "_send", fake_send)
    ledger_path = _tmp_ledger_path()
    try:
        expected_chat_id = pd._load_env_val(pd.TELEGRAM_INQUIRY_CHAT_ID_ENV_KEY)
        gm_chat_id = pd._load_env_val("TELEGRAM_CHAT_ID")
        assert expected_chat_id, "테스트 전제: TELEGRAM_INQUIRY_CHAT_ID가 .env에 설정돼 있어야 함"

        sent = pd.send_publish_digest(_l1_swim_items(), dry_run=False, ledger_path=ledger_path)

        assert sent == 1
        assert captured["chat_id"] == expected_chat_id
        assert captured["chat_id"] != gm_chat_id or not gm_chat_id, "GM 채널로 가면 안 됨"
        # 인스타그램 미리보기 카드 URL이 그룹의 인스타 post_url로 전달됐는지
        assert captured["preview_url"] == "https://www.instagram.com/p/Day7fIBEphf/"
    finally:
        if ledger_path.exists():
            ledger_path.unlink()


# ---------------------------------------------------------------------------
# ②-1 인스타그램 미리보기 카드 — _send payload에 link_preview_options 실제 실림
# ---------------------------------------------------------------------------
def test_send_payload_includes_instagram_link_preview_options(monkeypatch):
    """_send()가 sendMessage 요청 바디에 link_preview_options(JSON)를 실어
    인스타 게시물이 본문 위 큰 이미지 카드로 뜨게 하는지 (urlopen 자체를 가로채 검증)."""
    import urllib.parse as _urlparse

    captured_data = {}

    class _FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=10):
        captured_data["body"] = _urlparse.parse_qs(req.data.decode("utf-8"))
        return _FakeResp()

    monkeypatch.setattr(pd.urllib.request, "urlopen", fake_urlopen)

    ok = pd._send(
        "FAKE_TOKEN", "12345", "본문 텍스트",
        preview_url="https://www.instagram.com/p/Day7fIBEphf/",
    )

    assert ok is True
    assert "link_preview_options" in captured_data["body"], "link_preview_options가 payload에 없음"
    opts = json.loads(captured_data["body"]["link_preview_options"][0])
    assert opts["url"] == "https://www.instagram.com/p/Day7fIBEphf/"
    assert opts["prefer_large_media"] is True
    assert opts["show_above_text"] is True
    # 기존 disable_web_page_preview(미리보기 끄는 옵션)는 더 이상 실리지 않아야 함
    assert "disable_web_page_preview" not in captured_data["body"]


def test_send_payload_omits_link_preview_options_without_instagram_url(monkeypatch):
    """인스타 URL이 없으면 link_preview_options를 생략하고 정상 발송(에러 없이)."""
    import urllib.parse as _urlparse

    captured_data = {}

    class _FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=10):
        captured_data["body"] = _urlparse.parse_qs(req.data.decode("utf-8"))
        return _FakeResp()

    monkeypatch.setattr(pd.urllib.request, "urlopen", fake_urlopen)

    ok = pd._send("FAKE_TOKEN", "12345", "본문 텍스트")

    assert ok is True
    assert "link_preview_options" not in captured_data["body"]


# ---------------------------------------------------------------------------
# ③ 조용한 실패 금지 — 토큰 없으면 [ERROR] + 전송 시도 안 함
# ---------------------------------------------------------------------------
def test_missing_token_logs_error_and_does_not_send(monkeypatch, capsys):
    def fake_send(*a, **k):
        raise AssertionError("토큰 미설정인데 전송을 시도함 — 조용한 실패 금지 위반")

    monkeypatch.setattr(pd, "_send", fake_send)
    monkeypatch.setattr(pd, "_load_env_val", lambda key: "")  # 토큰·챗ID 전부 미설정 시뮬레이션

    ledger_path = _tmp_ledger_path()
    try:
        sent = pd.send_publish_digest(_l1_swim_items(), dry_run=False, ledger_path=ledger_path)
        assert sent == 0
        err = capsys.readouterr().err
        assert "[ERROR]" in err
    finally:
        if ledger_path.exists():
            ledger_path.unlink()


# ---------------------------------------------------------------------------
# ④ 멱등 — 같은 콘텐츠 2회 호출 시 2번째는 전송 0건
# ---------------------------------------------------------------------------
def test_idempotent_second_call_sends_zero(monkeypatch):
    calls = []

    def fake_send(token, chat_id, text, preview_url=""):
        calls.append(text)
        return True

    monkeypatch.setattr(pd, "_send", fake_send)
    ledger_path = _tmp_ledger_path()
    try:
        first = pd.send_publish_digest(_l1_swim_items(), dry_run=False, ledger_path=ledger_path)
        second = pd.send_publish_digest(_l1_swim_items(), dry_run=False, ledger_path=ledger_path)

        assert first == 1
        assert second == 0, "동일 콘텐츠 재발신 — 멱등 위반"
        assert len(calls) == 1, "실제 발신 호출은 1회만 있어야 함"
        # 원장에 그룹키 기록됐는지 확인
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        assert "instagram/260715_L1_수영" in ledger
    finally:
        if ledger_path.exists():
            ledger_path.unlink()


# ---------------------------------------------------------------------------
# ⑤ 배선 발동 — 감시기(run) 이번 사이클 '발행완료' 전환 항목으로 digest 실제 호출
# ---------------------------------------------------------------------------
def test_watcher_dispatch_calls_digest_only_for_newly_published(monkeypatch):
    """실브라우저·git·네트워크 없이: ig_review_publish_watcher._dispatch_publish_digest 가
    approved 리스트 중 '발행완료'로 전환된 것만 send_publish_digest 로 넘기는지 검증.
    이 함수는 _run_once_inner() 가 실제 호출하는 그 함수(같은 코드 경로) — 발동지점 실증."""
    import ig_review_publish_watcher as watcher

    captured = {}

    def fake_send_publish_digest(items, dry_run=False, ledger_path=None):
        captured["items"] = items
        return len(items)

    monkeypatch.setattr(watcher, "send_publish_digest", fake_send_publish_digest)

    approved = [
        {"id": "A-1", "status": "발행완료", "folder": "instagram/x", "channel": "인스타그램",
         "post_url": "https://example.com/a"},
        {"id": "A-2", "status": "발행실패", "folder": "instagram/y", "channel": "블로그"},
        {"id": "A-3", "status": "수동발행대기", "folder": "instagram/z", "channel": "카카오"},
    ]

    sent = watcher._dispatch_publish_digest(approved)

    assert sent == 1, "발행완료 1건만 digest로 전달돼야 함"
    assert len(captured["items"]) == 1
    assert captured["items"][0]["id"] == "A-1"

    # run 함수 소스에 실제 호출부가 존재함을 실행경로로도 재확인(정적 우회 방지)
    import inspect
    src = inspect.getsource(watcher._run_once_inner)
    assert "_dispatch_publish_digest(approved)" in src


def test_watcher_dispatch_no_newly_published_skips_digest(monkeypatch):
    """발행완료 전환 항목이 하나도 없으면 send_publish_digest 자체를 호출하지 않는다."""
    import ig_review_publish_watcher as watcher

    called = {"n": 0}

    def fake_send_publish_digest(items, dry_run=False, ledger_path=None):
        called["n"] += 1
        return 0

    monkeypatch.setattr(watcher, "send_publish_digest", fake_send_publish_digest)

    approved = [{"id": "B-1", "status": "발행실패", "folder": "instagram/y"}]
    sent = watcher._dispatch_publish_digest(approved)

    assert sent == 0
    assert called["n"] == 0
