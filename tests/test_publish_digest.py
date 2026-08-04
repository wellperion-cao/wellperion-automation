"""
test_publish_digest.py — 발행완료→문의방 통합요약 자동발신 pytest.
검증 대상: scripts/publish_digest.py (+ ig_review_publish_watcher.py 배선)

★ 실제 텔레그램 전송은 절대 하지 않는다 — 전송 함수(_send)는 항상 monkeypatch로
  가로채거나, dry_run=True 로만 호출한다.
"""

import datetime
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
    # (2026-07-31 GM 확정: 보고 맨 위에 북극성 대비 블록이 붙을 수 있어 startswith 대신
    #  포함 여부로 검증 — northstar_reach.build_northstar_block() 은 이 헤더보다 앞선다)
    assert "📢 웰페리온 공식 · 성인 수영 강습(디지털 디톡스) 발행 완료 — 응원 부탁드려요!" in msg
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
    """★ 2026-08-04 GM 검토 게이트 도입으로 계약이 뒤집혔다: 1차 호출은 실무진 방이 아니라
    GM 업무보고방(TELEGRAM_CHAT_ID)에 승인/보류 버튼 카드가 가고 실무진 방은 0건이어야
    한다. ledger[f"{folder}:gm_ok"]=True 를 심고 재호출해야 비로소 실무진 방
    (TELEGRAM_INQUIRY_CHAT_ID)으로 1건 나간다 — '실무진 방으로 잘못 새나가면 안 된다'는
    이 테스트의 본래 목적은 두 단계 모두 단언해 그대로 지킨다."""
    calls = []

    def fake_send(token, chat_id, text, preview_url="", reply_markup=""):
        calls.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return True

    monkeypatch.setattr(pd, "_send", fake_send)
    # ★ 2026-07-18 시토: L1 수영 콘텐츠의 실제 슬라이드 이미지가 리포에 존재해
    #   _send_photo(미모킹) 실경로로 빠져 실제 텔레그램 전송이 발생하던 안전결함 수리.
    #   이 테스트는 _send(텍스트) 경로 검증이 목적이므로 이미지 경로를 결정적으로 차단한다.
    monkeypatch.setattr(pd, "_first_slide_image", lambda group: "")
    ledger_path = _tmp_ledger_path()
    try:
        expected_inquiry_chat_id = pd._load_env_val(pd.TELEGRAM_INQUIRY_CHAT_ID_ENV_KEY)
        gm_chat_id = pd._load_env_val("TELEGRAM_CHAT_ID")
        assert expected_inquiry_chat_id, "테스트 전제: TELEGRAM_INQUIRY_CHAT_ID가 .env에 설정돼 있어야 함"
        assert gm_chat_id, "테스트 전제: TELEGRAM_CHAT_ID가 .env에 설정돼 있어야 함"

        # 1차 호출 — GM 검토 카드만 나가고 실무진 방은 0건
        sent = pd.send_publish_digest(_l1_swim_items(), dry_run=False, ledger_path=ledger_path)
        assert sent == 0, "GM 승인 전에는 실무진 방으로 나가면 안 됨"
        assert len(calls) == 1
        assert calls[0]["chat_id"] == gm_chat_id
        assert calls[0]["chat_id"] != expected_inquiry_chat_id
        assert calls[0]["reply_markup"], "검토 카드에는 승인/보류 버튼이 실려야 함"

        # GM 승인 — ledger[f"{folder}:gm_ok"]=True 를 심고 재호출하면 실무진 방으로 실제 발신
        ledger = pd._load_ledger(ledger_path)
        ledger["instagram/260715_L1_수영:gm_ok"] = True
        pd._save_ledger(ledger_path, ledger)
        calls.clear()
        sent2 = pd.send_publish_digest(_l1_swim_items(), dry_run=False, ledger_path=ledger_path)
        assert sent2 == 1
        assert calls[0]["chat_id"] == expected_inquiry_chat_id
        assert calls[0]["chat_id"] != gm_chat_id
    finally:
        if ledger_path.exists():
            ledger_path.unlink()


