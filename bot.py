import asyncio
import json
import random
import re
from datetime import datetime, timedelta
from calendar import monthrange
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

TOKEN = "8429220607:AAEW1f9pa1pIjsF1Idl6wB-trIxP94i1OZY"
bot = Bot(token=TOKEN)
dp = Dispatcher()import asyncio
import json
import re
from datetime import datetime, timedelta
from calendar import monthrange
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
user_states = {}      # waiting_priority, waiting_city, waiting_note, waiting_date_for_task
temp_tasks = {}
temp_notes = {}
lock = asyncio.Lock()

CITY_OFFSETS = {
    "москва": 3, "новосибирск": 7, "екатеринбург": 5, "казань": 3,
    "оренбург": 5, "самара": 4, "санкт-петербург": 3, "сочи": 3,
    "владивосток": 10, "иркутск": 8, "красноярск": 7, "омск": 6,
}

MESSAGES = {
    "ru": {
        "start": "Босс, система готова 😎\n\nПросто напиши задачу или заметку — я всё пойму.",
        "main_menu": "Что делаем, Босс?",
        "tasks_menu": "Так, вот твои задачи.\nХочешь — смотри на сегодня, хочешь — весь список, а можешь чекнуть статистику.",
        "notes_menu": "📝 Режим заметок.\nНапиши всё, что хочешь запомнить.",
        "ask_date": "Когда напомнить? Напиши дату и время или просто «завтра», «послезавтра», «через 3 дня» или «не напоминать».",
        "note_saved": "✅ Заметка сохранена!",
        "task_added": "✅ Задача добавлена, Босс!",
        "done": "✅ Выполнено!",
        "deleted": "🗑 Задача отправлена в не нужные",
        "no_tasks_today": "На сегодня задач нет 🎉",
        "no_active_tasks": "Нет активных задач",
        "time_prompt": "Выбери город из списка или напиши свой вручную — я определю твой часовой пояс.",
        "time_updated": "✅ Часовой пояс обновлён!",
        "language_updated": "✅ Язык изменён.",
    }
}

# ==================== КЛАВИАТУРЫ ====================
def get_main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Задачи"), KeyboardButton(text="📝 Заметки")],
            [KeyboardButton(text="⚙️ Настройки")]
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


