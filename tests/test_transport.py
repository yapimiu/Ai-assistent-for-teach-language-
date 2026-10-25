import asyncio
from unittest.mock import AsyncMock
import pytest
from aiogram import Bot
from aiogram.types import Update
from app.bot import chunks, recover_pending, build_dispatcher
from app.services.core import LearningCore


def test_chunks_preserve_unicode_within_telegram_limit():
    text = "🙂" * 5000 + "română"
    pieces = chunks(text)
    assert "".join(pieces) == text
    assert all(len(p.encode("utf-16-le")) // 2 <= 3900 for p in pieces)


def test_failed_send_then_restart_recovers_pending_response(sessions, model):
    core = LearningCore(sessions, model)
    receipt, response, _ = core.handle(10, "initial", "/start")
    bot = AsyncMock()
    bot.send_message.side_effect = RuntimeError("Telegram down")
    with pytest.raises(RuntimeError):
        asyncio.run(recover_pending(core, bot, 10))
    assert core.pending(10)
    restarted = LearningCore(sessions, model)
    bot.send_message.side_effect = None
    asyncio.run(recover_pending(restarted, bot, 10))
    assert not restarted.pending(10)
    assert restarted.handle(10, "initial", "/start")[2]


def test_next_distinct_message_delivers_pending_before_new_response(sessions, model):
    core = LearningCore(sessions, model)
    _, pending_text, _ = core.handle(10, "lost_reply", "/start")
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    bot.send_message = AsyncMock()
    dp = build_dispatcher(LearningCore(sessions, model))
    update = Update.model_validate({"update_id": 2, "message": {"message_id": 5, "date": 1700000000,
        "chat": {"id": 10, "type": "private"}, "from": {"id": 10, "is_bot": False, "first_name": "Learner"},
        "text": "русский"}})
    asyncio.run(dp.feed_update(bot, update))
    assert bot.send_message.call_args_list[0].args[1] == pending_text
    assert "организация" in bot.send_message.call_args_list[1].args[1]
    assert not core.pending(10)


def test_group_messages_do_not_access_personal_data(sessions, model):
    core = LearningCore(sessions, model)
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    bot.send_message = AsyncMock()
    update = Update.model_validate({"update_id": 3, "message": {"message_id": 6, "date": 1700000000,
        "chat": {"id": -123, "type": "group", "title": "group"},
        "from": {"id": 10, "is_bot": False, "first_name": "Learner"}, "text": "/progress"}})
    asyncio.run(build_dispatcher(core).feed_update(bot, update))
    bot.send_message.assert_not_called()
    assert not core.pending()