# ---------------------------------------------------------------------------
# ②-1 인스타그램 미리보기 카드 — _send payload에 link_preview_options 실제 실림
# ---------------------------------------------------------------------------
def test_send_payload_includes_instagram_link_preview_options(monkeypatch):
    """_send()가 sendMessage 요청 바디에 link_preview_options(JSON)를 싣는지 검증
    (urlopen 자체를 가로채 검증).
    ★ 2026-07-18 시토 수정: 2026-07-16 진단(IG 링크 미리보기가 텔레그램 429 유발)으로
    _send()가 미리보기를 항상 비활성(is_disabled=True)하도록 바뀐 뒤 테스트가 갱신되지
    않아 옛 동작(prefer_large_media/show_above_text 카드)을 계속 단언하며 실패하던 드리프트
    수리 — 현재 코드의 실제 계약(is_disabled=True 항상 실림)에 맞춘다."""
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
    assert opts["is_disabled"] is True
    # 기존 disable_web_page_preview(구식 옵션명)는 실리지 않아야 함
    assert "disable_web_page_preview" not in captured_data["body"]


def test_send_payload_disables_link_preview_without_instagram_url(monkeypatch):
    """인스타 URL이 없어도 link_preview_options(is_disabled=True)는 여전히 실려 정상 발송된다.
    ★ 2026-07-18 시토 수정: 옛 이름은 '미리보기 옵션 생략'이었으나, 2026-07-16부터 _send()는
    preview_url 유무와 무관하게 항상 미리보기를 비활성화한다(429 방지) — 그 계약에 맞춘다."""
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
    assert "link_preview_options" in captured_data["body"]
    opts = json.loads(captured_data["body"]["link_preview_options"][0])
    assert opts["is_disabled"] is True


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
    """★ 2026-08-04: GM 검토 게이트가 생겨도 멱등은 여전히 지켜야 하는 성질이다(낡은 계약이
    아니라 유지 대상) — GM 검토 카드도 같은 folder 재유입 시 1회만(ledger[f"{folder}:gm_review"]),
    승인 후 실무진 방 실발신도 1회만(ledger[key]) 나가야 한다. 두 단계 각각의 멱등을 확장해
    단언한다."""
    calls = []

    def fake_send(token, chat_id, text, preview_url="", reply_markup=""):
        calls.append(chat_id)
        return True

    monkeypatch.setattr(pd, "_send", fake_send)
    # ★ 2026-07-18 시토: 실제 슬라이드 이미지 존재 시 _send_photo(미모킹) 실경로로 빠지는
    #   안전결함 수리 — 이 테스트는 _send 호출 횟수 검증이 목적이라 이미지 경로를 차단한다.
    monkeypatch.setattr(pd, "_first_slide_image", lambda group: "")
    ledger_path = _tmp_ledger_path()
    try:
        # ① GM 검토 카드 — 승인 전엔 같은 folder 재호출해도 1회만
        first = pd.send_publish_digest(_l1_swim_items(), dry_run=False, ledger_path=ledger_path)
        second = pd.send_publish_digest(_l1_swim_items(), dry_run=False, ledger_path=ledger_path)
        assert first == 0 and second == 0, "GM 승인 전엔 실무진 방 발신 0건"
        assert len(calls) == 1, "GM 검토 카드도 같은 folder 재유입 시 재발송 금지 — 멱등 위반"

        # ② GM 승인 후 — 실무진 방 실발신도 재호출 시 1회만
        ledger = pd._load_ledger(ledger_path)
        ledger["instagram/260715_L1_수영:gm_ok"] = True
        pd._save_ledger(ledger_path, ledger)
        third = pd.send_publish_digest(_l1_swim_items(), dry_run=False, ledger_path=ledger_path)
        fourth = pd.send_publish_digest(_l1_swim_items(), dry_run=False, ledger_path=ledger_path)
        assert third == 1 and fourth == 0, "승인 후 실무진 방 재발신 — 멱등 위반"
        assert len(calls) == 2, "실무진 방 실제 발신 호출은 승인 뒤 1회만 있어야 함"

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
    """★ 2026-08-04(배C): approved(이번 사이클 전환분)만 넘기던 옛 계약은 폐기됐다 — 발행
    당일 5채널이 안 모였다가 나중 사이클에 채워진 folder 가 approved 에 안 잡혀 영원히
    재검사되지 않던 결함(L3~L6, 17일 미발신) 수리. 새 계약: review_queue 전체
    (_load_review_queue())를 approved 내용과 무관하게 그대로 send_publish_digest 로 넘긴다
    (원장 멱등 체크가 재발송을 막아 안전). 이 함수는 _run_once_inner() 가 실제 호출하는 그
    함수(같은 코드 경로) — 발동지점 실증은 유지."""
    import ig_review_publish_watcher as watcher

    captured = {}

    def fake_send_publish_digest(items, dry_run=False, ledger_path=None):
        captured["items"] = items
        return len(items)

    monkeypatch.setattr(watcher, "send_publish_digest", fake_send_publish_digest)

    queue_fixture = [
        {"id": "Q-1", "status": "발행완료", "folder": "instagram/q1", "channel": "인스타그램"},
        {"id": "Q-2", "status": "검수대기", "folder": "instagram/q2", "channel": "블로그"},
    ]
    monkeypatch.setattr(watcher, "_load_review_queue", lambda: queue_fixture)

    # approved 는 옛 계약의 필터 대상이었으나 새 계약에선 내용과 무관 — 일부러 다른 값으로 둔다.
    approved = [
        {"id": "A-1", "status": "발행완료", "folder": "instagram/x", "channel": "인스타그램",
         "post_url": "https://example.com/a"},
        {"id": "A-2", "status": "발행실패", "folder": "instagram/y", "channel": "블로그"},
    ]

    sent = watcher._dispatch_publish_digest(approved)

    assert sent == len(queue_fixture)
    assert captured["items"] == queue_fixture, "approved 가 아니라 review_queue 전체를 넘겨야 함(새 계약)"

    # run 함수 소스에 실제 호출부가 존재함을 실행경로로도 재확인(정적 우회 방지)
    import inspect
    src = inspect.getsource(watcher._run_once_inner)
    assert "_dispatch_publish_digest(approved)" in src


