import asyncio
import json
import re
from datetime import datetime, timedelta
from calendar import monthrange

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


# ---------- FILE (с миграцией старых данных) ----------
async def load_tasks():
    async with lock:
        try:
            with open(TASKS_FILE, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        except Exception:
            return {}

        # Миграция старой структуры в новую (tasks + meta)
        for uid, val in list(raw_data.items()):
            if isinstance(val, list):
                raw_data[uid] = {
                    "tasks": val,
                    "meta": {"monthly_sent": None}
                }
                # Миграция старых задач
                for t in raw_data[uid]["tasks"]:
                    if "status" not in t:
                        t["status"] = "done" if t.get("done", False) else "active"
                    if "action_date" not in t:
                        t["action_date"] = None
                    if "reminded" not in t:
                        t["reminded"] = False
                    t.pop("done", None)  # чистим старое поле
        return raw_data


async def save_tasks(data):
    async with lock:
        with open(TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# ---------- NLP ----------
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


# ---------- TODAY (только активные задачи на сегодняшний день) ----------
@dp.message(F.text == "📅 Сегодня")
async def show_today(message: types.Message):
    user_id = str(message.from_user.id)
    data = await load_tasks()
    user_data = data.get(user_id, {"tasks": [], "meta": {"monthly_sent": None}})
    tasks = user_data["tasks"]
    today = now().date()

    displayed = False
    for t in tasks:
        if t.get("status") != "active":
            continue
        try:
            dt = datetime.strptime(t["datetime"], "%Y-%m-%d %H:%M")
            if dt.date() != today:
                continue

            displayed = True
            emoji = ["💡", "📌", "🔥"][t.get("priority", 0)]
            task_id = t.get("task_id") or str(tasks.index(t))

            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅", callback_data=f"done_{task_id}"),
                InlineKeyboardButton(text="🗑", callback_data=f"del_{task_id}")
            ]])
            await message.answer(
                f"{emoji} {dt.strftime('%d.%m %H:%M')} — {t['text']}",
                reply_markup=kb
            )
        except:
            continue

    if not displayed:
        await message.answer("На сегодня задач нет 🎉")


# ---------- STATISTICS (только за сегодняшний день + подменю с кнопками) ----------
@dp.message(F.text == "📊 Статистика")
async def statistics(message: types.Message):
    user_id = str(message.from_user.id)
    data = await load_tasks()
    user_data = data.get(user_id, {"tasks": [], "meta": {"monthly_sent": None}})
    tasks = user_data["tasks"]

    today = now().date()
    today_str = today.strftime("%Y-%m-%d")

    active_today = 0
    done_today = 0
    for t in tasks:
        if t.get("status") == "deleted":
            continue
        try:
            dt = datetime.strptime(t["datetime"], "%Y-%m-%d %H:%M").date()
            if dt != today:
                continue
            if t.get("status") == "active":
                active_today += 1
            elif t.get("status") == "done" and t.get("action_date") == today_str:
                done_today += 1
        except:
            continue

    total_today = active_today + done_today
    if total_today == 0:
        await message.answer("На сегодня задач нет 🎉\nДобавь новые с кнопки ➕")
        return

    percent = int((done_today / total_today) * 100)

    if 0 <= percent <= 5:
        msg = "Мы вообще начинать планируем или это философский список задач? Давай, первая галочка самая важная."
    elif 6 <= percent <= 10:
        msg = "Ты не выспался? Эй, бро, давай поднажмём. Вот выполненные задачи:"
    elif 11 <= percent <= 20:
        msg = "Ну всё, лёд тронулся. Уже не ноль — это важно. Продолжаем."
    elif 21 <= percent <= 30:
        msg = "Разогнался. Уже видно, что это не просто список для красоты."
    elif 31 <= percent <= 40:
        msg = "Темп есть. Если не сольёшься сейчас — будет красиво."
    elif 41 <= percent <= 50:
        msg = "Полпути пройдено. Как ни крути — впереди ещё столько же."
    elif 51 <= percent <= 60:
        msg = "Вот это уже рабочее настроение. Осталось меньше, чем сделано."
    elif 61 <= percent <= 70:
        msg = "Ты в зоне. Главное — не расслабляться, финиш уже виден."
    elif 71 <= percent <= 80:
        msg = "Почти дожал. Осталось чуть-чуть, не тормози сейчас."
    elif 81 <= percent <= 90:
        msg = "Бро, я знал. Верил. Не зря же я тебя называю боссом."
    elif 91 <= percent <= 100:
        msg = "Закрыл всё. Чисто. Без шансов для прокрастинации. Уважаю."
    else:
        msg = "Что-то странное с процентами..."

    stats_text = (
        f"📊 На сегодня:\n"
        f"Всего задач: {total_today}\n"
        f"Выполнено: {done_today}\n"
        f"Осталось: {active_today}"
    )

    # Подменю с 3 новыми кнопками
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад", callback_data="back_to_main")],
        [InlineKeyboardButton(text="✅ Выполненные задачи", callback_data="show_done_today")],
        [InlineKeyboardButton(text="🗑 Не нужные задачи", callback_data="show_deleted_today")]
    ])

    await message.answer(f"{msg}\n\n{stats_text}", reply_markup=inline_kb)


