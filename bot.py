import asyncio
import json
import random
import re
from datetime import datetime, timedelta
from calendar import monthrange
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import pytz

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
user_states = {}      # waiting_priority, waiting_city
temp_tasks = {}
lock = asyncio.Lock()

# Расширенный словарь популярных городов
CITY_OFFSETS = {
    "москва": 3, "новосибирск": 7, "екатеринбург": 5, "казань": 3,
    "оренбург": 5, "самара": 4, "санкт-петербург": 3, "сочи": 3,
    "владивосток": 10, "иркутск": 8, "красноярск": 7, "омск": 6,
    "волгоград": 3, "ростов": 3, "нижний новгород": 3, "пермь": 5,
    "уфа": 5, "челябинск": 5, "тюмень": 5, "барнаул": 7,
}

# Многоязычные сообщения
MESSAGES = {
    "ru": {
        "start": "Босс, система готова 😎\n\nПросто напиши задачу — я всё пойму сам.",
        "main_menu": "Что делаем, Босс?",
        "tasks_menu": "Так, вот твои задачи.\nХочешь — смотри на сегодня, хочешь — весь список, а можешь чекнуть статистику.",
        "no_tasks_today": "На сегодня задач нет 🎉",
        "no_active_tasks": "Нет активных задач",
        "task_recognized": "Задача распознана!\nВыбери приоритет:",
        "task_added": "✅ Задача добавлена, Босс!",
        "done": "✅ Выполнено!",
        "deleted": "🗑 Задача отправлена в не нужные",
        "settings_menu": "⚙️ Настройки",
        "time_prompt": "Выбери город из списка или напиши свой вручную — я определю твой часовой пояс.",
        "time_updated": "✅ Часовой пояс обновлён! Теперь всё по твоему времени.",
        "language_updated": "✅ Язык изменён.",
        "back": "Вернулись назад",
    },
    "en": {
        "start": "Boss, system is ready 😎\n\nJust write a task — I'll understand it.",
        "main_menu": "What are we doing, Boss?",
        "tasks_menu": "Here are your tasks.",
        "time_updated": "✅ Timezone updated!",
        "language_updated": "✅ Language changed.",
    }
}

# Reply клавиатуры (всегда внизу)
def get_main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Задачи"), KeyboardButton(text="⚙️ Настройки")]
        ],
        resize_keyboard=True
    )

def get_tasks_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Сегодня"), KeyboardButton(text="📋 Список")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="← Назад")]
        ],
        resize_keyboard=True
    )

def get_settings_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏰ Время"), KeyboardButton(text="🌍 Язык")],
            [KeyboardButton(text="← Назад")]
        ],
        resize_keyboard=True
    )

# Inline клавиатуры
def get_cities_inline_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Москва", callback_data="city_moscow")],
        [InlineKeyboardButton(text="Новосибирск", callback_data="city_novosibirsk")],
        [InlineKeyboardButton(text="Екатеринбург", callback_data="city_ekaterinburg")],
        [InlineKeyboardButton(text="Казань", callback_data="city_kazan")],
        [InlineKeyboardButton(text="← Назад", callback_data="back_to_settings")]
    ])

def get_language_inline_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton(text="← Назад", callback_data="back_to_settings")]
    ])