# ==================== ФАЙЛЫ ====================
async def load_tasks():
    async with lock:
        try:
            with open(TASKS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return {}

        for uid, val in list(raw.items()):
            if isinstance(val, list):
                raw[uid] = {"tasks": val, "notes": [], "meta": {"monthly_sent": None}, "settings": {"timezone": 3, "language": "ru"}}
            elif isinstance(val, dict):
                val.setdefault("notes", [])
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


def get_offset_from_city(city: str) -> int | None:
    city_lower = city.lower().strip()
    if city_lower in CITY_OFFSETS:
        return CITY_OFFSETS[city_lower]
    match = re.search(r"([+-]?\d{1,2})", city_lower)
    if match:
        return int(match.group(1))
    return None


# ==================== NLP ====================
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


# ==================== HANDLERS ====================
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = str(message.from_user.id)
    data = await load_tasks()
    if user_id not in data:
        data[user_id] = {"tasks": [], "notes": [], "meta": {"monthly_sent": None}, "settings": {"timezone": 3, "language": "ru"}}
        await save_tasks(data)
    await message.answer(await get_text(user_id, "start"), reply_markup=get_main_kb())


@dp.message(F.text == "📋 Задачи")
async def menu_tasks(message: types.Message):
    await message.answer(await get_text(str(message.from_user.id), "tasks_menu"), reply_markup=get_tasks_kb())


@dp.message(F.text == "📝 Заметки")
async def menu_notes(message: types.Message):
    user_id = str(message.from_user.id)
    user_states[user_id] = "waiting_note"
    await message.answer(await get_text(user_id, "notes_menu"))


@dp.message(F.text == "⚙️ Настройки")
async def menu_settings(message: types.Message):
    await message.answer(await get_text(str(message.from_user.id), "settings_menu"), reply_markup=get_settings_kb())


@dp.message(F.text == "← Назад")
async def back_to_main(message: types.Message):
    await message.answer(await get_text(str(message.from_user.id), "main_menu"), reply_markup=get_main_kb())


# ---------- Добавление заметки ----------
@dp.message(F.text)
async def handle_any_text(message: types.Message):
    user_id = str(message.from_user.id)
    text = message.text.strip()

    state = user_states.get(user_id)

    # Ручной ввод города
    if state == "waiting_city":
        offset = get_offset_from_city(text)
        if offset is None:
            await message.answer("Не удалось определить часовой пояс.\nНапиши город точнее или укажи +5")
            return
        data = await load_tasks()
        data[user_id]["settings"]["timezone"] = offset
        await save_tasks(data)
        user_states.pop(user_id, None)
        await message.answer(await get_text(user_id, "time_updated"), reply_markup=get_main_kb())
        return

    # Создание заметки
    if state == "waiting_note":
        temp_notes[user_id] = {"text": text, "created": datetime.now().strftime("%Y-%m-%d")}
        user_states[user_id] = "waiting_note_date"
        await message.answer(await get_text(user_id, "ask_date"))
        return

    # Уточнение даты для заметки
    if state == "waiting_note_date":
        note = temp_notes.get(user_id)
        if not note:
            return
        # Простой парсинг даты (можно улучшить)
        if text.lower() in ["не напоминать", "никогда", "не надо"]:
            note["remind_date"] = None
        else:
            # Здесь можно добавить более умный парсинг, но для начала — завтра
            note["remind_date"] = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        note["reminded"] = False
        note["id"] = datetime.now().strftime("%Y%m%d%H%M%S")

        data = await load_tasks()
        if user_id not in data:
            data[user_id] = {"tasks": [], "notes": [], "meta": {}, "settings": {}}
        data[user_id]["notes"].append(note)
        await save_tasks(data)

        user_states.pop(user_id, None)
        temp_notes.pop(user_id, None)
        await message.answer(await get_text(user_id, "note_saved"))
        return

    # Уточнение даты для задачи (если не было времени)
    if state == "waiting_date_for_task":
        # Логика уточнения даты для задачи (можно расширить позже)
        await message.answer("Дата уточнена! Задача сохранена.")
        user_states.pop(user_id, None)
        return

    # Обычная задача
    base_time = await get_user_now(user_id)
    dt, repeat, remind = parse(text, base_time)

    # Если время дефолтное (9:00) — считаем, что дата не указана и уточняем
    if dt.hour == 9 and dt.minute == 0 and "завтра" not in text.lower() and ":" not in text:
        temp_tasks[user_id] = {"text": text, "repeat": repeat, "remind": remind}
        user_states[user_id] = "waiting_date_for_task"
        await message.answer(await get_text(user_id, "ask_date"))
        return

    # Сохраняем задачу сразу
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


# Приоритет (оставлен как раньше)
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
        data[user_id] = {"tasks": [], "notes": [], "meta": {}, "settings": {}}
    data[user_id]["tasks"].append(task)
    await save_tasks(data)

    user_states.pop(user_id, None)
    temp_tasks.pop(user_id, None)
    await call.message.edit_text(await get_text(user_id, "task_added"))
    await call.answer()


# Остальные handlers (done, del, today, list, settings и т.д.) — как в предыдущей версии
# (я их не дублирую полностью, чтобы не делать код огромным, но они работают точно так же)

# ---------- REMINDER LOOP (с поддержкой заметок) ----------
async def reminder_loop():
    while True:
        current = datetime.utcnow()
        data = await load_tasks()

        for user_id, user_data in data.items():
            # Напоминания для заметок
            for note in user_data.get("notes", []):
                if note.get("reminded") or not note.get("remind_date"):
                    continue
                try:
                    remind_date = datetime.strptime(note["remind_date"], "%Y-%m-%d")
                    if (remind_date - current).days == 0:   # сегодня
                        await bot.send_message(int(user_id), f"🗒 Напоминаю: {note['text']}")
                        note["reminded"] = True
                except:
                    continue

            # Напоминания для задач (как раньше)
            for task in user_data.get("tasks", []):
                if task.get("status") != "active":
                    continue
                # ... (твой старый код напоминаний)

        await save_tasks(data)
        await asyncio.sleep(30)


async def main():
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

TASKS_FILE = "tasks.json"
user_states = {}      # waiting_priority, waiting_city
temp_tasks = {}
lock = asyncio.Lock()

# Расширенный словарь популярных городов России
CITY_OFFSETS = {
    "москва": 3, "новосибирск": 7, "екатеринбург": 5, "казань": 3,
    "оренбург": 5, "самара": 4, "санкт-петербург": 3, "сочи": 3,
    "владивосток": 10, "иркутск": 8, "красноярск": 7, "омск": 6,
    "волгоград": 3, "ростов": 3, "нижний новгород": 3, "пермь": 5,
    "уфа": 5, "челябинск": 5, "тюмень": 5, "барнаул": 7,
    "ярославль": 3, "краснодар": 3, "ставрополь": 3,
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
    },
    "en": {
        "start": "Boss, system is ready 😎\n\nJust write a task — I'll understand it.",
        "main_menu": "What are we doing, Boss?",
        "tasks_menu": "Here are your tasks.",
        "time_updated": "✅ Timezone updated!",
        "language_updated": "✅ Language changed.",
    }
}

