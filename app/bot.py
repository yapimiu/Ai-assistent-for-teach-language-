"""Telegram transport: all persisted behavior is delegated to LearningCore."""
import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from app.config import get_settings
from app.db import SessionLocal
from app.llm import OpenRouter
from app.services.core import LearningCore

COMMANDS = {"start": "Настройка", "today": "Задачи", "plan": "План", "lesson": "Урок",
            "practice": "Практика ошибок", "test": "Диагностика", "mistakes": "Ошибки",
            "progress": "Прогресс", "settings": "Настройки", "finish": "Завершить", "hint": "Подсказка"}
KEYBOARD = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Урок", callback_data="cmd:lesson"), InlineKeyboardButton(text="Сегодня", callback_data="cmd:today")],
    [InlineKeyboardButton(text="Диагностика", callback_data="cmd:test"), InlineKeyboardButton(text="Практика", callback_data="cmd:practice")],
    [InlineKeyboardButton(text="План", callback_data="cmd:plan"), InlineKeyboardButton(text="Ошибки", callback_data="cmd:mistakes")],
    [InlineKeyboardButton(text="Прогресс", callback_data="cmd:progress"), InlineKeyboardButton(text="Настройки", callback_data="cmd:settings")],
    [InlineKeyboardButton(text="Подсказка", callback_data="cmd:hint"), InlineKeyboardButton(text="Завершить", callback_data="cmd:finish")],
])


def chunks(text, limit=3900):
    # Telegram limit is measured in UTF-16 code units; leave generous headroom.
    result, part, size = [], "", 0
    for char in text:
        width = 2 if ord(char) > 0xffff else 1
        if size + width > limit:
            result.append(part)
            part, size = "", 0
        part += char
        size += width
    return result + ([part] if part else [])


async def recover_pending(core, bot, user_id=None):
    """Replay committed replies after send failure or process restart.

    Delivery is at least once: a crash after send but before acknowledgement may
    repeat a reply; learning effects remain exactly once through receipts.
    """
    pending = await asyncio.to_thread(core.pending, user_id)
    for receipt_id, owner, response in pending:
        for piece in chunks(response):
            await bot.send_message(owner, piece, reply_markup=KEYBOARD)
        await asyncio.to_thread(core.delivered, owner, receipt_id)


def build_dispatcher(core):
    dp = Dispatcher()
    from weakref import WeakValueDictionary
    locks = WeakValueDictionary()

    async def deliver(bot, user_id, key, content):
        lock = locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            await recover_pending(core, bot, user_id)
            receipt, response, sent = await asyncio.to_thread(core.handle, user_id, key, content)
            if sent:
                return
            for piece in chunks(response):
                await bot.send_message(user_id, piece, reply_markup=KEYBOARD)
            await asyncio.to_thread(core.delivered, user_id, receipt)

    @dp.message(F.text)
    async def message_handler(message: Message, bot: Bot):
        if message.chat.type != "private" or not message.from_user:
            return
        await deliver(bot, message.from_user.id, f"msg:{message.chat.id}:{message.message_id}", message.text)

    @dp.callback_query(F.data.startswith("cmd:"))
    async def callback_handler(callback: CallbackQuery, bot: Bot):
        await callback.answer()
        # The sender is authoritative; callback payload never contains object IDs.
        if not callback.message or callback.message.chat.type != "private":
            return
        command = callback.data.split(":", 1)[1]
        if command in COMMANDS:
            await deliver(bot, callback.from_user.id, f"cb:{callback.id}", "/" + command)

    return dp


async def main():
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to run the bot")
    bot = Bot(settings.telegram_bot_token.get_secret_value())
    core = LearningCore(SessionLocal, OpenRouter(settings))
    await bot.set_my_commands([BotCommand(command=k, description=v) for k,v in COMMANDS.items()])
    try:
        try:
            await recover_pending(core, bot)
        except Exception:
            logging.getLogger(__name__).warning("Pending replies remain queued for next learner interaction")
        await build_dispatcher(core).start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
