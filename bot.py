import asyncio
import json
import random
import re
from datetime import datetime, timedelta
from calendar import monthrange

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "8429220607:AAEW1f9pa1pIjsF1Idl6wB-trIxP94i1OZY"
bot = Bot(token=TOKEN)
dp = Dispatcher()

TASKS_FILE = "tasks.json"
user_states = {}      # для состояний: waiting_priority, waiting_city, waiting_offset
temp_tasks = {}
lock = asyncio.Lock()

# ---------- НАСТРОЙКИ ПО УМОЛЧАНИЮ ----------
CITY_OFFSETS = {
    "москва": 3,
    "новосибирск": 7,
    "екатеринбург": 5,
    "казань": 3,
}

# ---------- МНОГОЯЗЫЧНЫЕ СООБЩЕНИЯ ----------
MESSAGES = {
    "ru": {
        "start": "Босс, система готова 😎\n\nПросто напиши задачу — я всё пойму сам.",
        "main_menu": "Что делаем, Босс?",
        "tasks_menu": "Так, вот твои задачи.\nХочешь — смотри на сегодня, хочешь — весь список, а можешь чекнуть статистику и понять, кто ты сегодня: герой или наблюдатель.\nЕсли что — путь назад всегда есть.",
        "no_tasks_today": "На сегодня задач нет 🎉",
        "no_active_tasks": "Нет активных задач",
        "task_recognized": "Задача распознана!\nВыбери приоритет:",
        "task_added": "✅ Задача добавлена, Босс!",
        "done": "✅ Выполнено!",
        "deleted": "🗑 Задача отправлена в не нужные",
        "settings_menu": "⚙️ Настройки",
        "time_first_1": "Давай настроим время нормально.\nВыбери свой город — так я буду понимать твой часовой пояс и не будить тебя среди ночи 🙂\nМожно выбрать из списка или написать свой город вручную.",
        "time_first_2": "Окей, теперь скажи, где ты обитаешь 🙂\nВыбери город — чтобы я не прислал напоминание в 3 ночи.\nЕсли твоего нет — просто напиши свой город вручную.",
        "time_change_1": "О, смена города 👀\nЧё, переехал или просто решил жить по другому времени? 😏\nВыбирай из списка или напиши свой город вручную.",
        "time_change_2": "Так-так… смена часового пояса?\nКуда в отпуск или уже вернулся? 😎\nВыбирай город ниже или напиши свой вручную.",
        "time_change_3": "Решил сменить город?\nНадеюсь, это апгрейд, а не бегство от задач 😄\nВыбирай из списка или просто напиши свой город вручную.",
        "time_updated": "✅ Часовой пояс обновлён! Теперь всё по твоему времени.",
        "language_updated": "✅ Язык изменён. Все сообщения теперь на новом языке.",
        "back_to_main": "Вернулись в главное меню",
        "monthly_report_1": "бро я в шоке от твоего интузиазма вот сколько задач было {total} столько ты выполнил {done} это {perc}% прокрастинации тебя не поймать",
        "monthly_report_2": "вперед ещё много задач {next_total}, давай как в этом месяце, только чтоб глаза из орбит не полезли",
    },
    "en": {
        "start": "Boss, the system is ready 😎\n\nJust write a task — I'll understand everything myself.",
        "main_menu": "What are we doing, Boss?",
        "tasks_menu": "Okay, here are your tasks.\nWant to see today's? Or the full list? Or check stats and see if you're a hero or just an observer today.\nBack button is always here.",
        "no_tasks_today": "No tasks for today 🎉",
        "no_active_tasks": "No active tasks",
        "task_recognized": "Task recognized!\nChoose priority:",
        "task_added": "✅ Task added, Boss!",
        "done": "✅ Done!",
        "deleted": "🗑 Task moved to unnecessary",
        "settings_menu": "⚙️ Settings",
        "time_first_1": "Let's set the time properly.\nChoose your city — so I understand your timezone and don't wake you up at night 🙂\nYou can choose from the list or type your city manually.",
        "time_first_2": "Okay, now tell me where you live 🙂\nChoose a city — so I don't send reminders at 3 AM.\nIf yours is missing — just type your city manually.",
        "time_change_1": "Oh, changing city 👀\nDid you move or just decided to live on different time? 😏\nChoose from the list or type your city manually.",
        "time_change_2": "Hmm… changing timezone?\nGoing on vacation or already back? 😎\nChoose city below or type manually.",
        "time_change_3": "Decided to change city?\nHope it's an upgrade, not running from tasks 😄\nChoose from the list or just type your city manually.",
        "time_updated": "✅ Timezone updated! Now everything is on your local time.",
        "language_updated": "✅ Language changed. All messages are now in the new language.",
        "back_to_main": "Back to main menu",
        "monthly_report_1": "bro i'm shocked by your enthusiasm, there were {total} tasks, you completed {done}, that's {perc}% — procrastination can't catch you",
        "monthly_report_2": "still a lot of tasks ahead {next_total}, let's do it like this month, but don't pop your eyes out",
    }
}

