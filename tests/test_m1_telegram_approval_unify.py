"""
test_m1_telegram_approval_unify.py — M1 웹 승인 ↔ 텔레그램 승인 통일(CMO 배1170) pytest.
검증 대상: telegram_bot/bot.py cmd_m1_publish (/m1pub 신호 핸들러).

케이스: ①GM 아닌 챗=무시 ②id 없음=사용법 ③status≠승인=보류
       ④게이트 OFF=발행 안 함(_launch_publish_engine 미호출)
       ⑤게이트 ON+승인=_launch_publish_engine 호출.
_launch_publish_engine·_git_pull_locked 는 실제 subprocess/git 이 뜨지 않도록 patch.
"""

import asyncio
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_BOT_DIR = os.path.join(_PROJECT_ROOT, "telegram_bot")
if _BOT_DIR not in sys.path:
    sys.path.insert(0, _BOT_DIR)

import bot  # noqa: E402


def _make_update(chat_id):
    update = MagicMock()
    update.effective_chat = SimpleNamespace(id=chat_id)
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    return update


def _make_ctx(args):
    ctx = MagicMock()
    ctx.args = args
    ctx.bot = MagicMock()
    ctx.bot.send_message = AsyncMock()
    return ctx


def _write_queue(tmp_path, items):
    p = tmp_path / "review_queue.json"
    p.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    return p


def test_non_gm_chat_ignored():
    """① GM 챗이 아니면 아무 동작도 하지 않는다(보안 가드)."""
    update = _make_update(chat_id=999999)
    ctx = _make_ctx(["REV-1"])
    with patch.object(bot, "_git_pull_locked") as mock_pull, \
         patch.object(bot, "_launch_publish_engine", new=AsyncMock()) as mock_launch:
        asyncio.run(bot.cmd_m1_publish(update, ctx))
    mock_pull.assert_not_called()
    mock_launch.assert_not_called()
    update.message.reply_text.assert_not_called()


def test_missing_id_shows_usage():
    """② id 인자 없이 호출하면 사용법만 안내하고 종료."""
    update = _make_update(chat_id=bot._GM_CHAT_ID)
    ctx = _make_ctx([])
    with patch.object(bot, "_git_pull_locked") as mock_pull, \
         patch.object(bot, "_launch_publish_engine", new=AsyncMock()) as mock_launch:
        asyncio.run(bot.cmd_m1_publish(update, ctx))
    mock_pull.assert_not_called()
    mock_launch.assert_not_called()
    update.message.reply_text.assert_awaited_once()
    assert "사용법" in update.message.reply_text.call_args[0][0]


def test_status_not_approved_holds(tmp_path):
    """③ 큐 항목 status가 '승인'이 아니면 발행 보류 안내만 하고 종료."""
    queue_path = _write_queue(tmp_path, [{"id": "REV-1", "status": "대기", "title": "테스트"}])
    update = _make_update(chat_id=bot._GM_CHAT_ID)
    ctx = _make_ctx(["REV-1"])
    with patch.object(bot, "REVIEW_QUEUE", queue_path), \
         patch.object(bot, "_git_pull_locked") as mock_pull, \
         patch.object(bot, "_launch_publish_engine", new=AsyncMock()) as mock_launch:
        asyncio.run(bot.cmd_m1_publish(update, ctx))
    mock_pull.assert_called_once()
    mock_launch.assert_not_called()
    assert "보류" in update.message.reply_text.call_args[0][0]


def test_gate_off_blocks_publish(tmp_path):
    """④ 승인건이어도 게이트(M1_AUTO_PUBLISH) OFF면 발행 엔진을 호출하지 않는다."""
    queue_path = _write_queue(tmp_path, [{"id": "REV-1", "status": "승인", "title": "테스트"}])
    update = _make_update(chat_id=bot._GM_CHAT_ID)
    ctx = _make_ctx(["REV-1"])
    with patch.object(bot, "REVIEW_QUEUE", queue_path), \
         patch.object(bot, "_git_pull_locked") as mock_pull, \
         patch.object(bot, "M1_AUTO_PUBLISH", False), \
         patch.object(bot, "_launch_publish_engine", new=AsyncMock()) as mock_launch:
        asyncio.run(bot.cmd_m1_publish(update, ctx))
    mock_pull.assert_called_once()
    mock_launch.assert_not_called()
    reply = update.message.reply_text.call_args[0][0]
    assert "게이트 OFF" in reply
    assert "M1_AUTO_PUBLISH" in reply


def test_gate_on_and_approved_publishes(tmp_path):
    """⑤ 승인건 + 게이트 ON이면 텔레그램 카드 승인과 동일한 발행 엔진을 호출한다."""
    queue_path = _write_queue(tmp_path, [{"id": "REV-1", "status": "승인", "title": "테스트"}])
    update = _make_update(chat_id=bot._GM_CHAT_ID)
    ctx = _make_ctx(["REV-1"])
    with patch.object(bot, "REVIEW_QUEUE", queue_path), \
         patch.object(bot, "_git_pull_locked") as mock_pull, \
         patch.object(bot, "M1_AUTO_PUBLISH", True), \
         patch.object(bot, "_launch_publish_engine", new=AsyncMock()) as mock_launch:
        asyncio.run(bot.cmd_m1_publish(update, ctx))
    mock_pull.assert_called_once()
    mock_launch.assert_awaited_once_with(["REV-1"], source="m1-web")
    update.message.reply_text.assert_awaited_once()
