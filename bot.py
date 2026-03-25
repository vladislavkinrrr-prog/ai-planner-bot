import asyncio
import json
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

TOKEN = "8429220607:AAEW1f9pa1pIjsF1Idl6wB-trIxP94i1OZY"

bot = Bot(token=TOKEN)
dp = Dispatcher()

TASKS_FILE = "tasks.json"

user_states = {}
temp_tasks = {}

TIMEZONE_OFFSET = 3


# ---------- КНОПКИ ----------
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить"), KeyboardButton(text="📅 Сегодня")],
        [KeyboardButton(text="📋 Список"), KeyboardButton(text="📊 Статистика")]
    ],
    resize_keyboard=True
)


def now():
    return datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET)


# ---------- ФАЙЛ ----------
def load_tasks():
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_tasks(data):
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------- ПАРСИНГ ----------
def parse_time(text):
    match = re.search(r"(\d{1,2}):(\d{2})", text)
    if match:
        return int(match.group(1)), int(match.group(2))

    if "утром" in text:
        return 9, 0
    if "днем" in text or "обед" in text:
        return 13, 0
    if "вечером" in text:
        return 19, 0
    if "ночью" in text:
        return 1, 0

    return 9, 0


def parse_date(text):
    base = now()

    if "завтра" in text:
        base += timedelta(days=1)

    return base


# ---------- START ----------
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Босс, я на месте 😎", reply_markup=main_kb)


# ---------- ДОБАВИТЬ ----------
@dp.message(F.text == "➕ Добавить")
@dp.message(Command("add"))
async def add(message: types.Message):
    user_states[str(message.from_user.id)] = "waiting_text"

    await message.answer("Что записать, Босс?")


# ---------- ВВОД ЗАДАЧИ ----------
@dp.message(F.text)
async def handle_text(message: types.Message):
    user_id = str(message.from_user.id)

    # ❗ ВАЖНО: если НЕ режим ввода — пропускаем
    if user_states.get(user_id) != "waiting_text":
        return

    text = message.text.lower()

    try:
        date = parse_date(text)
        hour, minute = parse_time(text)

        dt = date.replace(hour=hour, minute=minute, second=0)

        temp_tasks[user_id] = {
            "text": message.text,
            "datetime": dt.strftime("%Y-%m-%d %H:%M"),
            "done": False
        }

        user_states[user_id] = "waiting_priority"

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔥", callback_data="p_2"),
                InlineKeyboardButton(text="📌", callback_data="p_1"),
                InlineKeyboardButton(text="💡", callback_data="p_0")
            ]
        ])

        await message.answer("Выбери приоритет:", reply_markup=kb)

    except:
        await message.answer("❌ Ошибка ввода")


# ---------- ПРИОРИТЕТ ----------
@dp.callback_query(F.data.startswith("p_"))
async def set_priority(call: types.CallbackQuery):
    user_id = str(call.from_user.id)

    task = temp_tasks.get(user_id)
    if not task:
        return

    task["priority"] = int(call.data.split("_")[1])

    data = load_tasks()
    data.setdefault(user_id, []).append(task)

    save_tasks(data)

    user_states.pop(user_id, None)
    temp_tasks.pop(user_id, None)

    await call.message.edit_text("✅ Записал, Босс")
    await call.answer()


# ---------- СПИСОК ----------
@dp.message(F.text == "📋 Список")
async def show_list(message: types.Message):
    user_id = str(message.from_user.id)
    data = load_tasks()

    tasks = data.get(user_id, [])

    if not tasks:
        await message.answer("Нет задач")
        return

    for i, t in enumerate(tasks):
        await message.answer(f"{t['datetime']} — {t['text']}")


# ---------- СЕГОДНЯ ----------
@dp.message(F.text == "📅 Сегодня")
async def today(message: types.Message):
    user_id = str(message.from_user.id)
    data = load_tasks()

    today_str = now().strftime("%Y-%m-%d")

    tasks = [
        t for t in data.get(user_id, [])
        if t["datetime"].startswith(today_str)
    ]

    if not tasks:
        await message.answer("Нет задач")
        return

    for t in tasks:
        await message.answer(f"{t['datetime']} — {t['text']}")


# ---------- СТАТИСТИКА ----------
@dp.message(F.text == "📊 Статистика")
async def stats(message: types.Message):
    user_id = str(message.from_user.id)
    data = load_tasks()

    tasks = data.get(user_id, [])

    done = sum(1 for t in tasks if t.get("done"))

    await message.answer(
        f"📊 Всего: {len(tasks)}\n"
        f"✅ Выполнено: {done}"
    )


# ---------- MAIN ----------
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
