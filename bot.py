import asyncio
import json
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

TOKEN = "8429220607:AAEW1f9pa1pIjsF1Idl6wB-trIxP94i1OZY"

bot = Bot(token=TOKEN)
dp = Dispatcher()

TASKS_FILE = "tasks.json"
user_states = {}
temp_tasks = {}

TIMEZONE_OFFSET = 3


# 🔘 КНОПКИ
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить"), KeyboardButton(text="📅 Сегодня")],
        [KeyboardButton(text="📋 Список"), KeyboardButton(text="📊 Статистика")]
    ],
    resize_keyboard=True
)


def now_local():
    return datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET)


def load_tasks():
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_tasks(tasks):
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


# 🧠 УМНЫЙ ПАРСЕР
def parse_task(text):
    now = now_local()

    date = now
    time_start = "09:00"
    time_end = None

    if "завтра" in text:
        date = now + timedelta(days=1)
    elif "сегодня" in text:
        date = now

    import re

    # диапазон времени
    range_match = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", text)
    if range_match:
        time_start = range_match.group(1)
        time_end = range_match.group(2)

    else:
        # одиночное время
        time_match = re.search(r"(\d{1,2}:\d{2})", text)
        if time_match:
            time_start = time_match.group(1)

    dt = datetime.strptime(
        f"{date.strftime('%Y-%m-%d')} {time_start}",
        "%Y-%m-%d %H:%M"
    )

    return dt, time_end


# 🚀 START
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Босс, система готова 😎", reply_markup=main_kb)


# ➕ ДОБАВИТЬ
@dp.message(F.text == "➕ Добавить")
@dp.message(Command("add"))
async def add_task(message: types.Message):
    user_states[str(message.from_user.id)] = "waiting_text"

    await message.answer(
        "Напиши задачу:\n\n"
        "📌 19.04 16:00 Созвон\n"
        "📌 завтра позвонить маме\n"
        "📌 завтра 16:00 - 17:00 барбер"
    )


# ✍️ ВВОД
@dp.message()
async def handle_text(message: types.Message):
    user_id = str(message.from_user.id)

    if user_states.get(user_id) != "waiting_text":
        return

    text = message.text

    try:
        dt, time_end = parse_task(text)

        temp_tasks[user_id] = {
            "text": text,
            "datetime": dt.strftime("%Y-%m-%d %H:%M"),
            "time_end": time_end
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
        await message.answer("❌ Не понял задачу")


# 🔥 ПРИОРИТЕТ
@dp.callback_query(F.data.startswith("p_"))
async def set_priority(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    priority = int(call.data.split("_")[1])

    task = temp_tasks.get(user_id)

    if not task:
        return

    tasks = load_tasks()

    if user_id not in tasks:
        tasks[user_id] = []

    task["priority"] = priority
    task["done"] = False
    task["reminded"] = False

    tasks[user_id].append(task)

    save_tasks(tasks)

    user_states.pop(user_id)
    temp_tasks.pop(user_id)

    await call.message.edit_text("✅ Записал, Босс")
    await call.answer()


# 📋 СПИСОК
@dp.message(F.text == "📋 Список")
@dp.message(Command("all"))
async def show_tasks(message: types.Message):
    user_id = str(message.from_user.id)
    tasks = load_tasks()

    if user_id not in tasks or not tasks[user_id]:
        await message.answer("Нет задач")
        return

    tasks_sorted = sorted(
        tasks[user_id],
        key=lambda x: (x.get("priority", 0), x["datetime"])
    )

    for i, task in enumerate(tasks_sorted):
        dt = datetime.strptime(task["datetime"], "%Y-%m-%d %H:%M")

        emoji = "💡"
        if task["priority"] == 2:
            emoji = "🔥"
        elif task["priority"] == 1:
            emoji = "📌"

        text = f"{emoji} {dt.strftime('%d.%m %H:%M')} — {task['text']}"

        if task.get("done"):
            text = "✅ " + text

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅", callback_data=f"done_{i}"),
                InlineKeyboardButton(text="🗑", callback_data=f"del_{i}")
            ]
        ])

        await message.answer(text, reply_markup=kb)


# 📅 СЕГОДНЯ
@dp.message(F.text == "📅 Сегодня")
async def today_tasks(message: types.Message):
    user_id = str(message.from_user.id)
    tasks = load_tasks()

    today = now_local().strftime("%Y-%m-%d")

    result = "📅 Сегодня:\n\n"
    found = False

    for task in tasks.get(user_id, []):
        if task["datetime"].startswith(today):
            dt = datetime.strptime(task["datetime"], "%Y-%m-%d %H:%M")
            result += f"{dt.strftime('%H:%M')} — {task['text']}\n"
            found = True

    if not found:
        result = "Нет задач"

    await message.answer(result)


# 📊 СТАТИСТИКА
@dp.message(F.text == "📊 Статистика")
async def stats(message: types.Message):
    user_id = str(message.from_user.id)
    tasks = load_tasks()

    done = sum(1 for t in tasks.get(user_id, []) if t.get("done"))
    total = len(tasks.get(user_id, []))

    await message.answer(
        f"📊 Статистика:\n\n"
        f"Всего: {total}\n"
        f"Выполнено: {done}\n"
        f"Активных: {total - done}"
    )


# 🔘 CALLBACK
@dp.callback_query(F.data.startswith("done_") | F.data.startswith("del_"))
async def actions(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    tasks = load_tasks()

    action, index = call.data.split("_")
    index = int(index)

    if action == "done":
        tasks[user_id][index]["done"] = True
    elif action == "del":
        tasks[user_id].pop(index)

    save_tasks(tasks)

    await call.message.edit_reply_markup()
    await call.answer("Готово")


# 🔔 НАПОМИНАНИЯ + СБРОС СТАТЫ
async def reminder_loop():
    last_reset_day = None

    while True:
        now = now_local()
        tasks = load_tasks()

        # 🔄 сброс статистики в 01:00
        if now.hour == 1:
            if last_reset_day != now.date():
                for user_id in tasks:
                    for task in tasks[user_id]:
                        task["done"] = False
                save_tasks(tasks)
                last_reset_day = now.date()

        # 🔔 напоминания
        for user_id, user_tasks in tasks.items():
            for task in user_tasks:
                if task.get("done"):
                    continue

                task_time = datetime.strptime(task["datetime"], "%Y-%m-%d %H:%M")
                diff = (task_time - now).total_seconds()

                if not task.get("reminded"):
                    if 0 <= diff <= 60:
                        await bot.send_message(user_id, f"🔔 {task['text']}")
                        task["reminded"] = True

        save_tasks(tasks)
        await asyncio.sleep(30)


async def main():
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
