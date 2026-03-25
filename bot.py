import asyncio
import json
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

TOKEN = "8429220607:AAEW1f9pa1pIjsF1Idl6wB-trIxP94i1OZY"

bot = Bot(token=TOKEN)
dp = Dispatcher()

user_states = {}

TASKS_FILE = "tasks.json"

TIMEZONE_OFFSET = 3  # поменяй при необходимости


# ✅ КНОПКИ
keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить задачу")],
        [KeyboardButton(text="📅 Сегодня"), KeyboardButton(text="📋 Все задачи")],
        [KeyboardButton(text="🧪 Тест (1 минута)")]
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


# 🚀 СТАРТ
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Я твой планировщик, Босс 😎", reply_markup=keyboard)


# ➕ КНОПКА
@dp.message(F.text == "➕ Добавить задачу")
async def add_task_button(message: types.Message):
    user_id = str(message.from_user.id)
    user_states[user_id] = "waiting_task"
    await message.answer("Какую задачу записать, Босс 😎")


# ➕ КОМАНДА (на всякий случай)
@dp.message(Command("add"))
async def add_task_cmd(message: types.Message):
    user_id = str(message.from_user.id)
    user_states[user_id] = "waiting_task"
    await message.answer("Какую задачу записать, Босс 😎")


# 🧪 ТЕСТ
@dp.message(F.text == "🧪 Тест (1 минута)")
async def test_task(message: types.Message):
    user_id = str(message.from_user.id)

    test_time = now_local() + timedelta(minutes=1)

    tasks = load_tasks()

    if user_id not in tasks:
        tasks[user_id] = []

    tasks[user_id].append({
        "text": "ТЕСТОВАЯ ЗАДАЧА",
        "datetime": test_time.strftime("%Y-%m-%d %H:%M"),
        "reminded_test": False,
        "reminded_1h": False
    })

    save_tasks(tasks)

    await message.answer("✅ Тестовая задача добавлена")


# 📅 СЕГОДНЯ (кнопка)
@dp.message(F.text == "📅 Сегодня")
async def today_tasks(message: types.Message):
    await show_today(message)


# 📅 СЕГОДНЯ (команда)
@dp.message(Command("today"))
async def today_cmd(message: types.Message):
    await show_today(message)


async def show_today(message: types.Message):
    user_id = str(message.from_user.id)
    tasks = load_tasks()

    if user_id not in tasks:
        await message.answer("Нет задач")
        return

    today = now_local().strftime("%Y-%m-%d")

    result = "📅 Сегодня:\n\n"
    found = False

    for task in sorted(tasks[user_id], key=lambda x: x["datetime"]):
        if task["datetime"].startswith(today):
            dt = datetime.strptime(task["datetime"], "%Y-%m-%d %H:%M")
            result += f"{dt.strftime('%H:%M')} — {task['text']}\n"
            found = True

    if not found:
        result = "Нет задач на сегодня"

    await message.answer(result)


# 📋 ВСЕ (кнопка)
@dp.message(F.text == "📋 Все задачи")
async def all_tasks(message: types.Message):
    await show_all(message)


# 📋 ВСЕ (команда)
@dp.message(Command("all"))
async def all_cmd(message: types.Message):
    await show_all(message)


async def show_all(message: types.Message):
    user_id = str(message.from_user.id)
    tasks = load_tasks()

    if user_id not in tasks:
        await message.answer("Нет задач")
        return

    result = "📋 Твои задачи:\n\n"

    for task in sorted(tasks[user_id], key=lambda x: x["datetime"]):
        dt = datetime.strptime(task["datetime"], "%Y-%m-%d %H:%M")
        result += f"{dt.strftime('%d.%m %H:%M')} — {task['text']}\n"

    await message.answer(result)


# ✍️ ВВОД ЗАДАЧИ (ВАЖНО — без фильтра !)
@dp.message()
async def handle_text(message: types.Message):
    user_id = str(message.from_user.id)

    if user_states.get(user_id) != "waiting_task":
        return

    try:
        parts = message.text.split(" ", 2)

        if len(parts) < 3:
            raise ValueError()

        date_str, time_str, task_text = parts

        current_year = now_local().year

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
            "reminded_test": False,
            "reminded_1h": False
        })

        save_tasks(tasks)

        user_states.pop(user_id, None)

        await message.answer("✅ Записал, Босс")

    except:
        await message.answer("❌ Формат: 19.04 16:00 Созвон")


# 🔥 НАПОМИНАНИЯ
async def reminder_loop():
    while True:
        now = now_local()
        tasks = load_tasks()

        for user_id, user_tasks in tasks.items():
            for task in user_tasks:
                task_time = datetime.strptime(task["datetime"], "%Y-%m-%d %H:%M")
                diff = (task_time - now).total_seconds()

                # 🧪 тест (1 минута)
                if not task.get("reminded_test"):
                    if 0 <= diff <= 60:
                        await bot.send_message(user_id, f"🔔 {task['text']}")
                        task["reminded_test"] = True

                # ⏰ за 1 час
                if not task.get("reminded_1h"):
                    if 3540 <= diff <= 3600:
                        await bot.send_message(user_id, f"⏰ Через 1 час: {task['text']}")
                        task["reminded_1h"] = True

        save_tasks(tasks)
        await asyncio.sleep(30)


async def main():
    print("Бот запущен...")

    asyncio.create_task(reminder_loop())

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