# ---------- INLINE КЛАВИАТУРЫ ----------
def get_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Задачи", callback_data="menu_tasks")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu_settings")]
    ])

def get_tasks_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Сегодня", callback_data="tasks_today")],
        [InlineKeyboardButton(text="📋 Список", callback_data="tasks_list")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="tasks_stats")],
        [InlineKeyboardButton(text="← Назад", callback_data="back_to_main")]
    ])

def get_settings_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏰ Время", callback_data="settings_time")],
        [InlineKeyboardButton(text="🌍 Язык", callback_data="settings_language")],
        [InlineKeyboardButton(text="← Назад", callback_data="back_to_main")]
    ])

def get_cities_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Москва", callback_data="city_moscow")],
        [InlineKeyboardButton(text="Новосибирск", callback_data="city_novosibirsk")],
        [InlineKeyboardButton(text="Екатеринбург", callback_data="city_ekaterinburg")],
        [InlineKeyboardButton(text="Казань", callback_data="city_kazan")],
        [InlineKeyboardButton(text="← Назад", callback_data="back_to_settings")]
    ])

def get_language_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский язык", callback_data="lang_ru")],
        [InlineKeyboardButton(text="🇬🇧 English language", callback_data="lang_en")],
        [InlineKeyboardButton(text="← Назад", callback_data="back_to_settings")]
    ])


# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------
async def load_tasks():
    async with lock:
        try:
            with open(TASKS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return {}

        # Миграция старых данных
        for uid, val in list(raw.items()):
            if isinstance(val, list):
                raw[uid] = {
                    "tasks": val,
                    "meta": {"monthly_sent": None},
                    "settings": {"timezone": 3, "language": "ru"}
                }
                for t in raw[uid]["tasks"]:
                    if "status" not in t:
                        t["status"] = "done" if t.get("done", False) else "active"
                    if "action_date" not in t:
                        t["action_date"] = None
                    if "reminded" not in t:
                        t["reminded"] = False
                    t.pop("done", None)
            elif isinstance(val, dict) and "settings" not in val:
                val["settings"] = {"timezone": 3, "language": "ru"}
        return raw


async def save_tasks(data):
    async with lock:
        with open(TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


async def get_user_settings(user_id: str):
    data = await load_tasks()
    user_data = data.get(user_id, {})
    settings = user_data.get("settings", {"timezone": 3, "language": "ru"})
    return settings


async def get_user_now(user_id: str):
    settings = await get_user_settings(user_id)
    offset = settings.get("timezone", 3)
    return datetime.utcnow() + timedelta(hours=offset)


async def get_text(user_id: str, key: str):
    settings = await get_user_settings(user_id)
    lang = settings.get("language", "ru")
    return MESSAGES.get(lang, MESSAGES["ru"]).get(key, key)


def parse(text: str, base: datetime = None):
    if base is None:
        base = datetime.utcnow() + timedelta(hours=3)
    text = text.lower()
    if "завтра" in text or "tomorrow" in text:
        base += timedelta(days=1)
    if "через неделю" in text or "next week" in text:
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
    if "каждый день" in text or "daily" in text:
        repeat = "daily"
    elif "через день" in text:
        repeat = "2days"
    elif "каждый месяц" in text or "monthly" in text:
        repeat = "monthly"

    remind = 60
    if "за день" in text or "day before" in text:
        remind = 1440
    elif "за 2 часа" in text or "2 hours" in text:
        remind = 120

    return dt, repeat, remind


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


# ---------- ГЛАВНОЕ МЕНЮ ----------
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    text = await get_text(user_id, "main_menu")
    try:
        await call.message.edit_text(text, reply_markup=get_main_kb())
    except:
        await call.message.answer(text, reply_markup=get_main_kb())
    await call.answer(await get_text(user_id, "back_to_main"))


# ---------- МЕНЮ ЗАДАЧ ----------
@dp.callback_query(F.data == "menu_tasks")
async def menu_tasks(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    text = await get_text(user_id, "tasks_menu")
    try:
        await call.message.edit_text(text, reply_markup=get_tasks_kb())
    except:
        await call.message.answer(text, reply_markup=get_tasks_kb())
    await call.answer()


# ---------- МЕНЮ НАСТРОЕК ----------
@dp.callback_query(F.data == "menu_settings")
async def menu_settings(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    text = await get_text(user_id, "settings_menu")
    try:
        await call.message.edit_text(text, reply_markup=get_settings_kb())
    except:
        await call.message.answer(text, reply_markup=get_settings_kb())
    await call.answer()


# ---------- НАСТРОЙКА ВРЕМЕНИ ----------
@dp.callback_query(F.data == "settings_time")
async def settings_time(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    settings = await get_user_settings(user_id)
    is_first = "timezone" not in settings or settings.get("first_time_timezone", True)

    if is_first:
        msgs = [MESSAGES["ru"]["time_first_1"], MESSAGES["ru"]["time_first_2"]]
        msg = random.choice(msgs)
    else:
        msgs = [
            MESSAGES["ru"]["time_change_1"],
            MESSAGES["ru"]["time_change_2"],
            MESSAGES["ru"]["time_change_3"]
        ]
        msg = random.choice(msgs)

    # Устанавливаем состояние для ручного ввода города
    user_states[user_id] = "waiting_city"

    try:
        await call.message.edit_text(msg, reply_markup=get_cities_kb())
    except:
        await call.message.answer(msg, reply_markup=get_cities_kb())
    await call.answer()


# ---------- ВЫБОР ГОРОДА (КНОПКИ) ----------
@dp.callback_query(F.data.startswith("city_"))
async def city_selected(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    city_map = {
        "city_moscow": 3,
        "city_novosibirsk": 7,
        "city_ekaterinburg": 5,
        "city_kazan": 3,
    }
    offset = city_map.get(call.data, 3)

    data = await load_tasks()
    if user_id not in data:
        data[user_id] = {"tasks": [], "meta": {"monthly_sent": None}, "settings": {}}
    data[user_id]["settings"]["timezone"] = offset
    data[user_id]["settings"]["first_time_timezone"] = False
    await save_tasks(data)

    user_states.pop(user_id, None)
    text = await get_text(user_id, "time_updated")
    await call.message.edit_text(text, reply_markup=get_main_kb())
    await call.answer()


# ---------- НАСТРОЙКА ЯЗЫКА ----------
@dp.callback_query(F.data == "settings_language")
async def settings_language(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    try:
        await call.message.edit_text("Выбери язык / Choose language", reply_markup=get_language_kb())
    except:
        await call.message.answer("Выбери язык / Choose language", reply_markup=get_language_kb())
    await call.answer()


@dp.callback_query(F.data.startswith("lang_"))
async def lang_selected(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    lang = "ru" if call.data == "lang_ru" else "en"

    data = await load_tasks()
    if user_id not in data:
        data[user_id] = {"tasks": [], "meta": {"monthly_sent": None}, "settings": {}}
    data[user_id]["settings"]["language"] = lang
    await save_tasks(data)

    text = await get_text(user_id, "language_updated")
    await call.message.edit_text(text, reply_markup=get_main_kb())
    await call.answer()


# ---------- НАЗАД ИЗ НАСТРОЕК ----------
@dp.callback_query(F.data == "back_to_settings")
async def back_to_settings(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    try:
        await call.message.edit_text(await get_text(user_id, "settings_menu"), reply_markup=get_settings_kb())
    except:
        await call.message.answer(await get_text(user_id, "settings_menu"), reply_markup=get_settings_kb())
    await call.answer()


# ---------- ЗАДАЧИ: СЕГОДНЯ ----------
@dp.callback_query(F.data == "tasks_today")
async def tasks_today(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
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
            await call.message.answer(
                f"{emoji} {dt.strftime('%d.%m %H:%M')} — {t['text']}",
                reply_markup=kb
            )
        except:
            continue

    if not displayed:
        await call.message.answer(await get_text(user_id, "no_tasks_today"))
    await call.answer()


# ---------- ЗАДАЧИ: СПИСОК ----------
@dp.callback_query(F.data == "tasks_list")
async def tasks_list(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
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
            await call.message.answer(
                f"{emoji} {dt.strftime('%d.%m %H:%M')} — {t['text']}",
                reply_markup=kb
            )
            displayed = True
        except:
            continue

    if not displayed:
        await call.message.answer(await get_text(user_id, "no_active_tasks"))
    await call.answer()


# ---------- ЗАДАЧИ: СТАТИСТИКА ----------
@dp.callback_query(F.data == "tasks_stats")
async def tasks_stats(call: types.CallbackQuery):
    # (оставлена прежняя логика статистики за сегодня — можно расширить позже)
    user_id = str(call.from_user.id)
    data = await load_tasks()
    user_data = data.get(user_id, {"tasks": []})
    tasks = user_data["tasks"]

    today = (await get_user_now(user_id)).date()
    today_str = today.strftime("%Y-%m-%d")

    active_today = sum(1 for t in tasks if t.get("status") == "active" and
                       datetime.strptime(t["datetime"], "%Y-%m-%d %H:%M").date() == today)
    done_today = sum(1 for t in tasks if t.get("status") == "done" and t.get("action_date") == today_str)

    total_today = active_today + done_today
    if total_today == 0:
        await call.message.answer(await get_text(user_id, "no_tasks_today"))
        await call.answer()
        return

    percent = int((done_today / total_today) * 100)
    # ... (мотивационные фразы оставлены на русском, как в предыдущих версиях)
    msg = "Мы вообще начинать планируем или это философский список задач? Давай, первая галочка самая важная." if percent <= 5 else \
          "Закрыл всё. Чисто. Без шансов для прокрастинации. Уважаю." if percent >= 91 else "Полпути пройдено. Как ни крути — впереди ещё столько же."

    stats_text = f"📊 На сегодня:\nВсего: {total_today}\nВыполнено: {done_today}\nОсталось: {active_today}"

    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад", callback_data="back_to_main")],
        [InlineKeyboardButton(text="✅ Выполненные задачи", callback_data="show_done_today")],
        [InlineKeyboardButton(text="🗑 Не нужные задачи", callback_data="show_deleted_today")]
    ])

    await call.message.answer(f"{msg}\n\n{stats_text}", reply_markup=inline_kb)
    await call.answer()


# ---------- ДОБАВЛЕНИЕ ЗАДАЧИ (ЛЮБОЙ ТЕКСТ) ----------
@dp.message(F.text)
async def handle_any_text(message: types.Message):
    user_id = str(message.from_user.id)
    text = message.text.strip()

    state = user_states.get(user_id)

    # ---------- РУЧНОЙ ВВОД ГОРОДА ----------
    if state == "waiting_city":
        city = text.lower().strip()
        offset = None
        for known_city, off in CITY_OFFSETS.items():
            if known_city in city:
                offset = off
                break
        if offset is None:
            # Пробуем распарсить offset вручную (+3, 3, -2 и т.д.)
            match = re.search(r"([+-]?\d{1,2})", city)
            if match:
                offset = int(match.group(1))
            else:
                await message.answer("Не нашёл такой город.\nНапиши offset от UTC, например +3 или -5")
                return

        data = await load_tasks()
        if user_id not in data:
            data[user_id] = {"tasks": [], "meta": {"monthly_sent": None}, "settings": {}}
        data[user_id]["settings"]["timezone"] = offset
        data[user_id]["settings"]["first_time_timezone"] = False
        await save_tasks(data)

        user_states.pop(user_id, None)
        await message.answer(await get_text(user_id, "time_updated"), reply_markup=get_main_kb())
        return

    # ---------- ВЫБОР ПРИОРИТЕТА (старое состояние) ----------
    if state == "waiting_priority":
        return  # уже обработано в callback

    # ---------- ДОБАВЛЕНИЕ НОВОЙ ЗАДАЧИ ----------
    if text in ["📅 Сегодня", "📋 Список", "📊 Статистика"]:  # на всякий случай
        return

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


# ---------- DONE / DELETE ----------
@dp.callback_query(F.data.startswith("done_"))
async def mark_done(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    task_id = call.data.split("_", 1)[1]
    data = await load_tasks()
    user_tasks = data.get(user_id, {}).get("tasks", [])

    for t in user_tasks:
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
    user_tasks = data.get(user_id, {}).get("tasks", [])

    for t in user_tasks:
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


# ---------- CALLBACKS ДЛЯ СТАТИСТИКИ (show_done / show_deleted) ----------
@dp.callback_query(F.data == "show_done_today")
async def show_done_today(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    data = await load_tasks()
    today_str = (await get_user_now(user_id)).strftime("%Y-%m-%d")
    for t in data.get(user_id, {}).get("tasks", []):
        if t.get("status") == "done" and t.get("action_date") == today_str:
            await call.message.answer(f"✅ {t['text']}")
    await call.answer()


@dp.callback_query(F.data == "show_deleted_today")
async def show_deleted_today(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    data = await load_tasks()
    today_str = (await get_user_now(user_id)).strftime("%Y-%m-%d")
    for t in data.get(user_id, {}).get("tasks", []):
        if t.get("status") == "deleted" and t.get("action_date") == today_str:
            await call.message.answer(f"❌ {t['text']}")
    await call.answer()


# ---------- REMINDER + МЕСЯЧНЫЙ ОТЧЁТ ----------
async def reminder_loop():
    while True:
        current = datetime.utcnow()  # UTC для расчётов
        data = await load_tasks()

        # Месячный отчёт
        year = current.year
        month = current.month
        _, last_day = monthrange(year, month)
        if current.day == last_day:
            month_key = f"{year}-{month:02d}"
            next_year, next_m = (year, month + 1) if month < 12 else (year + 1, 1)

            for uid, user_data in data.items():
                meta = user_data.get("meta", {})
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

                perc = int((month_done / month_total) * 100) if month_total else 0
                await bot.send_message(int(uid), MESSAGES["ru"]["monthly_report_1"].format(total=month_total, done=month_done, perc=perc))
                await bot.send_message(int(uid), MESSAGES["ru"]["monthly_report_2"].format(next_total=next_total))
                meta["monthly_sent"] = month_key

        # Напоминания
        for user_id, user_data in data.items():
            tasks = user_data.get("tasks", [])
            user_now = await get_user_now(user_id)
            for task in tasks:
                if task.get("status") != "active":
                    continue
                try:
                    task_time = datetime.strptime(task["datetime"], "%Y-%m-%d %H:%M")
                except:
                    continue

                diff = (task_time - user_now).total_seconds() / 60

                if not task.get("reminded", False) and 0 <= diff <= task.get("remind", 60):
                    try:
                        await bot.send_message(int(user_id), f"🔔 {task['text']}")
                        task["reminded"] = True
                    except:
                        pass

                # Повторы
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
