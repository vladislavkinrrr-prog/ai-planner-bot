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


# ---------- ПАРСИНГ ВРЕМЕНИ ----------
def parse_time_block(text):
    blocks = {
        "утром": (6, 12),
        "днем": (12, 17),
        "день": (12, 17),
        "вечером": (17, 23),
        "ночью": (0, 5),
        "ранний вечер": (17, 20),
        "поздний вечер": (20, 23)
    }

    for key, (start, _) in blocks.items():
        if key in text:
            return start, 0

    match = re.search(r"(\d{1,2}):(\d{2})", text)
    if match:
        return int(match.group(1)), int(match.group(2))

    return 9, 0


def parse_date(text):
    base = now()

    if "завтра" in text:
        base += timedelta(days=1)

    # пятница и т.д.
    weekdays = {
        "понедельник": 0, "вторник": 1, "среду": 2,
        "четверг": 3, "пятницу": 4, "субботу": 5, "воскресенье": 6
    }

    for day, index in weekdays.items():
        if day in text:
            today = base.weekday()
            diff = (index - today) % 7

            if "через неделю" in text:
                diff += 7
            elif "на следующей неделе" in text:
                diff += 7

            base += timedelta(days=diff)

    return base


def parse_repeat(text):
    if "каждый день" in text:
        return "daily"
    if "через день" in text:
        return "2days"
    if "каждый месяц" in text:
        return "monthly"
    return None


def parse_remind(text):
    if "за день" in text:
        return 1440
    if "за 2 часа" in text:
        return 120
    if "за час" in text:
        return 60
    return 60


# ---------- START ----------
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Босс, я на месте 😎", reply_markup=main_kb)


# ---------- ДОБАВИТЬ ----------
@dp.message(F.text == "➕ Добавить")
async def add(message: types.Message):
    user_states[str(message.from_user.id)] = "text"
    await message.answer(
        "Напиши задачу:\n"
        "Пример:\n"
        "завтра в 16:00 встреча\n"
        "в пятницу утром барбер\n"
        "каждый день в 6:00 зарядка"
    )


# ---------- ОБРАБОТКА ВВОДА ----------
@dp.message(F.text)
async def handle(message: types.Message):
    user_id = str(message.from_user.id)

    # 👉 если не режим ввода — игнор
    if user_states.get(user_id) != "text":
        return

    text = message.text.lower()

    date = parse_date(text)
    hour, minute = parse_time_block(text)

    dt = date.replace(hour=hour, minute=minute, second=0)

    repeat = parse_repeat(text)
    remind = parse_remind(text)

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
    data = load_tasks()

    tasks = data.get(user_id, [])

    if not tasks:
        await message.answer("Нет задач")
        return

    tasks = sorted(tasks, key=lambda x: (x["priority"], x["datetime"]))

    for i, t in enumerate(tasks):
        dt = datetime.strptime(t["datetime"], "%Y-%m-%d %H:%M")

        emoji = ["💡", "📌", "🔥"][t["priority"]]

        text = f"{emoji} {dt.strftime('%d.%m %H:%M')} — {t['text']}"

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅", callback_data=f"done_{i}"),
                InlineKeyboardButton(text="🗑", callback_data=f"del_{i}")
            ]
        ])

        await message.answer(text, reply_markup=kb)


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

    text = "📅 Сегодня:\n\n"
    for t in tasks:
        dt = datetime.strptime(t["datetime"], "%Y-%m-%d %H:%M")
        text += f"{dt.strftime('%H:%M')} — {t['text']}\n"

    await message.answer(text)


# ---------- СТАТИСТИКА ----------
@dp.message(F.text == "📊 Статистика")
async def stats(message: types.Message):
    user_id = str(message.from_user.id)
    data = load_tasks()

    tasks = data.get(user_id, [])

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
async def reminders():
    while True:
        now_time = now()
        data = load_tasks()

        for user_id, tasks in data.items():
            for task in tasks:

                if task.get("done"):
                    continue

                task_time = datetime.strptime(task["datetime"], "%Y-%m-%d %H:%M")

                diff = (task_time - now_time).total_seconds() / 60

                if not task.get("reminded") and 0 <= diff <= task["remind"]:
                    await bot.send_message(
                        user_id,
                        f"🔔 Босс, скоро: {task['text']}"
                    )
                    task["reminded"] = True

                # 🔁 повтор
                if task["repeat"] == "daily" and diff < -1:
                    task["datetime"] = (task_time + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
                    task["reminded"] = False

        save_tasks(data)
        await asyncio.sleep(30)


async def main():
    asyncio.create_task(reminders())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