def test_watcher_dispatch_no_newly_published_skips_digest(monkeypatch):
    """★ 2026-08-04(배C): 반대로 뒤집힌 계약 — 이번 사이클에 새로 '발행완료'로 전환된 게
    approved 에 하나도 없어도 digest 는 여전히 호출돼야 한다(과거 미완결 folder 재훑기가
    목적이라, 여기서 early-return 하면 재훑기 자체가 죽는다)."""
    import ig_review_publish_watcher as watcher

    called = {"n": 0}

    def fake_send_publish_digest(items, dry_run=False, ledger_path=None):
        called["n"] += 1
        return 0

    monkeypatch.setattr(watcher, "send_publish_digest", fake_send_publish_digest)
    monkeypatch.setattr(watcher, "_load_review_queue", lambda: [{"id": "Q-1", "folder": "instagram/q1"}])

    approved = [{"id": "B-1", "status": "발행실패", "folder": "instagram/y"}]
    sent = watcher._dispatch_publish_digest(approved)

    assert sent == 0
    assert called["n"] == 1, "approved 에 신규 전환분이 없어도 digest 호출을 스킵하면 안 됨(재훑기 목적)"


# ---------------------------------------------------------------------------
# ⑥ 게이트 완화 (2026-07-22) — URL 미회수(카카오·블로그)여도 상태만 완료면 그룹 완결
#    + 홈 URL 폴백으로 '1이미지+5링크' 표준 유지. 회귀: 개인 IG단독·미완료그룹은 그대로.
# ---------------------------------------------------------------------------
def _official_group_entries_url_gaps() -> list[dict]:
    """공식(wellperion) 5채널 전부 발행완료이나 카카오·블로그 post_url이 빈 픽스처."""
    return [
        {
            "id": "CMO-TEST-URLGAP-IG", "account": "wellperion",
            "folder": "instagram/260722_URL갭테스트", "channel": "인스타그램 (wellperion 공식)",
            "status": "발행완료", "post_url": "https://www.instagram.com/p/urlgapTest/",
            "published_at": "2026-07-22T10:00:00",
        },
        {
            "id": "CMO-TEST-URLGAP-BLOG", "account": "wellperion",
            "folder": "instagram/260722_URL갭테스트/output(블로그)", "channel": "네이버 블로그",
            "status": "발행완료", "post_url": "",  # ★ URL 미회수
            "published_at": "2026-07-22T10:05:00",
        },
        {
            "id": "CMO-TEST-URLGAP-CAFE", "account": "wellperion",
            "folder": "instagram/260722_URL갭테스트/output(카페)", "channel": "네이버 카페 (동부이촌동)",
            "status": "발행완료", "post_url": "https://cafe.naver.com/ichon1dong?iframe_url_utf8=x",
            "published_at": "2026-07-22T10:06:00",
        },
        {
            "id": "CMO-TEST-URLGAP-KAKAO", "account": "wellperion",
            "folder": "instagram/260722_URL갭테스트/output(카카오 채널)", "channel": "카카오 채널",
            "status": "발행완료", "post_url": "",  # ★ 카카오 = 편별 공개 URL 원래 없음
            "published_at": "2026-07-22T10:07:00",
        },
        {
            "id": "CMO-TEST-URLGAP-DANGGN", "account": "wellperion",
            "folder": "instagram/260722_URL갭테스트/output(당근)", "channel": "당근채널",
            "status": "발행완료", "post_url": "https://www.daangn.com/kr/business-posts/testpost",
            "published_at": "2026-07-22T10:08:00",
        },
    ]