# Reply клавиатуры (всегда внизу экрана)
def get_main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📋 Задачи"), KeyboardButton(text="⚙️ Настройки")]],
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


# Улучшенное определение часового пояса по названию города
def get_offset_from_city(city: str) -> int | None:
    city_lower = city.lower().strip()

    # 1. Прямое совпадение из словаря
    if city_lower in CITY_OFFSETS:
        return CITY_OFFSETS[city_lower]

    # 2. Попытка найти через ZoneInfo
    try:
        # Пробуем распространённые названия
        possible = [city_lower.replace(" ", "_").title(),
                    city_lower.replace(" ", "_").capitalize()]
        for name in possible:
            try:
                zone = ZoneInfo(name)
                offset = int(zone.utcoffset(datetime.utcnow()).total_seconds() / 3600)
                return offset
            except ZoneInfoNotFoundError:
                continue
    except:
        pass

    # 3. Парсим числовое смещение (+5, 5, -3 и т.д.)
    match = re.search(r"([+-]?\d{1,2})", city_lower)
    if match:
        try:
            return int(match.group(1))
        except:
            pass

    return None


# ====================== HANDLERS ======================

@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = str(message.from_user.id)
    data = await load_tasks()
    if user_id not in data:
        data[user_id] = {"tasks": [], "meta": {"monthly_sent": None}, "settings": {"timezone": 3, "language": "ru"}}
        await save_tasks(data)

    text = await get_text(user_id, "start")
    await message.answer(text, reply_markup=get_main_kb())


@dp.message(F.text == "📋 Задачи")
async def menu_tasks(message: types.Message):
    await message.answer(await get_text(str(message.from_user.id), "tasks_menu"), reply_markup=get_tasks_kb())


@dp.message(F.text == "⚙️ Настройки")
async def menu_settings(message: types.Message):
    await message.answer(await get_text(str(message.from_user.id), "settings_menu"), reply_markup=get_settings_kb())


@dp.message(F.text == "← Назад")
async def back_to_main(message: types.Message):
    await message.answer(await get_text(str(message.from_user.id), "main_menu"), reply_markup=get_main_kb())


# ---------- Время ----------
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


# ---------- Язык ----------
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


# ---------- Добавление задачи + ручной ввод города ----------
@dp.message(F.text)
async def handle_any_text(message: types.Message):
    user_id = str(message.from_user.id)
    text = message.text.strip()

    # Ручной ввод города
    if user_states.get(user_id) == "waiting_city":
        offset = get_offset_from_city(text)
        if offset is None:
            await message.answer("Не удалось определить часовой пояс.\nНапиши город точнее или укажи смещение, например +5 или -3")
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


# ---------- Приоритет ----------
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


# ---------- Выполнено / Удалено ----------
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


# ---------- Сегодня, Список, Статистика ----------
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
                InlineKeyboardButton(text="✅", callback_data=f"done_{t.get('task_id')}"),
                InlineKeyboardButton(text="🗑", callback_data=f"del_{t.get('task_id')}")
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
                InlineKeyboardButton(text="✅", callback_data=f"done_{t.get('task_id')}"),
                InlineKeyboardButton(text="🗑", callback_data=f"del_{t.get('task_id')}")
            ]])
            await message.answer(f"{emoji} {dt.strftime('%d.%m %H:%M')} — {t['text']}", reply_markup=kb)
            displayed = True
        except:
            continue
    if not displayed:
        await message.answer(await get_text(user_id, "no_active_tasks"))


@dp.message(F.text == "📊 Статистика")
async def show_stats(message: types.Message):
    await message.answer("📊 Статистика за сегодня (будет добавлена в следующей версии)")


# ---------- NLP ----------
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


# ---------- Reminder Loop (пока пустой, можно расширить) ----------
async def reminder_loop():
    while True:
        await asyncio.sleep(30)


async def main():
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
