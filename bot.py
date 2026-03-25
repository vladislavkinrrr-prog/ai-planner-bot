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


# ---------- NLP ----------
def parse(text):
    text = text.lower()
    base = now()

    # дата
    if "завтра" in text:
        base += timedelta(days=1)

    if "через неделю" in text:
        base += timedelta(days=7)

    # время
    match = re.search(r"(\d{1,2}):(\d{2})", text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
    elif "утром" in text:
        hour, minute = 9, 0
    elif "днем" in text:
        hour, minute = 13, 0
    elif "вечером" in text:
        hour, minute = 19, 0
    else:
        hour, minute = 9, 0

    dt = base.replace(hour=hour, minute=minute, second=0)

    # не в прошлое
    if dt < now():
        dt += timedelta(days=1)

    # повтор
    repeat = None
    if "каждый день" in text:
        repeat = "daily"
    elif "через день" in text:
        repeat = "2days"
    elif "каждый месяц" in text:
        repeat = "monthly"

    # напоминание
    remind = 60
    if "за день" in text:
        remind = 1440
    elif "за 2 часа" in text:
        remind = 120

    return dt, repeat, remind


# ---------- START ----------
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Босс, система готова 😎", reply_markup=main_kb)


# ---------- ДОБАВИТЬ ----------
@dp.message(F.text == "➕ Добавить")
async def add(message: types.Message):
    user_states[str(message.from_user.id)] = "waiting"
    await message.answer("Что записать, Босс?")


# ---------- ВВОД ----------
@dp.message(F.text)
async def handle(message: types.Message):
    user_id = str(message.from_user.id)

    if user_states.get(user_id) != "waiting":
        return

    dt, repeat, remind = parse(message.text)

    temp_tasks[user_id] = {
        "text": message.text,
        "datetime": dt.strftime("%Y-%m-%d %H:%M"),
        "repeat": repeat,
        "remind": remind,
        "done": False,
        "reminded": False
    }

    user_states[user_id] = "priority"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔥", callback_data="p_2"),
            InlineKeyboardButton(text="📌", callback_data="p_1"),
            InlineKeyboardButton(text="💡", callback_data="p_0"),
        ]
    ])

    await message.answer("Выбери приоритет:", reply_markup=kb)


# ---------- ПРИОРИТЕТ ----------
@dp.callback_query(F.data.startswith("p_"))
async def priority(call: types.CallbackQuery):
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
async def list_tasks(message: types.Message):
    user_id = str(message.from_user.id)
    tasks = load_tasks().get(user_id, [])

    if not tasks:
        await message.answer("Нет задач")
        return

    for i, t in enumerate(tasks):
        dt = datetime.strptime(t["datetime"], "%Y-%m-%d %H:%M")
        emoji = ["💡", "📌", "🔥"][t["priority"]]

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅", callback_data=f"done_{i}"),
                InlineKeyboardButton(text="🗑", callback_data=f"del_{i}")
            ]
        ])

        await message.answer(f"{emoji} {dt.strftime('%d.%m %H:%M')} — {t['text']}", reply_markup=kb)


# ---------- СЕГОДНЯ ----------
@dp.message(F.text == "📅 Сегодня")
async def today(message: types.Message):
    user_id = str(message.from_user.id)
    tasks = load_tasks().get(user_id, [])

    today_str = now().strftime("%Y-%m-%d")

    result = [t for t in tasks if t["datetime"].startswith(today_str)]

    if not result:
        await message.answer("Нет задач")
        return

    text = "📅 Сегодня:\n\n"
    for t in result:
        dt = datetime.strptime(t["datetime"], "%Y-%m-%d %H:%M")
        text += f"{dt.strftime('%H:%M')} — {t['text']}\n"

    await message.answer(text)


# ---------- СТАТИСТИКА ----------
@dp.message(F.text == "📊 Статистика")
async def stats(message: types.Message):
    user_id = str(message.from_user.id)
    tasks = load_tasks().get(user_id, [])

    done = sum(1 for t in tasks if t.get("done"))

    await message.answer(
        f"📊 Всего: {len(tasks)}\n"
        f"✅ Выполнено: {done}\n"
        f"📌 Активных: {len(tasks)-done}"
    )


# ---------- CALLBACK ----------
@dp.callback_query(F.data.startswith(("done_", "del_")))
async def actions(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    data = load_tasks()

    action, index = call.data.split("_")
    index = int(index)

    if action == "done":
        data[user_id][index]["done"] = True
    else:
        data[user_id].pop(index)

    save_tasks(data)

    await call.message.edit_reply_markup()
    await call.answer("Готово")


# ---------- НАПОМИНАНИЯ ----------
async def reminder_loop():
    while True:
        current = now()
        data = load_tasks()

        for user_id, tasks in data.items():
            for task in tasks:
                if task.get("done"):
                    continue

                task_time = datetime.strptime(task["datetime"], "%Y-%m-%d %H:%M")
                diff = (task_time - current).total_seconds() / 60

                # 🔔 напоминание
                if not task["reminded"] and 0 <= diff <= task["remind"]:
                    await bot.send_message(user_id, f"🔔 Босс, скоро: {task['text']}")
                    task["reminded"] = True

                # 🔁 повтор
                if task["repeat"] == "daily" and diff < -60:
                    task["datetime"] = (task_time + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
                    task["reminded"] = False

                if task["repeat"] == "2days" and diff < -60:
                    task["datetime"] = (task_time + timedelta(days=2)).strftime("%Y-%m-%d %H:%M")
                    task["reminded"] = False

                if task["repeat"] == "monthly" and diff < -60:
                    task["datetime"] = (task_time + timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
                    task["reminded"] = False

        save_tasks(data)
        await asyncio.sleep(30)


async def main():
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
