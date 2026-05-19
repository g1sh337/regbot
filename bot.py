import asyncio
import re
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, Update, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

from config import BOT_TOKEN, GOAL, MEMBERS
from storage import load_data, save_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TZ = ZoneInfo("Europe/Moscow")

WEBHOOK_HOST = "https://regbot-production.up.railway.app"
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = 8080

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def get_all_members() -> list:
    data = load_data()
    saved_members = data.get("members", [])
    return list(MEMBERS) + [m for m in saved_members if m not in MEMBERS]


def parse_link_key(line: str) -> str | None:
    """
    Из строки вида 'мобилка казино(2) россия 🇷🇺 - 11'
    возвращает ключ вида 'Россия 🇷🇺 (2)'
    Если номера нет — 'Россия 🇷🇺 (1)'
    """
    line = line.strip()
    # Убираем число в конце
    line = re.sub(r'\s*-\s*\d+\s*$', '', line)

    # Извлекаем номер ссылки (N) из названия продукта
    num_match = re.search(r'казино\((\d+)\)', line, re.IGNORECASE)
    num = int(num_match.group(1)) if num_match else 1

    # Убираем "мобилка казино(N)" или "мобилка казино"
    line = re.sub(r'мобилка\s+казино(\(\d+\))?\s*', '', line, flags=re.IGNORECASE)
    line = line.strip()

    if not line:
        return None

    # Первая буква заглавная
    line = line[0].upper() + line[1:]
    return f"{line} ({num})"


def parse_message(text: str) -> dict:
    result = {"name": None, "date": None, "total": 0, "lines": [], "links": {}}
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

            key = parse_link_key(line)
            if key:
                result["links"][key] = result["links"].get(key, 0) + count

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


def get_links_summary(day_data: dict) -> dict:
    """Суммирует регистрации по ссылкам за день по всем участникам."""
    link_totals = {}
    for member, info in day_data.items():
        if not isinstance(info, dict):
            continue
        links = info.get("links", {})
        for key, count in links.items():
            link_totals[key] = link_totals.get(key, 0) + count
    return link_totals


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

    # Ссылки
    link_totals = get_links_summary(day_data)
    if link_totals:
        lines.append("")
        lines.append("🌍 *По странам:*")
        # Сортируем: сначала по названию страны, потом по номеру
        def sort_key(item):
            k = item[0]
            # Извлекаем номер из конца "(N)"
            m = re.search(r'\((\d+)\)$', k)
            num = int(m.group(1)) if m else 1
            name = re.sub(r'\s*\(\d+\)$', '', k)
            return (name, num)

        sorted_links = sorted(link_totals.items(), key=sort_key)
        for key, count in sorted_links:
            lines.append(f"  {key} — {count}")

    return "\n".join(lines)


