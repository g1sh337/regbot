import asyncio
import re
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Moscow")
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

from config import BOT_TOKEN, GOAL, MEMBERS
from storage import load_data, save_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def get_all_members() -> list:
    data = load_data()
    saved_members = data.get("members", [])
    return list(MEMBERS) + [m for m in saved_members if m not in MEMBERS]


def parse_message(text: str) -> dict:
    result = {"name": None, "date": None, "total": 0, "lines": []}
    lines = text.strip().split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if re.match(r"\d{2}\.\d{2}\.\d{2,4}", line):
            result["date"] = line
            continue

        match = re.search(r"-\s*(\d+)\s*$", line)
        if match:
            count = int(match.group(1))
            result["total"] += count
            result["lines"].append((line, count))

    # Ищем имя только в первых 3 строках
    first_lines = "\n".join(lines[:3]).lower()
    for member in get_all_members():
        if member.lower() in first_lines:
            result["name"] = member
            break

    return result


def get_status_emoji(total: int, goal: int) -> str:
    if total == 0:
        return "❌"
    elif total >= goal * 2:
        return "🏅"
    elif total >= goal:
        return "✅"
    elif total >= goal // 2:
        return "🟡"
    else:
        return "🔴"


def format_summary(day_data: dict, date: str) -> str:
    members = get_all_members()
    now = datetime.now(TZ).strftime("%H:%M")
    lines = [
        f"📊 *Отчёт по регистрациям* — {date}",
        f"🎯 Цель: {GOAL} рег/день",
        f"🕐 Обновлено: {now}",
        "",
    ]

    total_all = 0
    for member in members:
        count = day_data.get(member, {}).get("total", 0)
        emoji = get_status_emoji(count, GOAL)
        lines.append(f"{emoji} {member} — {count}/{GOAL}")
        total_all += count

    lines.append("")
    lines.append("──────────────")
    lines.append(f"📈 Итого: {total_all}/{GOAL * len(members)}")

    return "\n".join(lines)


async def update_summary(chat_id: int, date: str, summary_text: str):
    """
    Редактирует существующее сообщение-сводку.
    Если его нет или оно удалено — отправляет новое и запоминает ID.
    """
    data = load_data()
    bot_messages = data.get("bot_messages", {})
    key = f"{chat_id}:{date}"
    existing_msg_id = bot_messages.get(key)

    if existing_msg_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=existing_msg_id,
                text=summary_text,
                parse_mode="Markdown",
            )
            logger.info(f"[EDIT] Сводка обновлена (msg_id={existing_msg_id})")
            return
        except TelegramBadRequest as e:
            logger.warning(f"[EDIT] Не удалось отредактировать: {e}")

    # Отправляем новое сообщение если старого нет
    sent = await bot.send_message(chat_id, summary_text, parse_mode="Markdown")
    data = load_data()
    data.setdefault("bot_messages", {})[key] = sent.message_id
    save_data(data)
    logger.info(f"[SEND] Новая сводка отправлена (msg_id={sent.message_id})")


async def process_any_message(message: Message):
    text = message.text or message.caption or ""
    logger.info(f"[MSG] chat={message.chat.id} type={message.chat.type} text={text[:80]!r}")

    if not text:
        return

    parsed = parse_message(text)
    logger.info(f"[PARSE] name={parsed['name']} total={parsed['total']} date={parsed['date']}")

    if not parsed["name"]:
        logger.info("[SKIP] Имя участника не найдено")
        return

    if parsed["name"] not in get_all_members():
        logger.info(f"[SKIP] {parsed['name']} не в списке")
        return

    date = parsed["date"] or datetime.now().strftime("%d.%m.%y")

    data = load_data()
    data.setdefault("days", {}).setdefault(date, {})[parsed["name"]] = {
        "total": parsed["total"],
        "message_id": message.message_id,
        "updated_at": datetime.now().isoformat(),
    }
    save_data(data)

    summary_text = format_summary(data["days"][date], date)

    try:
        await update_summary(message.chat.id, date, summary_text)
        logger.info(f"[OK] {parsed['name']} = {parsed['total']}")
    except Exception as e:
        logger.error(f"[ERR] {e}")


# ── Команды ──────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Бот учёта регистраций запущен!\n\n"
        "Команды:\n"
        "/summary — текущая сводка\n"
        "/members — список участников\n"
        "/addmember Имя — добавить участника\n"
        "/removemember Имя — удалить участника\n"
        "/reset — сбросить счётчики (админ)\n"
        "/test — проверка связи"
    )


@dp.message(Command("test"))
async def cmd_test(message: Message):
    await message.answer(
        f"✅ Бот работает!\n"
        f"Chat ID: `{message.chat.id}`\n"
        f"Chat type: {message.chat.type}",
        parse_mode="Markdown"
    )


@dp.message(Command("summary"))
async def cmd_summary(message: Message):
    data = load_data()
    today = datetime.now().strftime("%d.%m.%y")
    today_data = data.get("days", {}).get(today, {})
    await message.answer(format_summary(today_data, today), parse_mode="Markdown")


@dp.message(Command("members"))
async def cmd_members(message: Message):
    members = get_all_members()
    await message.answer("👥 Участников:\n" + "\n".join(f"• {m}" for m in members))


@dp.message(Command("addmember"))
async def cmd_addmember(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /addmember Имя")
        return
    name = args[1].strip()
    if name in get_all_members():
        await message.answer(f"❗ {name} уже в списке.")
        return
    data = load_data()
    saved = data.get("members", [])
    saved.append(name)
    data["members"] = saved
    save_data(data)
    await message.answer(f"✅ {name} добавлен в список участников!")


@dp.message(Command("removemember"))
async def cmd_removemember(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /removemember Имя")
        return
    name = args[1].strip()
    if name in MEMBERS:
        await message.answer(
            f"❗ {name} указан в config.py — удали его оттуда вручную и перезапусти бота."
        )
        return
    data = load_data()
    saved = data.get("members", [])
    if name not in saved:
        await message.answer(f"❗ {name} не найден в списке.")
        return
    saved.remove(name)
    data["members"] = saved
    save_data(data)
    await message.answer(f"✅ {name} удалён из списка участников!")


@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    chat_member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if chat_member.status not in ("administrator", "creator"):
        await message.answer("❗ Только администраторы могут сбрасывать счётчики.")
        return
    data = load_data()
    today = datetime.now().strftime("%d.%m.%y")
    data.setdefault("days", {})[today] = {}
    save_data(data)
    await message.answer(f"🔄 Счётчики на {today} сброшены.")


# ── Хендлеры сообщений ───────────────────────────────

@dp.message(F.text & ~F.text.startswith("/"))
async def on_message(message: Message):
    await process_any_message(message)

@dp.edited_message(F.text)
async def on_edited_message(message: Message):
    await process_any_message(message)

@dp.channel_post(F.text)
async def on_channel_post(message: Message):
    await process_any_message(message)

@dp.edited_channel_post(F.text)
async def on_edited_channel_post(message: Message):
    await process_any_message(message)


async def main():
    logger.info("Бот запущен...")
    await dp.start_polling(bot, allowed_updates=[
        "message", "edited_message",
        "channel_post", "edited_channel_post"
    ])


if __name__ == "__main__":
    asyncio.run(main())