async def load_tasks():
    async with lock:
        try:
            with open(TASKS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return {}

        for uid, val in list(raw.items()):
            if isinstance(val, list):
                raw[uid] = {
                    "tasks": val,
                    "meta": {"monthly_sent": None},
                    "settings": {"timezone": 3, "language": "ru"}
                }
            elif isinstance(val, dict) and "settings" not in val:
                val.setdefault("settings", {"timezone": 3, "language": "ru"})
        return raw


async def save_tasks(data):
    async with lock:
        with open(TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


async def get_user_settings(user_id: str):
    data = await load_tasks()
    return data.get(user_id, {}).get("settings", {"timezone": 3, "language": "ru"})


async def get_user_now(user_id: str):
    settings = await get_user_settings(user_id)
    offset = settings.get("timezone", 3)
    return datetime.utcnow() + timedelta(hours=offset)


async def get_text(user_id: str, key: str):
    settings = await get_user_settings(user_id)
    lang = settings.get("language", "ru")
    return MESSAGES.get(lang, MESSAGES["ru"]).get(key, key)


# Улучшенное определение часового пояса
def get_offset_from_city(city: str) -> int | None:
    city_lower = city.lower().strip()

    # 1. Прямое совпадение
    if city_lower in CITY_OFFSETS:
        return CITY_OFFSETS[city_lower]

    # 2. Поиск через zoneinfo и pytz
    try:
        for tz_name in pytz.all_timezones:
            if city_lower in tz_name.lower().replace("_", " "):
                tz = pytz.timezone(tz_name)
                offset = int(tz.utcoffset(datetime.utcnow()).total_seconds() / 3600)
                return offset
    except:
        pass

    # 3. Попытка через zoneinfo
    try:
        zone = ZoneInfo(city_lower.replace(" ", "_").title())
        offset = int(zone.utcoffset(datetime.utcnow()).total_seconds() / 3600)
        return offset
    except:
        pass

    # 4. Парсинг числового смещения (+5, 5, -3 и т.д.)
    match = re.search(r"([+-]?\d{1,2})", city_lower)
    if match:
        try:
            return int(match.group(1))
        except:
            pass

    return None


# ---------- START ----------
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = str(message.from_user.id)
    data = await load_tasks()
    if user_id not in data:
        data[user_id] = {"tasks": [], "meta": {"monthly_sent": None}, "settings": {"timezone": 3, "language": "ru"}}
        await save_tasks(data)

    text = await get_text(user_id, "start")
    await message.answer(text, reply_markup=get_main_kb())


# ---------- МЕНЮ ----------
@dp.message(F.text == "← Назад")
async def back_handler(message: types.Message):
    if message.text == "← Назад":
        await message.answer(await get_text(str(message.from_user.id), "main_menu"), reply_markup=get_main_kb())


@dp.message(F.text == "📋 Задачи")
async def menu_tasks(message: types.Message):
    await message.answer(await get_text(str(message.from_user.id), "tasks_menu"), reply_markup=get_tasks_kb())


@dp.message(F.text == "⚙️ Настройки")
async def menu_settings(message: types.Message):
    await message.answer(await get_text(str(message.from_user.id), "settings_menu"), reply_markup=get_settings_kb())


# ---------- ВРЕМЯ ----------
@dp.message(F.text == "⏰ Время")
async def settings_time(message: types.Message):
    user_id = str(message.from_user.id)
    user_states[user_id] = "waiting_city"
    await message.answer(await get_text(user_id, "time_prompt"), reply_markup=get_cities_inline_kb())


@dp.callback_query(F.data.startswith("city_"))
async def city_selected(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    city_map = {"city_moscow": 3, "city_novosibirsk": 7, "city_ekaterinburg": 5, "city_kazan": 3}
    offset = city_map.get(call.data, 3)

    data = await load_tasks()
    if user_id not in data:
        data[user_id] = {"tasks": [], "meta": {"monthly_sent": None}, "settings": {}}
    data[user_id]["settings"]["timezone"] = offset
    await save_tasks(data)

    user_states.pop(user_id, None)
    await call.message.edit_text(await get_text(user_id, "time_updated"))
    await call.answer()
    await call.message.answer(await get_text(user_id, "main_menu"), reply_markup=get_main_kb())


# ---------- ЯЗЫК ----------
@dp.message(F.text == "🌍 Язык")
async def settings_language(message: types.Message):
    await message.answer("Выбери язык / Choose language", reply_markup=get_language_inline_kb())


@dp.callback_query(F.data.startswith("lang_"))
async def lang_selected(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    lang = "ru" if call.data == "lang_ru" else "en"

    data = await load_tasks()
    if user_id not in data:
        data[user_id] = {"tasks": [], "meta": {"monthly_sent": None}, "settings": {}}
    data[user_id]["settings"]["language"] = lang
    await save_tasks(data)

    await call.message.edit_text(await get_text(user_id, "language_updated"))
    await call.answer()
    await call.message.answer(await get_text(user_id, "main_menu"), reply_markup=get_main_kb())


@dp.callback_query(F.data == "back_to_settings")
async def back_to_settings(call: types.CallbackQuery):
    await call.message.edit_text(await get_text(str(call.from_user.id), "settings_menu"), reply_markup=get_settings_kb())
    await call.answer()


# ---------- ОБРАБОТКА ТЕКСТА (задачи + ручной ввод города) ----------
@dp.message(F.text)
async def handle_any_text(message: types.Message):
    user_id = str(message.from_user.id)
    text = message.text.strip()

    if user_states.get(user_id) == "waiting_city":
        offset = get_offset_from_city(text)
        if offset is None:
            await message.answer("Не удалось определить часовой пояс.\nПопробуй написать город точнее или укажи смещение, например +5")
            return

        data = await load_tasks()
        if user_id not in data:
            data[user_id] = {"tasks": [], "meta": {"monthly_sent": None}, "settings": {}}
        data[user_id]["settings"]["timezone"] = offset
        await save_tasks(data)

        user_states.pop(user_id, None)
        await message.answer(await get_text(user_id, "time_updated"), reply_markup=get_main_kb())
        return

    # Игнорируем кнопки меню
    if text in ["📋 Задачи", "⚙️ Настройки", "📅 Сегодня", "📋 Список", "📊 Статистика", "⏰ Время", "🌍 Язык", "← Назад"]:
        return

    # Добавление новой задачи
    base_time = await get_user_now(user_id)
    dt, repeat, remind = parse(text, base_time)

    temp_tasks[user_id] = {
        "text": text,
        "datetime": dt.strftime("%Y-%m-%d %H:%M"),
        "repeat": repeat,
        "remind": remind,
        "priority": 0,
        "status": "active",
        "action_date": None,
        "reminded": False,
        "task_id": None
    }
    user_states[user_id] = "waiting_priority"

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔥", callback_data="p_2"),
        InlineKeyboardButton(text="📌", callback_data="p_1"),
        InlineKeyboardButton(text="💡", callback_data="p_0")
    ]])
    await message.answer(await get_text(user_id, "task_recognized"), reply_markup=kb)


# ---------- ПРИОРИТЕТ ----------
@dp.callback_query(F.data.startswith("p_"))
async def priority(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    task = temp_tasks.get(user_id)
    if not task:
        return

    task["priority"] = int(call.data.split("_")[1])
    task["task_id"] = (await get_user_now(user_id)).strftime("%Y%m%d%H%M%S%f")

    data = await load_tasks()
    if user_id not in data:
        data[user_id] = {"tasks": [], "meta": {"monthly_sent": None}, "settings": {"timezone": 3, "language": "ru"}}
    data[user_id]["tasks"].append(task)
    await save_tasks(data)

    user_states.pop(user_id, None)
    temp_tasks.pop(user_id, None)

    await call.message.edit_text(await get_text(user_id, "task_added"))
    await call.answer()


# ---------- DONE ----------
@dp.callback_query(F.data.startswith("done_"))
async def mark_done(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    task_id = call.data.split("_", 1)[1]
    data = await load_tasks()
    tasks = data.get(user_id, {}).get("tasks", [])

    for t in tasks:
        if t.get("task_id") == task_id:
            t["status"] = "done"
            t["action_date"] = (await get_user_now(user_id)).strftime("%Y-%m-%d")
            break

    await save_tasks(data)
    try:
        await call.message.edit_text(call.message.text + " ✅", reply_markup=None)
    except:
        pass
    await call.answer(await get_text(user_id, "done"))


# ---------- DELETE ----------
@dp.callback_query(F.data.startswith("del_"))
async def delete_task(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    task_id = call.data.split("_", 1)[1]
    data = await load_tasks()
    tasks = data.get(user_id, {}).get("tasks", [])

    for t in tasks:
        if t.get("task_id") == task_id:
            t["status"] = "deleted"
            t["action_date"] = (await get_user_now(user_id)).strftime("%Y-%m-%d")
            break

    await save_tasks(data)
    try:
        await call.message.edit_text(await get_text(user_id, "deleted"), reply_markup=None)
    except:
        pass
    await call.answer()


# ---------- TODAY, LIST, STATS (упрощённо) ----------
@dp.message(F.text == "📅 Сегодня")
async def show_today(message: types.Message):
    user_id = str(message.from_user.id)
    data = await load_tasks()
    tasks = data.get(user_id, {}).get("tasks", [])
    today = (await get_user_now(user_id)).date()

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
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅", callback_data=f"done_{t['task_id']}"),
                InlineKeyboardButton(text="🗑", callback_data=f"del_{t['task_id']}")
            ]])
            await message.answer(f"{emoji} {dt.strftime('%d.%m %H:%M')} — {t['text']}", reply_markup=kb)
        except:
            continue
    if not displayed:
        await message.answer(await get_text(user_id, "no_tasks_today"))


@dp.message(F.text == "📋 Список")
async def show_list(message: types.Message):
    user_id = str(message.from_user.id)
    data = await load_tasks()
    tasks = data.get(user_id, {}).get("tasks", [])

    displayed = False
    for t in tasks:
        if t.get("status") != "active":
            continue
        try:
            dt = datetime.strptime(t["datetime"], "%Y-%m-%d %H:%M")
            emoji = ["💡", "📌", "🔥"][t.get("priority", 0)]
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅", callback_data=f"done_{t['task_id']}"),
                InlineKeyboardButton(text="🗑", callback_data=f"del_{t['task_id']}")
            ]])
            await message.answer(f"{emoji} {dt.strftime('%d.%m %H:%M')} — {t['text']}", reply_markup=kb)
            displayed = True
        except:
            continue
    if not displayed:
        await message.answer(await get_text(user_id, "no_active_tasks"))


@dp.message(F.text == "📊 Статистика")
async def show_stats(message: types.Message):
    # Простая заглушка — можно расширить
    await message.answer("Статистика за сегодня (в разработке)")


# ---------- PARSE (NLP) ----------
def parse(text: str, base: datetime):
    text = text.lower()
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
    if dt < base:
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


# ---------- REMINDER LOOP ----------
async def reminder_loop():
    while True:
        await asyncio.sleep(30)
        # Здесь можно добавить напоминания и месячный отчёт (как в предыдущих версиях)


async def main():
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