def make_member_keyboard() -> InlineKeyboardMarkup:
    members = get_all_members()
    buttons = []
    row = []
    for i, member in enumerate(members):
        row.append(InlineKeyboardButton(
            text=f"🔍 {member}",
            callback_data=f"detail:{member}"
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def format_member_detail(name: str, date: str, day_data: dict) -> str:
    member_data = day_data.get(name, {})
    links = member_data.get("links", {})
    total = member_data.get("total", 0)

    lines = [f"📋 *{name}* — {date}", f"Итого: {total}/{GOAL}", ""]

    if links:
        def sort_key(item):
            k = item[0]
            m = re.search(r'\((\d+)\)$', k)
            num = int(m.group(1)) if m else 1
            name_part = re.sub(r'\s*\(\d+\)$', '', k)
            return (name_part, num)

        sorted_links = sorted(links.items(), key=sort_key)
        for key, count in sorted_links:
            emoji = "✅" if count > 0 else "➖"
            lines.append(f"{emoji} {key} — {count}")
    else:
        lines.append("Нет данных по ссылкам")

    return "\n".join(lines)


def format_stats(name: str) -> str:
    data = load_data()
    days = data.get("days", {})

    history = []
    for date, day_data in days.items():
        if name in day_data:
            total = day_data[name].get("total", 0)
            history.append((date, total))

    if not history:
        return f"❗ Нет данных по участнику *{name}*"

    def parse_date(d):
        try:
            return datetime.strptime(d, "%d.%m.%y")
        except:
            try:
                return datetime.strptime(d, "%d.%m.%Y")
            except:
                return datetime.min

    history.sort(key=lambda x: parse_date(x[0]), reverse=True)

    totals = [t for _, t in history]
    days_count = len(history)
    days_goal = sum(1 for t in totals if t >= GOAL)
    avg = round(sum(totals) / days_count)
    best = max(history, key=lambda x: x[1])
    worst = min(history, key=lambda x: x[1])

    lines = [
        f"📈 *Статистика — {name}*",
        "",
        f"📅 Дней в базе: {days_count}",
        f"✅ Выполнил цель: {days_goal} дн.",
        f"📊 Среднее в день: {avg}",
        f"🏆 Лучший день: {best[1]} ({best[0]})",
        f"📉 Худший день: {worst[1]} ({worst[0]})",
        "",
        "──────────────",
        f"*Последние {min(10, days_count)} дней:*",
    ]

    for date, total in history[:10]:
        emoji = get_status_emoji(total, GOAL)
        lines.append(f"{emoji} {date} — {total}")

    return "\n".join(lines)


def format_top() -> str:
    data = load_data()
    days = data.get("days", {})
    members = get_all_members()

    totals = {}
    days_count = {}
    for date, day_data in days.items():
        for member in members:
            if member in day_data:
                totals[member] = totals.get(member, 0) + day_data[member].get("total", 0)
                days_count[member] = days_count.get(member, 0) + 1

    if not totals:
        return "❗ Нет данных для рейтинга"

    ranked = sorted(members, key=lambda m: totals.get(m, 0), reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 *Рейтинг за всё время*", ""]

    for i, member in enumerate(ranked):
        total = totals.get(member, 0)
        days_n = days_count.get(member, 0)
        avg = round(total / days_n) if days_n else 0
        medal = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"{medal} {member} — {total} рег. ({days_n} дн., ср. {avg}/день)")

    return "\n".join(lines)


async def update_summary(chat_id: int, summary_text: str):
    data = load_data()
    key = f"summary:{chat_id}"
    existing_msg_id = data.get("bot_messages", {}).get(key)
    keyboard = make_member_keyboard()

    if existing_msg_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=existing_msg_id,
                text=summary_text,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
            logger.info(f"[EDIT] Сводка обновлена (msg_id={existing_msg_id})")
            return
        except TelegramBadRequest as e:
            logger.warning(f"[EDIT] Не удалось отредактировать: {e}")

    sent = await bot.send_message(chat_id, summary_text, parse_mode="Markdown", reply_markup=keyboard)
    data = load_data()
    data.setdefault("bot_messages", {})[key] = sent.message_id
    save_data(data)
    logger.info(f"[SEND] Новая сводка отправлена (msg_id={sent.message_id})")


async def process_any_message(message: Message):
    text = message.text or message.caption or ""
    if not text:
        return

    parsed = parse_message(text)
    logger.info(f"[PARSE] name={parsed['name']} total={parsed['total']} date={parsed['date']}")

    if not parsed["name"]:
        return
    if parsed["name"] not in get_all_members():
        return

    date = parsed["date"] or datetime.now(TZ).strftime("%d.%m.%y")

    data = load_data()
    data.setdefault("days", {}).setdefault(date, {})[parsed["name"]] = {
        "total": parsed["total"],
        "message_id": message.message_id,
        "updated_at": datetime.now(TZ).isoformat(),
        "links": parsed["links"],
    }
    save_data(data)

    summary_text = format_summary(data["days"][date], date)

    try:
        await update_summary(message.chat.id, summary_text)
        logger.info(f"[OK] {parsed['name']} = {parsed['total']}")
    except Exception as e:
        logger.error(f"[ERR] {e}")


# ── Callback кнопок ───────────────────────────────────

@dp.callback_query(F.data.startswith("detail:"))
async def on_detail_callback(callback: CallbackQuery):
    name = callback.data.split(":", 1)[1]
    data = load_data()
    today = datetime.now(TZ).strftime("%d.%m.%y")

    days = data.get("days", {})
    date = today
    if today not in days or name not in days.get(today, {}):
        for d in sorted(days.keys(), reverse=True):
            if name in days[d]:
                date = d
                break

    day_data = days.get(date, {})
    detail_text = format_member_detail(name, date, day_data)

    try:
        await bot.send_message(callback.from_user.id, detail_text, parse_mode="Markdown")
        await callback.answer()
    except TelegramBadRequest:
        total = day_data.get(name, {}).get("total", 0)
        await callback.answer(
            f"{name}: {total}/{GOAL} рег. Напиши боту /start чтобы видеть детали.",
            show_alert=True
        )


# ── Команды ──────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Бот учёта регистраций запущен!\n\n"
        "Команды:\n"
        "/summary — текущая сводка\n"
        "/stats Имя — статистика участника\n"
        "/top — рейтинг всех участников\n"
        "/members — список участников\n"
        "/addmember Имя — добавить участника\n"
        "/removemember Имя — удалить участника\n"
        "/reset — сбросить счётчики (админ)\n"
        "/resetmsg — сбросить ID сводки\n"
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
    today = datetime.now(TZ).strftime("%d.%m.%y")
    today_data = data.get("days", {}).get(today, {})
    await message.answer(format_summary(today_data, today), parse_mode="Markdown")


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        members = get_all_members()
        await message.answer(
            "Использование: /stats Имя\n\n"
            "Участники:\n" + "\n".join(f"• {m}" for m in members)
        )
        return
    name = args[1].strip()
    members = get_all_members()
    matched = next((m for m in members if m.lower() == name.lower()), None)
    if not matched:
        await message.answer(f"❗ Участник *{name}* не найден.", parse_mode="Markdown")
        return
    await message.answer(format_stats(matched), parse_mode="Markdown")


@dp.message(Command("top"))
async def cmd_top(message: Message):
    await message.answer(format_top(), parse_mode="Markdown")


@dp.message(Command("members"))
async def cmd_members(message: Message):
    members = get_all_members()
    await message.answer("👥 Участники:\n" + "\n".join(f"• {m}" for m in members))


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
    today = datetime.now(TZ).strftime("%d.%m.%y")
    data.setdefault("days", {})[today] = {}
    save_data(data)
    await message.answer(f"🔄 Счётчики на {today} сброшены.")


@dp.message(Command("resetmsg"))
async def cmd_resetmsg(message: Message):
    data = load_data()
    data["bot_messages"] = {}
    save_data(data)
    await message.answer("✅ ID сводок сброшены.")


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


# ── Webhook ───────────────────────────────────────────

async def handle_webhook(request: web.Request) -> web.Response:
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return web.Response(text="OK")


async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook установлен: {WEBHOOK_URL}")


async def on_shutdown():
    await bot.delete_webhook()
    logger.info("Webhook удалён")


async def main():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.on_startup.append(lambda _: on_startup())
    app.on_shutdown.append(lambda _: on_shutdown())

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Бот запущен на порту {PORT}")

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())