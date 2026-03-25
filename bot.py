import asyncio
import json
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command

TOKEN = "8429220607:AAEW1f9pa1pIjsF1Idl6wB-trIxP94i1OZY"

bot = Bot(token=TOKEN)
dp = Dispatcher()

user_states = {}

TASKS_FILE = "tasks.json"


def load_tasks():
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_tasks(tasks):
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Привет 👋\n\n"
        "/add - добавить задачу\n"
        "/today - задачи на сегодня\n"
        "/all - все задачи"
    )


@dp.message(Command("add"))
async def add_task(message: types.Message):
    user_id = str(message.from_user.id)

    # всегда принудительно включаем режим
    user_states[user_id] = "waiting_task"

    await message.answer(
        "Введи задачу:\n\n"
        "19.04 16:00 Созвон"
    )


@dp.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: types.Message):
    user_id = str(message.from_user.id)

    if user_states.get(user_id) != "waiting_task":
        return

    text = message.text

    try:
        parts = text.split(" ", 2)

        if len(parts) < 3:
            raise ValueError()

        date_str = parts[0]
        time_str = parts[1]
        task_text = parts[2]

        # добавляем текущий год
        current_year = datetime.now().year
        dt = datetime.strptime(
            f"{date_str} {time_str} {current_year}",
            "%d.%m %H:%M %Y"
        )

        tasks = load_tasks()

        if user_id not in tasks:
            tasks[user_id] = []

        tasks[user_id].append({
            "text": task_text,
            "datetime": dt.strftime("%Y-%m-%d %H:%M")
        })

        save_tasks(tasks)

        # сброс состояния
        user_states.pop(user_id, None)

        await message.answer("✅ Задача добавлена")

    except:
        await message.answer("❌ Ошибка формата\nПример:\n19.04 16:00 Созвон")


@dp.message(Command("today"))
async def today_tasks(message: types.Message):
    user_id = str(message.from_user.id)
    tasks = load_tasks()

    if user_id not in tasks or not tasks[user_id]:
        await message.answer("Нет задач")
        return

    today = datetime.now().strftime("%Y-%m-%d")

    result = "📅 Сегодня:\n\n"
    found = False

    for task in tasks[user_id]:
        if task["datetime"].startswith(today):
            result += f"{task['datetime'][11:16]} - {task['text']}\n"
            found = True

    if not found:
        result = "Нет задач на сегодня"

    await message.answer(result)


@dp.message(Command("all"))
async def all_tasks(message: types.Message):
    user_id = str(message.from_user.id)
    tasks = load_tasks()

    if user_id not in tasks or not tasks[user_id]:
        await message.answer("Нет задач")
        return

    result = "📋 Все задачи:\n\n"

    for task in tasks[user_id]:
        dt = datetime.strptime(task["datetime"], "%Y-%m-%d %H:%M")
        formatted = dt.strftime("%d.%m %H:%M")

        result += f"{formatted} — {task['text']}\n"

    await message.answer(result)


async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
