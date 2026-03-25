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

lock = asyncio.Lock()

# ---------- UI ----------
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить"), KeyboardButton(text="📅 Сегодня")],
        [KeyboardButton(text="📋 Список"), KeyboardButton(text="📊 Статистика")]
    ],
    resize_keyboard=True
)


def now():
    return datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET)


# ---------- FILE (с защитой от race conditions) ----------
async def load_tasks():
    async with lock:
        try:
            with open(TASKS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}


async def save_tasks(data):
    async with lock:
        with open(TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# ---------- NLP (исправлен парсинг времени) ----------
def parse(text):
    text = text.lower()
    base = now()
    if "завтра" in text:
        base += timedelta(days=1)
    if "через неделю" in text:
        base += timedelta(days=7)

    hour, minute = 9, 0
    match = re.search(r"(\d{1,2}):(\d{2})", text)
    if match:
        h = int(match.group(1))
        m = int(match.group(2))
        if 0 <= h < 24 and 0 <= m < 60:
            hour, minute = h, m

    dt = base.replace(hour=hour, minute=minute, second=0)
    if dt < now():
        dt += timedelta(days=1)

    repeat = None
    if "каждый день" in text:
        repeat = "daily"
    elif "через день" in text:
        repeat = "2days"
    elif "каждый месяц" in text:
        repeat = "monthly"

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


# ---------- ADD ----------
@dp.message(F.text == "➕ Добавить")
async def add(message: types.Message):
    user_states[str(message.from_user.id)] = "waiting"
    await message.answer("Что записать, Босс?")


# ---------- TODAY & STATISTICS (добавлены, чтобы кнопки работали) ----------
@dp.message(F.text == "📅 Сегодня")
async def show_today(message: types.Message):
    await message.answer("📅 Сегодня: используй «📋 Список» для просмотра задач")


@dp.message(F.text == "📊 Статистика")
async def statistics(message: types.Message):
    await message.answer("📊 Статистика: в разработке")


# ---------- LIST ----------
@dp.message(F.text == "📋 Список")
async def list_tasks(message: types.Message):
    user_id = str(message.from_user.id)
    data = await load_tasks()
    tasks = data.get(user_id, [])
    if not tasks:
        await message.answer("Нет задач")
        return

    for i, t in enumerate(tasks):
        dt = datetime.strptime(t["datetime"], "%Y-%m-%d %H:%M")
        emoji = ["💡", "📌", "🔥"][t.get("priority", 0)]
        task_id = t.get("task_id") or str(i)

        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅", callback_data=f"done_{task_id}"),
            InlineKeyboardButton(text="🗑", callback_data=f"del_{task_id}")
        ]])
        await message.answer(
            f"{emoji} {dt.strftime('%d.%m %H:%M')} — {t['text']}",
            reply_markup=kb
        )


# ---------- INPUT (теперь после всех кнопок) ----------
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
        "priority": 0,
        "done": False,
        "reminded": False
    }
    user_states[user_id] = "priority"

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔥", callback_data="p_2"),
        InlineKeyboardButton(text="📌", callback_data="p_1"),
        InlineKeyboardButton(text="💡", callback_data="p_0")
    ]])
    await message.answer("Выбери приоритет:", reply_markup=kb)


# ---------- PRIORITY ----------
@dp.callback_query(F.data.startswith("p_"))
async def priority(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    task = temp_tasks.get(user_id)
    if not task:
        return

    task["priority"] = int(call.data.split("_")[1])
    task["task_id"] = now().strftime("%Y%m%d%H%M%S%f")   # уникальный ID

    data = await load_tasks()
    data.setdefault(user_id, []).append(task)
    await save_tasks(data)

    user_states.pop(user_id, None)
    temp_tasks.pop(user_id, None)

    await call.message.edit_text("✅ Записал, Босс")
    await call.answer()


# ---------- DONE ----------
@dp.callback_query(F.data.startswith("done_"))
async def mark_done(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    task_id = call.data.split("_", 1)[1]
    data = await load_tasks()
    user_tasks = data.get(user_id, [])

    updated = False
    for t in user_tasks:
        if t.get("task_id") == task_id:
            t["done"] = True
            updated = True
            break
    else:
        # legacy fallback (для старых задач без task_id)
        if task_id.isdigit():
            try:
                idx = int(task_id)
                if 0 <= idx < len(user_tasks):
                    user_tasks[idx]["done"] = True
                    updated = True
            except:
                pass

    if updated:
        await save_tasks(data)
        try:
            await call.message.edit_text(call.message.text + " ✅", reply_markup=None)
        except:
            pass
        await call.answer("✅ Выполнено!")
    else:
        await call.answer("Задача не найдена")


# ---------- DELETE ----------
@dp.callback_query(F.data.startswith("del_"))
async def delete_task(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    task_id = call.data.split("_", 1)[1]
    data = await load_tasks()
    user_tasks = data.get(user_id, [])

    updated = False
    if any(t.get("task_id") == task_id for t in user_tasks):
        data[user_id] = [t for t in user_tasks if t.get("task_id") != task_id]
        updated = True
    else:
        # legacy fallback
        if task_id.isdigit():
            try:
                idx = int(task_id)
                if 0 <= idx < len(user_tasks):
                    del user_tasks[idx]
                    updated = True
            except:
                pass

    if updated:
        await save_tasks(data)
        try:
            await call.message.edit_text("🗑 Задача удалена", reply_markup=None)
        except:
            pass
        await call.answer("Удалено")
    else:
        await call.answer("Задача не найдена")


# ---------- REMINDER (исправлено всё) ----------
async def reminder_loop():
    while True:
        current = now()
        data = await load_tasks()

        for user_id, tasks in data.items():
            for task in tasks:
                if task.get("done", False):
                    continue
                try:
                    task_time = datetime.strptime(task["datetime"], "%Y-%m-%d %H:%M")
                except:
                    continue

                diff = (task_time - current).total_seconds() / 60

                # напоминание
                if not task.get("reminded", False) and 0 <= diff <= task.get("remind", 60):
                    try:
                        await bot.send_message(int(user_id), f"🔔 {task['text']}")
                        task["reminded"] = True
                    except:
                        pass  # пользователь мог заблокировать бота

                # повтор
                if task.get("repeat") == "daily" and diff < -60:
                    task["datetime"] = (task_time + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
                    task["reminded"] = False
                elif task.get("repeat") == "2days" and diff < -60:
                    task["datetime"] = (task_time + timedelta(days=2)).strftime("%Y-%m-%d %H:%M")
                    task["reminded"] = False
                elif task.get("repeat") == "monthly" and diff < -60:
                    task["datetime"] = (task_time + timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
                    task["reminded"] = False

        await save_tasks(data)
        await asyncio.sleep(30)


async def main():
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
