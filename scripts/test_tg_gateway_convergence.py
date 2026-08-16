"""배255(2026-08-08 웰리 지적) — 텔레그램 발신은 관문(tg_outbound_log.send) 하나만 지나야 한다.

1차(2026-08-17): sendMessage 직접호출 수렴 — naver_talktalk_custommenu.py·publish_digest.py.
2차(2026-08-17): 위 2곳 sendMessage 관문 경유로 이동(정적 검사만, TARGETS).
3차(2026-08-17 배255 3차): sendPhoto·sendDocument 도 관문에 편입 — 관문 send()를 kind
(sendMessage/sendPhoto/sendDocument) + photo/document(파일 경로) + full_response 로 확장하고,
아래 8곳 중 실제 발신부 6곳을 관문 경유로 이동했다:
  naver_talktalk_custommenu.py · notify_gm_progress.py · publish_digest.py ·
  publish_register.py · send_review_card.py · wellperion-agents/telegram_notifier.py
4차(2026-08-17 배255 4차): 남아있던 마지막 sendMessage 직접호출 2곳도 관문 경유로 이동 —
  publish_register.py::_telegram_send_message · wellperion-agents/telegram_notifier.py::send.
  telegram_notifier.send() 의 reply_markup(dict)은 gateway 가 urlencode 하므로 json.dumps 로
  선직렬화해 extra 에 얹는다(send_review_card.py 가 이미 쓰던 방식과 동일, 회귀 아님).
남긴 것(의도적, 회귀 아님):
  - precommit_sheet_link_guard.py — 발신부가 아니다. "sendPhoto" 는 이 파일이 *다른* 파일의
    알림 신호를 찾는 정규식 패턴 문자열일 뿐, 이 파일 자신은 텔레그램을 호출하지 않는다.
  - telegram_bot/bot.py — 상시가동 봇. sendPhoto/sendDocument 관련 코드는 python-telegram-bot
    라이브러리의 Bot.send_photo/Message.reply_photo 를 **로깅 목적으로만 래핑**할 뿐, 이 파일이
    직접 sendPhoto HTTP 호출을 구성하지 않는다(라이브러리가 내부에서 처리) — 원본 손대지 않음.
  - send_review_card.py 의 deleteMessage(카드 교체 시 이전 카드 삭제) — "발신"이 아니라 별개
    엔드포인트라 관문(sendMessage/sendPhoto/sendDocument 전용) 대상이 아니다. pace()만 공유.

실행: C:/Python314/python.exe scripts/test_tg_gateway_convergence.py
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEXT_TARGETS = ["naver_talktalk_custommenu.py", "publish_digest.py"]

# sendPhoto/sendDocument 를 실제로 관문으로 옮긴 파일들(정적 검사 대상).
PHOTO_TARGETS = [
    ROOT / "naver_talktalk_custommenu.py",
    ROOT / "notify_gm_progress.py",
    ROOT / "publish_digest.py",
    ROOT / "publish_register.py",
    ROOT / "send_review_card.py",
    ROOT.parent / "wellperion-agents" / "telegram_notifier.py",
]


def _check_text_targets() -> None:
    for name in TEXT_TARGETS:
        src = (ROOT / name).read_text(encoding="utf-8")
        assert "/sendMessage" not in src, (
            f"{name} 에 sendMessage 직접 호출이 남아있다 — tg_outbound_log.send() 관문 경유로 바꿔야 한다"
        )
        assert "tg_outbound_log import" in src, f"{name} 이 발신 관문(tg_outbound_log)을 import 하지 않는다"
    print(f"OK[text] — {', '.join(TEXT_TARGETS)} 모두 sendMessage 직접호출 0건 + 관문 import 확인")


def _check_photo_targets() -> None:
    """sendPhoto/sendDocument 직접 URL 구성이 남아있지 않은지 + 관문 import 확인.

    '/sendPhoto"' 처럼 따옴표로 끝나는 문자열 리터럴만 위반으로 본다 — 주석 속
    "(sendMessage/sendPhoto)" 같은 설명문은 오탐이 아니게 걸러진다.
    """
    import re
    violation_re = re.compile(r'/sendPhoto["\']|/sendDocument["\']')
    for path in PHOTO_TARGETS:
        src = path.read_text(encoding="utf-8")
        m = violation_re.search(src)
        assert m is None, (
            f"{path.name} 에 sendPhoto/sendDocument 직접 URL 구성이 남아있다: {m.group(0)!r} — "
            "tg_outbound_log.send(photo=... / document=...) 관문 경유로 바꿔야 한다"
        )
        assert "tg_outbound_log import" in src, f"{path.name} 이 발신 관문(tg_outbound_log)을 import 하지 않는다"
    print(f"OK[photo] — {len(PHOTO_TARGETS)}개 파일 sendPhoto/sendDocument 직접호출 0건 + 관문 import 확인")


# 4차(2026-08-17) — 마지막 sendMessage 직접호출 2곳(경로가 scripts/ 밖에도 있어 별도 리스트).
SENDMESSAGE_TARGETS = [
    ROOT / "publish_register.py",
    ROOT.parent / "wellperion-agents" / "telegram_notifier.py",
]


def _check_sendmessage_targets() -> None:
    for path in SENDMESSAGE_TARGETS:
        src = path.read_text(encoding="utf-8")
        assert "/sendMessage" not in src, (
            f"{path.name} 에 sendMessage 직접 호출이 남아있다 — tg_outbound_log.send() 관문 경유로 바꿔야 한다"
        )
        assert "tg_outbound_log import" in src, f"{path.name} 이 발신 관문(tg_outbound_log)을 import 하지 않는다"
    print(f"OK[sendmessage] — {len(SENDMESSAGE_TARGETS)}개 파일 sendMessage 직접호출 0건 + 관문 import 확인")


class _FakeResp:
    def __init__(self, status, body_dict):
        self.status = status
        self._body = json.dumps(body_dict).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _check_gateway_text_unchanged(tmp_path: Path) -> None:
    """텍스트 발신 경로 — url·payload 형태가 기존과 완전히 동일해야 한다(회귀 0)."""
    import tg_outbound_log as gw

    captured = {}

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["data"] = req.data
        captured["headers"] = dict(req.headers)
        return _FakeResp(200, {"ok": True, "result": {"message_id": 111}})

    with mock.patch("urllib.request.urlopen", side_effect=_fake_urlopen), \
         mock.patch.object(gw, "pace", lambda *a, **k: None), \
         mock.patch.object(gw, "log_outbound", lambda *a, **k: None):
        ok = gw.send("TOKEN", 123, "hello world", source="test")

    assert ok is True, "텍스트 발신 기존 동작(bool True)이 깨졌다"
    assert captured["url"] == "https://api.telegram.org/botTOKEN/sendMessage", captured["url"]
    assert b"text=hello" in captured["data"], "urlencode 페이로드가 아니다 — multipart 로 샌 것으로 보임"
    assert not any(k.lower() == "content-type" and "multipart" in v.lower()
                   for k, v in captured["headers"].items()), "텍스트 발신인데 multipart 헤더가 붙었다"
    print("OK[gateway] — 텍스트 발신 경로 url/payload 형태 무변경 확인")


def _check_gateway_photo(tmp_path: Path) -> None:
    """sendPhoto — kind 자동전환, multipart 파일 포함, full_response 로 message_id 회수."""
    import tg_outbound_log as gw

    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfakebytes")

    captured = {}

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["data"] = req.data
        captured["headers"] = dict(req.headers)
        return _FakeResp(200, {"ok": True, "result": {"message_id": 999}})

    with mock.patch("urllib.request.urlopen", side_effect=_fake_urlopen), \
         mock.patch.object(gw, "pace", lambda *a, **k: None), \
         mock.patch.object(gw, "log_outbound", lambda *a, **k: None):
        resp = gw.send("TOKEN", 456, "caption text", source="test",
                       photo=str(img), full_response=True)

    assert resp.get("result", {}).get("message_id") == 999, "full_response 로 message_id 를 못 뽑는다"
    assert captured["url"].endswith("/sendPhoto"), f"kind 자동전환 실패: {captured['url']}"
    assert b"fakebytes" in captured["data"], "multipart 본문에 실제 파일 바이트가 없다"
    assert b'name="caption"' in captured["data"], "caption 필드가 안 실렸다(sendPhoto 는 text 가 아니라 caption)"
    ctype = next(v for k, v in captured["headers"].items() if k.lower() == "content-type")
    assert "multipart/form-data" in ctype, f"multipart 헤더가 아니다: {ctype}"
    print("OK[gateway] — sendPhoto multipart + kind 자동전환 + full_response(message_id) 확인")


def _check_gateway_document(tmp_path: Path) -> None:
    """sendDocument — document= 인자로도 동일하게 동작."""
    import tg_outbound_log as gw

    doc = tmp_path / "report.pdf"
    doc.write_bytes(b"%PDF-1.4 fake")

    def _fake_urlopen(req, timeout=None):
        assert req.full_url.endswith("/sendDocument")
        assert b'name="document"' in req.data
        return _FakeResp(200, {"ok": True, "result": {"message_id": 42}})

    with mock.patch("urllib.request.urlopen", side_effect=_fake_urlopen), \
         mock.patch.object(gw, "pace", lambda *a, **k: None), \
         mock.patch.object(gw, "log_outbound", lambda *a, **k: None):
        ok = gw.send("TOKEN", 789, "doc caption", source="test", document=str(doc))

    assert ok is True
    print("OK[gateway] — sendDocument 경로 확인")


def _check_gateway_missing_file_no_network() -> None:
    """파일이 없으면 네트워크를 두드리지 않고 실패로 떨어진다."""
    import tg_outbound_log as gw

    with mock.patch("urllib.request.urlopen") as fake_urlopen, \
         mock.patch.object(gw, "pace", lambda *a, **k: None), \
         mock.patch.object(gw, "log_outbound", lambda *a, **k: None):
        ok = gw.send("TOKEN", 123, "caption", source="test", photo="/no/such/file.png")

    assert ok is False
    fake_urlopen.assert_not_called()
    print("OK[gateway] — 파일 없음 → 네트워크 호출 0회, False 반환 확인")


def _check_send_review_card_message_id(tmp_path: Path) -> None:
    """send_review_card.py 가 관문에 정확한 chat_id·caption·파일을 넘기고,
    응답의 message_id 를 그대로 받아오는지(카드 재발송 시 이전 카드 삭제 기능의 전제조건)."""
    import send_review_card as src_mod

    img = tmp_path / "montage.png"
    img.write_bytes(b"fake-montage-bytes")

    calls = []

    def _fake_gateway_send(token, chat_id, text, **kwargs):
        calls.append({"token": token, "chat_id": chat_id, "text": text, **kwargs})
        return {"ok": True, "result": {"message_id": 555}}

    with mock.patch.object(src_mod, "_tg_gateway_send", side_effect=_fake_gateway_send):
        mid = src_mod._send_photo_card("TOKEN", "카드 캡션", {"inline_keyboard": []}, img, "ITEM-1")

    assert mid == 555, "sendPhoto 카드가 관문 응답의 message_id 를 못 받아온다(카드 교체 기능 회귀)"
    assert len(calls) == 1
    call = calls[0]
    assert call["chat_id"] == src_mod.TELEGRAM_CHAT_ID
    assert call["text"] == "카드 캡션"
    assert call["kind"] == "sendPhoto"
    assert call["photo"] == str(img)
    assert call.get("full_response") is True

    calls.clear()
    with mock.patch.object(src_mod, "_tg_gateway_send", side_effect=_fake_gateway_send):
        mid2 = src_mod._send_text_card("TOKEN", "텍스트 폴백 캡션", {"inline_keyboard": []}, "ITEM-2")
    assert mid2 == 555
    assert calls[0]["kind"] == "sendMessage"
    print("OK[callsite] — send_review_card.py 관문 호출 인자(chat_id/caption/photo/kind) + message_id 확인")


def _check_publish_register_sendmessage() -> None:
    """publish_register.py::_telegram_send_message 가 관문을 정확한 인자로 부르는지(4차)."""
    import publish_register as pr_mod

    calls = []

    def _fake_gateway_send(token, chat_id, text, **kwargs):
        calls.append({"token": token, "chat_id": chat_id, "text": text, **kwargs})
        return True

    with mock.patch.object(pr_mod, "_tg_gateway_send", side_effect=_fake_gateway_send), \
         mock.patch.object(pr_mod, "_load_telegram_token", return_value="FAKE_TOKEN"):
        pr_mod._telegram_send_message("테스트 문구")

    assert len(calls) == 1, "gateway 가 정확히 1회 호출돼야 한다"
    call = calls[0]
    assert call["token"] == "FAKE_TOKEN"
    assert call["chat_id"] == pr_mod.TELEGRAM_CHAT_ID
    assert call["text"] == "테스트 문구"
    assert call["kind"] == "sendMessage"
    assert call["extra"] == {"disable_web_page_preview": "true"}, "disable_web_page_preview 옵션이 유실됐다"
    print("OK[callsite] — publish_register._telegram_send_message 관문 호출 인자 확인")


def _check_telegram_notifier_sendmessage() -> None:
    """telegram_notifier.TelegramNotifier.send() 가 관문을 정확한 인자로 부르고
    reply_markup 을 json.dumps 로 선직렬화해 얹는지 + message_id 왕복 확인(4차)."""
    import sys as _sys
    _wa = str((ROOT.parent / "wellperion-agents").resolve())
    if _wa not in _sys.path:
        _sys.path.insert(0, _wa)
    import telegram_notifier as tn_mod

    notifier = tn_mod.TelegramNotifier()
    notifier.token = "FAKE_TOKEN"
    notifier.chat_id = "12345"

    calls = []

    def _fake_gateway_send(token, chat_id, text, **kwargs):
        calls.append({"token": token, "chat_id": chat_id, "text": text, **kwargs})
        return {"ok": True, "result": {"message_id": 777}}

    with mock.patch.object(tn_mod, "_tg_gateway_send", side_effect=_fake_gateway_send):
        resp = notifier.send("본문", reply_markup={"inline_keyboard": [[{"text": "a", "callback_data": "b"}]]})

    assert resp.get("result", {}).get("message_id") == 777, "full_response 로 message_id 를 못 뽑는다"
    assert len(calls) == 1
    call = calls[0]
    assert call["token"] == "FAKE_TOKEN" and call["chat_id"] == "12345"
    assert call["text"] == "본문"
    assert call["kind"] == "sendMessage"
    assert call.get("full_response") is True
    assert call["extra"]["parse_mode"] == "HTML"
    assert json.loads(call["extra"]["reply_markup"]) == {"inline_keyboard": [[{"text": "a", "callback_data": "b"}]]}, (
        "reply_markup 이 json.dumps 로 선직렬화되지 않았다 — urlencode 되면 텔레그램이 거부한다"
    )
    print("OK[callsite] — telegram_notifier.send() 관문 호출 인자(reply_markup 직렬화) + message_id 확인")


def main() -> int:
    _check_text_targets()
    _check_photo_targets()
    _check_sendmessage_targets()

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        _check_gateway_text_unchanged(tmp_path)
        _check_gateway_photo(tmp_path)
        _check_gateway_document(tmp_path)
        _check_gateway_missing_file_no_network()
        _check_send_review_card_message_id(tmp_path)

    _check_publish_register_sendmessage()
    _check_telegram_notifier_sendmessage()

    print("ALL OK — 텔레그램 발신 관문(sendMessage+sendPhoto+sendDocument) 수렴 검증 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
