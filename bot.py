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

TIMEZONE_OFFSET = 3


# 🔘 КНОПКИ
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить")],
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


# 🧠 УМНЫЙ ПАРСИНГ
def parse_date(text):
    now = now_local()

    if "завтра" in text:
        date = now + timedelta(days=1)
    elif "сегодня" in text:
        date = now
    else:
        return None

    import re
    time_match = re.search(r"(\d{1,2}):(\d{2})", text)

    if not time_match:
        return None

    hour = int(time_match.group(1))
    minute = int(time_match.group(2))

    return date.replace(hour=hour, minute=minute, second=0)


# 🚀 START
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Босс, система готова 😎", reply_markup=main_kb)


# ➕ ДОБАВИТЬ
@dp.message(F.text == "➕ Добавить")
@dp.message(Command("add"))
async def add_task(message: types.Message):
    user_states[str(message.from_user.id)] = "waiting"
    await message.answer(
        "Напиши задачу:\n\n"
        "📌 19.04 16:00 Созвон\n"
        "📌 завтра в 18:00 тренировка\n"
        "📌 !! срочно оплатить"
    )


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

        prefix = ""
        if task.get("priority") == 2:
            prefix = "🔥 "
        elif task.get("priority") == 1:
            prefix = "⚡ "

        text = f"{prefix}{dt.strftime('%d.%m %H:%M')} — {task['text']}"

        if task.get("done"):
            text = "✅ " + text

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅", callback_data=f"done_{i}"),
                InlineKeyboardButton(text="🗑", callback_data=f"del_{i}")
            ]
        ])

        await message.answer(text, reply_markup=kb)


# 📊 СТАТИСТИКА
@dp.message(F.text == "📊 Статистика")
async def stats(message: types.Message):
    user_id = str(message.from_user.id)
    tasks = load_tasks()

    if user_id not in tasks:
        await message.answer("Нет данных")
        return

    done = sum(1 for t in tasks[user_id] if t.get("done"))
    total = len(tasks[user_id])

    await message.answer(
        f"📊 Статистика:\n\n"
        f"Всего задач: {total}\n"
        f"Выполнено: {done}\n"
        f"Активных: {total - done}"
    )


# ✍️ ВВОД
@dp.message()
async def handle_text(message: types.Message):
    user_id = str(message.from_user.id)

    if user_states.get(user_id) != "waiting":
        return

    text = message.text

    try:
        priority = 0

        if text.startswith("!!"):
            priority = 2
            text = text[2:].strip()
        elif text.startswith("!"):
            priority = 1
            text = text[1:].strip()

        dt = parse_date(text)

        if not dt:
            parts = text.split(" ", 2)
            date_str, time_str, task_text = parts

            year = now_local().year
            dt = datetime.strptime(
                f"{date_str} {time_str} {year}",
                "%d.%m %H:%M %Y"
            )
        else:
            task_text = text

        tasks = load_tasks()

        if user_id not in tasks:
            tasks[user_id] = []

        tasks[user_id].append({
            "text": task_text,
            "datetime": dt.strftime("%Y-%m-%d %H:%M"),
            "priority": priority,
            "done": False,
            "reminded": False
        })

        save_tasks(tasks)

        user_states.pop(user_id)

        await message.answer("✅ Записал, Босс")

    except:
        await message.answer("❌ Не понял задачу")


# 🔘 INLINE
@dp.callback_query()
async def callbacks(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    tasks = load_tasks()

    if user_id not in tasks:
        return

    action, index = call.data.split("_")
    index = int(index)

    if action == "done":
        tasks[user_id][index]["done"] = True

    elif action == "del":
        tasks[user_id].pop(index)

    save_tasks(tasks)

    await call.message.edit_reply_markup()
    await call.answer("Готово")


# 🔔 НАПОМИНАНИЯ
async def reminder_loop():
    while True:
        now = now_local()
        tasks = load_tasks()

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
    print("Бот запущен...")

    asyncio.create_task(reminder_loop())

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
