import asyncio
import json
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "8429220607:AAEW1f9pa1pIjsF1Idl6wB-trIxP94i1OZY"

bot = Bot(token=TOKEN)
dp = Dispatcher()

TASKS_FILE = "tasks.json"
user_states = {}

TIMEZONE_OFFSET = 3


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


# 🚀 START
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Я твой умный планировщик 😎\n\n"
        "/add - добавить\n"
        "/all - список"
    )


# ➕ ДОБАВИТЬ
@dp.message(Command("add"))
async def add_task(message: types.Message):
    user_states[str(message.from_user.id)] = "waiting"
    await message.answer("Напиши задачу:\n19.04 16:00 Созвон")


# 📋 СПИСОК
@dp.message(Command("all"))
async def show_tasks(message: types.Message):
    user_id = str(message.from_user.id)
    tasks = load_tasks()

    if user_id not in tasks or not tasks[user_id]:
        await message.answer("Нет задач")
        return

    tasks_sorted = sorted(tasks[user_id], key=lambda x: x["datetime"])

    for i, task in enumerate(tasks_sorted):
        dt = datetime.strptime(task["datetime"], "%Y-%m-%d %H:%M")

        text = f"{dt.strftime('%d.%m %H:%M')} — {task['text']}"

        if task.get("done"):
            text = "✅ " + text

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅", callback_data=f"done_{i}"),
                InlineKeyboardButton(text="🗑", callback_data=f"del_{i}")
            ]
        ])

        await message.answer(text, reply_markup=kb)


# ✍️ ВВОД
@dp.message()
async def handle_text(message: types.Message):
    user_id = str(message.from_user.id)

    if user_states.get(user_id) != "waiting":
        return

    try:
        parts = message.text.split(" ", 2)
        date_str, time_str, task_text = parts

        year = now_local().year

        dt = datetime.strptime(
            f"{date_str} {time_str} {year}",
            "%d.%m %H:%M %Y"
        )

        tasks = load_tasks()

        if user_id not in tasks:
            tasks[user_id] = []

        tasks[user_id].append({
            "text": task_text,
            "datetime": dt.strftime("%Y-%m-%d %H:%M"),
            "done": False,
            "reminded": False
        })

        save_tasks(tasks)

        user_states.pop(user_id)

        await message.answer("✅ Добавил")

    except:
        await message.answer("❌ Формат: 19.04 16:00 Созвон")


# ✅ / 🗑 CALLBACK
@dp.callback_query()
async def callbacks(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    tasks = load_tasks()

    if user_id not in tasks:
        return

    data = call.data

    if "_" not in data:
        return

    action, index = data.split("_")
    index = int(index)

    if index >= len(tasks[user_id]):
        return

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

                # тест (1 мин)
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
