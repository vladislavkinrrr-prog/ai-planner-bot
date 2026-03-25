import asyncio
import json
from datetime import datetime, timedelta

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
        "Я слежу за твоими задачами, Босс 😎\n\n"
        "/add - добавить задачу\n"
        "/today - сегодня\n"
        "/all - все задачи"
    )


@dp.message(Command("add"))
async def add_task(message: types.Message):
    user_id = str(message.from_user.id)
    user_states[user_id] = "waiting_task"

    await message.answer("Какую задачу записать, Босс 😎")


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
            "datetime": dt.strftime("%Y-%m-%d %H:%M"),
            "reminded_1h": False,
            "reminded_1d": False
        })

        save_tasks(tasks)

        user_states.pop(user_id, None)

        await message.answer("✅ Записал, Босс")

    except:
        await message.answer("❌ Формат: 19.04 16:00 Созвон")


def sort_tasks(task_list):
    return sorted(
        task_list,
        key=lambda x: datetime.strptime(x["datetime"], "%Y-%m-%d %H:%M")
    )


@dp.message(Command("all"))
async def all_tasks(message: types.Message):
    user_id = str(message.from_user.id)
    tasks = load_tasks()

    if user_id not in tasks:
        await message.answer("Нет задач")
        return

    sorted_tasks = sort_tasks(tasks[user_id])

    result = "📋 Твои задачи:\n\n"

    for task in sorted_tasks:
        dt = datetime.strptime(task["datetime"], "%Y-%m-%d %H:%M")
        formatted = dt.strftime("%d.%m %H:%M")
        result += f"{formatted} — {task['text']}\n"

    await message.answer(result)


# 🔥 ГЛАВНАЯ МАГИЯ — НАПОМИНАНИЯ
async def reminder_loop():
    while True:
        now = datetime.now()
        tasks = load_tasks()

        for user_id, user_tasks in tasks.items():
            for task in user_tasks:
                task_time = datetime.strptime(task["datetime"], "%Y-%m-%d %H:%M")

                # напоминание за 1 час
                if not task.get("reminded_1h"):
                    if 0 <= (task_time - now).total_seconds() <= 60:
                        await bot.send_message(
                            user_id,
                            f"⏰ Через 1 час:\n{task['text']}"
                        )
                        task["reminded_1h"] = True

                # напоминание за день (в 23:00)
                if not task.get("reminded_1d"):
                    day_before = task_time - timedelta(days=1)
                    if (
                        now.date() == day_before.date()
                        and now.hour == 23
                        and now.minute == 0
                    ):
                        await bot.send_message(
                            user_id,
                            f"🌙 Завтра у тебя:\n{task['text']} в {task_time.strftime('%H:%M')}"
                        )
                        task["reminded_1d"] = True

        save_tasks(tasks)

        await asyncio.sleep(60)  # проверка каждую минуту


async def main():
    print("Бот запущен...")

    # запускаем напоминания
    asyncio.create_task(reminder_loop())

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