def test_group_is_complete_true_when_kakao_and_blog_url_blank():
    """5채널 전부 발행완료면 카카오·블로그 post_url이 비어 있어도 완결(True) —
    게이트 완화 핵심 단언(2026-07-22). 실 review_queue.json은 건드리지 않고 픽스처만 사용."""
    entries = _official_group_entries_url_gaps()
    key = pd._base_key(entries[0])

    complete, reason = pd._group_is_complete(key, entries)

    assert complete is True, f"URL 미회수여도 상태 전부 완료면 True여야 함 (사유: {reason})"
    assert reason == ""


def test_build_digest_falls_back_to_channel_home_when_url_missing():
    """URL 미회수 채널(카카오·블로그)은 링크 목록에서 정본 채널 홈 URL로 폴백 —
    '1이미지+5링크' 표준 유지 + 게시글 링크와 헷갈리지 않게 표기 구분."""
    entries = _official_group_entries_url_gaps()
    dedup = pd._dedup_channel_entries(entries)
    assert len(dedup) == 5, "채널 5종 전부 링크 조립 대상이어야 함"

    msg = pd.build_digest(dedup)

    # 실제 URL이 있는 채널은 그대로 노출
    assert "https://www.instagram.com/p/urlgapTest/" in msg
    assert "https://cafe.naver.com/ichon1dong" in msg
    assert "https://www.daangn.com/kr/business-posts/testpost" in msg
    # URL 미회수 채널(블로그·카카오)은 채널 홈으로 폴백 + 게시글 링크와 구분 표기
    assert "https://blog.naver.com/wellperion (채널 홈 · 게시글 링크 미확정)" in msg
    assert "https://pf.kakao.com/_cgxiKj (채널 홈 · 게시글 링크 미확정)" in msg
    # 채널 이모지 라벨 5종 전부 여전히 포함(누락 없음)
    for label in ["📷 인스타그램", "📝 네이버 블로그", "☕ 네이버 카페", "💬 카카오채널", "🥕 당근"]:
        assert label in msg


def test_send_publish_digest_sends_with_url_gaps_via_fixture(monkeypatch):
    """★ 2026-08-04: URL 갭이 있어도 채널 이름 노출(카카오 홈 폴백 등) 기존 성질은 그대로
    유지하되, GM 검토 게이트 도입으로 1차 목적지가 실무진 방이 아니라 GM 업무보고방으로
    바뀐 것만 반영한다(승인 전이라 sent==0). 픽스처로 _load_review_queue를 격리해 실제
    review_queue.json은 절대 건드리지 않는다."""
    entries = _official_group_entries_url_gaps()

    monkeypatch.setattr(pd, "_load_review_queue", lambda: entries)
    monkeypatch.setattr(pd, "_first_slide_image", lambda group: "")  # 실제 이미지 첨부 경로 차단

    captured = {}

    def fake_send(token, chat_id, text, preview_url="", reply_markup=""):
        captured["chat_id"] = chat_id
        captured["text"] = text
        return True

    monkeypatch.setattr(pd, "_send", fake_send)

    ledger_path = _tmp_ledger_path()
    try:
        gm_chat_id = pd._load_env_val("TELEGRAM_CHAT_ID")
        sent = pd.send_publish_digest(entries, dry_run=False, ledger_path=ledger_path)
        assert sent == 0, "GM 승인 전에는 실무진 방 발신 0건(게이트)"
        assert captured["chat_id"] == gm_chat_id
        assert "https://pf.kakao.com/_cgxiKj (채널 홈 · 게시글 링크 미확정)" in captured["text"]
    finally:
        if ledger_path.exists():
            ledger_path.unlink()