# ---------- LIST (только активные задачи) ----------
@dp.message(F.text == "📋 Список")
async def list_tasks(message: types.Message):
    user_id = str(message.from_user.id)
    data = await load_tasks()
    user_data = data.get(user_id, {"tasks": [], "meta": {"monthly_sent": None}})
    tasks = user_data["tasks"]

    displayed = False
    for t in tasks:
        if t.get("status") != "active":
            continue
        try:
            dt = datetime.strptime(t["datetime"], "%Y-%m-%d %H:%M")
            emoji = ["💡", "📌", "🔥"][t.get("priority", 0)]
            task_id = t.get("task_id") or str(tasks.index(t))

            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅", callback_data=f"done_{task_id}"),
                InlineKeyboardButton(text="🗑", callback_data=f"del_{task_id}")
            ]])
            await message.answer(
                f"{emoji} {dt.strftime('%d.%m %H:%M')} — {t['text']}",
                reply_markup=kb
            )
            displayed = True
        except:
            continue

    if not displayed:
        await message.answer("Нет задач")


# ---------- INPUT ----------
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
        "status": "active",
        "action_date": None,
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
    task["task_id"] = now().strftime("%Y%m%d%H%M%S%f")

    data = await load_tasks()
    if user_id not in data:
        data[user_id] = {"tasks": [], "meta": {"monthly_sent": None}}
    data[user_id]["tasks"].append(task)
    await save_tasks(data)

    user_states.pop(user_id, None)
    temp_tasks.pop(user_id, None)

    await call.message.edit_text("✅ Записал, Босс")
    await call.answer()


# ---------- SUB-MENU CALLBACKS ----------
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(call: types.CallbackQuery):
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await call.answer("Вернулись в главное меню")


