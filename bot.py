import asyncio
import json
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

TOKEN = "8429220607:AAEW1f9pa1pIjsF1Idl6wB-trIxP94i1OZY"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# файл для хранения задач
TASKS_FILE = "tasks.json"


# загрузка задач
def load_tasks():
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


# сохранение задач
def save_tasks(tasks):
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


# старт
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Привет 👋\n\n"
        "Я твой планировщик.\n\n"
        "Команды:\n"
        "/add - добавить задачу\n"
        "/today - задачи на сегодня\n"
        "/all - все задачи"
    )


# добавление задачи
@dp.message(Command("add"))
async def add_task(message: types.Message):
    await message.answer(
        "Напиши задачу в формате:\n\n"
        "19.04 16:00 Созвон с подрядчиком"
    )


@dp.message()
async def handle_text(message: types.Message):
    text = message.text
    user_id = str(message.from_user.id)

    try:
        parts = text.split(" ", 2)
        date_str = parts[0]
        time_str = parts[1]
        task_text = parts[2]

        dt = datetime.strptime(date_str + " " + time_str, "%d.%m %H:%M")

        tasks = load_tasks()

        if user_id not in tasks:
            tasks[user_id] = []

        tasks[user_id].append({
            "text": task_text,
            "datetime": dt.strftime("%Y-%m-%d %H:%M")
        })

        save_tasks(tasks)

        await message.answer("✅ Задача добавлена")

    except:
        await message.answer("❌ Неверный формат. Попробуй ещё раз.")


# задачи на сегодня
@dp.message(Command("today"))
async def today_tasks(message: types.Message):
    user_id = str(message.from_user.id)
    tasks = load_tasks()

    if user_id not in tasks:
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


# все задачи
@dp.message(Command("all"))
async def all_tasks(message: types.Message):
    user_id = str(message.from_user.id)
    tasks = load_tasks()

    if user_id not in tasks:
        await message.answer("Нет задач")
        return

    result = "📋 Все задачи:\n\n"

    for task in tasks[user_id]:
        result += f"{task['datetime']} - {task['text']}\n"

    await message.answer(result)


async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