def test_group_is_complete_personal_ig_solo_still_true_no_url_required():
    """회귀: 개인(namuk) IG 단독 그룹은 5채널 강제 미적용 — URL 게이트 완화 이후에도
    여전히 완결(True) 판정돼야 한다."""
    entries = [
        {
            "id": "CMO-TEST-PERSONAL-IG", "account": "namuk.wellperion",
            "folder": "instagram/260722_개인단독", "channel": "인스타그램 (namuk 개인)",
            "status": "발행완료", "post_url": "https://www.instagram.com/p/personalSolo/",
            "published_at": "2026-07-22T09:00:00",
        },
    ]
    key = pd._base_key(entries[0])

    complete, reason = pd._group_is_complete(key, entries)

    assert complete is True, f"개인 IG단독 그룹은 여전히 True여야 함 (사유: {reason})"


def test_group_is_complete_still_false_when_channel_pending_review():
    """회귀: 일부 채널이 검수대기(미발행 상태)면 URL 게이트 완화와 무관하게 여전히 False."""
    entries = _official_group_entries_url_gaps()
    entries[1] = {**entries[1], "status": "검수대기", "post_url": ""}  # 블로그만 아직 검수대기
    key = pd._base_key(entries[0])

    complete, reason = pd._group_is_complete(key, entries)

    assert complete is False, "일부 채널 미발행이면 여전히 False여야 함"
    assert "미발행" in reason


# ---------------------------------------------------------------------------
# ⑦ D(2026-08-04) — 디제스트 본문 발행일 표기: 2일 이상 지난 것만, 지어내지 않는다
# ---------------------------------------------------------------------------
def test_build_digest_shows_publish_date_only_when_2days_or_older():
    """2일 이상 지난 콘텐츠만 '📅 YYYY-MM-DD 발행' 표기 — 최신 건·published_at 없는 건은
    생략(지어내지 않는다, 약속 L05)."""
    old_group = [{"title": "옛날 글", "channel": "인스타그램", "published_at": "2020-01-01T00:00:00"}]
    assert "📅 2020-01-01 발행" in pd.build_digest(old_group)

    fresh_group = [{"title": "오늘 글", "channel": "인스타그램",
                     "published_at": datetime.date.today().isoformat() + "T00:00:00"}]
    assert "📅" not in pd.build_digest(fresh_group)

    no_date_group = [{"title": "날짜없음", "channel": "인스타그램"}]
    assert "📅" not in pd.build_digest(no_date_group)


# ---------------------------------------------------------------------------
# ⑧ E(2026-08-04) — 채널별 /output(...) 접미 병합 회귀 방지
# ---------------------------------------------------------------------------
def test_base_key_merges_trailing_output_suffix_only():
    """_base_key()는 folder 끝의 /output(채널) 접미만 벗겨 base 로 병합한다. 끝이 아니라
    중간 세그먼트(예: KPGA 처럼 output(...) 뒤에 /epN 이 더 붙는 실데이터 패턴)는 원문 그대로
    유지돼 실제로 동일한 folder 값을 공유하는 그룹과 충돌하지 않는다(E 조사 회귀 방지)."""
    assert pd._base_key({"folder": "instagram/260715_L1_수영/output(블로그)"}) == "instagram/260715_L1_수영"
    assert pd._base_key({"folder": "instagram/260715_L1_수영"}) == "instagram/260715_L1_수영"
    kpga = "instagram/260620_골프_유소년_KPGA주니어대회/output(인스타그램)/ep1"
    assert pd._base_key({"folder": kpga}) == kpga  # 끝이 아니므로 그대로(의도된 동작)