@dp.callback_query(F.data == "show_done_today")
async def show_done_today(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    data = await load_tasks()
    user_data = data.get(user_id, {"tasks": [], "meta": {"monthly_sent": None}})
    tasks = user_data["tasks"]
    today_str = now().strftime("%Y-%m-%d")

    displayed = False
    for t in tasks:
        if t.get("status") == "done" and t.get("action_date") == today_str:
            await call.message.answer(f"✅ {t['text']}")
            displayed = True
    if not displayed:
        await call.message.answer("Сегодня нет выполненных задач")
    await call.answer()


@dp.callback_query(F.data == "show_deleted_today")
async def show_deleted_today(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    data = await load_tasks()
    user_data = data.get(user_id, {"tasks": [], "meta": {"monthly_sent": None}})
    tasks = user_data["tasks"]
    today_str = now().strftime("%Y-%m-%d")

    displayed = False
    for t in tasks:
        if t.get("status") == "deleted" and t.get("action_date") == today_str:
            await call.message.answer(f"❌ {t['text']}")
            displayed = True
    if not displayed:
        await call.message.answer("Сегодня нет отправленных в не нужные задач")
    await call.answer()


# ---------- DONE ----------
@dp.callback_query(F.data.startswith("done_"))
async def mark_done(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    task_id = call.data.split("_", 1)[1]
    data = await load_tasks()
    user_data = data.get(user_id, {"tasks": [], "meta": {"monthly_sent": None}})
    user_tasks = user_data["tasks"]

    updated = False
    for t in user_tasks:
        if t.get("task_id") == task_id:
            t["status"] = "done"
            t["action_date"] = now().strftime("%Y-%m-%d")
            updated = True
            break
    else:
        # legacy fallback
        if task_id.isdigit():
            try:
                idx = int(task_id)
                if 0 <= idx < len(user_tasks):
                    user_tasks[idx]["status"] = "done"
                    user_tasks[idx]["action_date"] = now().strftime("%Y-%m-%d")
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


# ---------- DELETE (теперь только меняет статус, не удаляет) ----------
@dp.callback_query(F.data.startswith("del_"))
async def delete_task(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    task_id = call.data.split("_", 1)[1]
    data = await load_tasks()
    user_data = data.get(user_id, {"tasks": [], "meta": {"monthly_sent": None}})
    user_tasks = user_data["tasks"]

    updated = False
    for t in user_tasks:
        if t.get("task_id") == task_id:
            t["status"] = "deleted"
            t["action_date"] = now().strftime("%Y-%m-%d")
            updated = True
            break
    else:
        # legacy fallback
        if task_id.isdigit():
            try:
                idx = int(task_id)
                if 0 <= idx < len(user_tasks):
                    user_tasks[idx]["status"] = "deleted"
                    user_tasks[idx]["action_date"] = now().strftime("%Y-%m-%d")
                    updated = True
            except:
                pass

    if updated:
        await save_tasks(data)
        try:
            await call.message.edit_text("🗑 Задача отправлена в не нужные", reply_markup=None)
        except:
            pass
        await call.answer("Отправлено в не нужные")
    else:
        await call.answer("Задача не найдена")


# ---------- REMINDER + АВТОМАТИЧЕСКИЙ МЕСЯЧНЫЙ ОТЧЁТ ----------
async def reminder_loop():
    while True:
        current = now()
        data = await load_tasks()

        # ==================== МЕСЯЧНЫЙ ОТЧЁТ (последний день месяца) ====================
        year = current.year
        month = current.month
        _, last_day = monthrange(year, month)
        if current.day == last_day:
            month_key = f"{year}-{month:02d}"

            # следующий месяц
            next_year = year
            next_m = month + 1
            if next_m > 12:
                next_m = 1
                next_year += 1

            for uid_str, user_data in data.items():
                if not isinstance(user_data, dict) or "meta" not in user_data:
                    continue
                meta = user_data["meta"]
                if meta.get("monthly_sent") == month_key:
                    continue

                tasks = user_data.get("tasks", [])
                month_total = 0
                month_done = 0
                next_total = 0

                for t in tasks:
                    try:
                        dt = datetime.strptime(t["datetime"], "%Y-%m-%d %H:%M")
                        if dt.year == year and dt.month == month:
                            month_total += 1
                            if t.get("status") == "done":
                                month_done += 1
                        elif dt.year == next_year and dt.month == next_m:
                            next_total += 1
                    except:
                        continue

                if month_total == 0:
                    meta["monthly_sent"] = month_key
                    continue

                perc = int((month_done / month_total) * 100) if month_total > 0 else 0

                msg1 = f"бро я в шоке от твоего интузиазма вот сколько задач было {month_total} столько ты выполнил {month_done} это {perc}% прокрастинации тебя не поймать"
                msg2 = f"вперед ещё много задач {next_total}, давай как в этом месяце, только чтоб глаза из орбит не полезли"

                try:
                    await bot.send_message(int(uid_str), msg1)
                    await bot.send_message(int(uid_str), msg2)
                    meta["monthly_sent"] = month_key
                except:
                    pass

        # ==================== НАПОМИНАНИЯ И ПОВТОРЫ ====================
        for user_id, user_data in data.items():
            if not isinstance(user_data, dict):
                continue
            tasks = user_data.get("tasks", [])
            for task in tasks:
                if task.get("status") != "active":
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
                        pass

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
