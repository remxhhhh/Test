import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
import sqlite3
import math

# Конфигурация
TOKEN = "8623083352:AAHPhZkAFymFxs272OO_YYECCeXQUXfH8is"
ADMIN_ID = 2010296191

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота
storage = MemoryStorage()
bot = Bot(token=TOKEN)
dp = Dispatcher(bot, storage=storage)

# Состояния для FSM
class AddTagStates(StatesGroup):
    waiting_for_tag = State()
    waiting_for_deadline = State()

class AdminAddProfit(StatesGroup):
    waiting_for_tag = State()
    waiting_for_usd = State()
    waiting_for_rub = State()

class MarkUnsubscribed(StatesGroup):
    waiting_for_selection = State()

# Инициализация БД
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        is_admin BOOLEAN DEFAULT 0
    )
    ''')
    
    # Таблица тегов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tag TEXT UNIQUE,
        user_id INTEGER,
        deadline TEXT,
        is_active BOOLEAN DEFAULT 1,
        created_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    # Таблица платежей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tag_id INTEGER,
        amount_usd REAL,
        amount_rub REAL,
        profit REAL,
        payment_date TEXT,
        FOREIGN KEY (tag_id) REFERENCES tags (id)
    )
    ''')
    
    # Таблица отписавшихся
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS unsubscribed (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tag_id INTEGER,
        unsubscribed_date TEXT,
        FOREIGN KEY (tag_id) REFERENCES tags (id)
    )
    ''')
    
    # Добавляем админа если его нет
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, is_admin) VALUES (?, ?, ?)", 
                  (ADMIN_ID, "admin", 1))
    
    conn.commit()
    conn.close()

# Вспомогательные функции
def get_user(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def add_user(user_id, username, full_name):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)", 
                  (user_id, username, full_name))
    conn.commit()
    conn.close()

def add_tag(user_id, tag, deadline):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tags (user_id, tag, deadline, created_at) VALUES (?, ?, ?, ?)", 
                  (user_id, tag, deadline, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_tag_by_name(tag_name):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tags WHERE tag = ? AND is_active = 1", (tag_name,))
    tag = cursor.fetchone()
    conn.close()
    return tag

def get_user_tags(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tags WHERE user_id = ? AND is_active = 1 ORDER BY created_at DESC", (user_id,))
    tags = cursor.fetchall()
    conn.close()
    return tags

def get_user_active_tags(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT t.* FROM tags t 
    WHERE t.user_id = ? AND t.is_active = 1 
    AND t.id NOT IN (SELECT tag_id FROM unsubscribed)
    ORDER BY t.created_at DESC
    ''', (user_id,))
    tags = cursor.fetchall()
    conn.close()
    return tags

def get_user_unsubscribed_tags(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT t.*, u.unsubscribed_date 
    FROM tags t 
    JOIN unsubscribed u ON t.id = u.tag_id 
    WHERE t.user_id = ?
    ORDER BY u.unsubscribed_date DESC
    ''', (user_id,))
    tags = cursor.fetchall()
    conn.close()
    return tags

def get_all_user_tags(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT t.*, 
           CASE WHEN u.tag_id IS NOT NULL THEN 1 ELSE 0 END as is_unsubscribed
    FROM tags t 
    LEFT JOIN unsubscribed u ON t.id = u.tag_id 
    WHERE t.user_id = ? AND t.is_active = 1
    ORDER BY t.created_at DESC
    ''', (user_id,))
    tags = cursor.fetchall()
    conn.close()
    return tags

def add_payment(tag_id, amount_usd, amount_rub, profit):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO payments (tag_id, amount_usd, amount_rub, profit, payment_date) VALUES (?, ?, ?, ?, ?)", 
                  (tag_id, amount_usd, amount_rub, profit, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def add_unsubscribed(tag_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO unsubscribed (tag_id, unsubscribed_date) VALUES (?, ?)", 
                  (tag_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_unsubscribed_tags():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT t.id, t.tag, u.username, u.user_id 
    FROM tags t 
    JOIN users u ON t.user_id = u.user_id 
    WHERE t.is_active = 1 
    AND t.id NOT IN (SELECT tag_id FROM unsubscribed)
    ORDER BY t.created_at DESC
    ''')
    tags = cursor.fetchall()
    conn.close()
    return tags

def calculate_profit(amount_rub):
    if amount_rub <= 1000:
        return amount_rub * 0.8
    elif amount_rub <= 5000:
        return amount_rub * 0.7
    elif amount_rub <= 10000:
        return amount_rub * 0.6
    else:
        return amount_rub * 0.5

def get_user_stats(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Получаем теги пользователя
    cursor.execute("SELECT id FROM tags WHERE user_id = ? AND is_active = 1", (user_id,))
    tags = cursor.fetchall()
    tag_ids = [tag[0] for tag in tags]
    
    stats = {
        'total_payments': 0,
        'total_profit': 0,
        'clients_count': len(tags),
        'unsubscribed_count': 0,
        'refund_amount': 0
    }
    
    if tag_ids:
        # Сумма платежей
        placeholders = ','.join('?' * len(tag_ids))
        cursor.execute(f"SELECT SUM(amount_rub) FROM payments WHERE tag_id IN ({placeholders})", tag_ids)
        result = cursor.fetchone()[0]
        stats['total_payments'] = result if result else 0
        
        # Сумма профита
        cursor.execute(f"SELECT SUM(profit) FROM payments WHERE tag_id IN ({placeholders})", tag_ids)
        result = cursor.fetchone()[0]
        stats['total_profit'] = result if result else 0
        
        # Количество отписавшихся
        cursor.execute(f"SELECT COUNT(*) FROM unsubscribed WHERE tag_id IN ({placeholders})", tag_ids)
        stats['unsubscribed_count'] = cursor.fetchone()[0]
        
        # Сумма за отписавшихся (0.5$ за каждого)
        stats['refund_amount'] = stats['unsubscribed_count'] * 0.5
    
    conn.close()
    return stats

def get_team_stats():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    stats = {
        'active_workers': 0,
        'total_payments': 0,
        'total_profit': 0,
        'total_clients': 0,
        'total_unsubscribed': 0
    }
    
    # Активные работники (пользователи с активными тегами)
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM tags WHERE is_active = 1")
    stats['active_workers'] = cursor.fetchone()[0]
    
    # Общая сумма оплат
    cursor.execute("SELECT SUM(amount_rub) FROM payments")
    result = cursor.fetchone()[0]
    stats['total_payments'] = result if result else 0
    
    # Общая сумма профитов
    cursor.execute("SELECT SUM(profit) FROM payments")
    result = cursor.fetchone()[0]
    stats['total_profit'] = result if result else 0
    
    # Общее количество клиентов
    cursor.execute("SELECT COUNT(*) FROM tags WHERE is_active = 1")
    stats['total_clients'] = cursor.fetchone()[0]
    
    # Общее количество отписавшихся
    cursor.execute("SELECT COUNT(*) FROM unsubscribed")
    stats['total_unsubscribed'] = cursor.fetchone()[0]
    
    conn.close()
    return stats

# Клавиатуры
def get_main_keyboard(user_id):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    user = get_user(user_id)
    is_admin = user[3] if user else 0
    
    buttons = [KeyboardButton("➕ Добавить тег")]
    
    if is_admin:
        buttons.append(KeyboardButton("💰 Добавить профит"))
        buttons.append(KeyboardButton("📝 Пометить отписавших"))
        buttons.append(KeyboardButton("📊 Статистика команды"))
    
    buttons.append(KeyboardButton("👥 Клиенты"))
    buttons.append(KeyboardButton("📈 Личная статистика"))
    
    keyboard.row(*buttons)
    return keyboard

# Пагинация
def paginate_items(items, page, per_page=20):
    total_pages = math.ceil(len(items) / per_page)
    if page < 1:
        page = 1
    if page > total_pages and total_pages > 0:
        page = total_pages
    
    start = (page - 1) * per_page
    end = start + per_page
    page_items = items[start:end]
    
    return page_items, page, total_pages

def get_pagination_keyboard(current_page, total_pages, callback_prefix):
    keyboard = InlineKeyboardMarkup(row_width=3)
    buttons = []
    
    if current_page > 1:
        buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"{callback_prefix}_page_{current_page-1}"))
    
    buttons.append(InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="current"))
    
    if current_page < total_pages:
        buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"{callback_prefix}_page_{current_page+1}"))
    
    if buttons:
        keyboard.row(*buttons)
    
    keyboard.row(InlineKeyboardButton("❌ Закрыть", callback_data="close"))
    return keyboard

# Обработчики команд
@dp.message_handler(commands=["start"])
async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "unknown"
    full_name = message.from_user.full_name
    
    add_user(user_id, username, full_name)
    
    await message.answer(
        "👋 Добро пожаловать в бот!\n\n"
        "Выберите действие:",
        reply_markup=get_main_keyboard(user_id)
    )

@dp.message_handler(lambda message: message.text == "➕ Добавить тег")
async def add_tag_start(message: types.Message):
    await AddTagStates.waiting_for_tag.set()
    await message.answer(
        "Введите тег для клиента:",
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.message_handler(state=AddTagStates.waiting_for_tag)
async def process_tag(message: types.Message, state: FSMContext):
    tag = message.text.strip()
    
    existing_tag = get_tag_by_name(tag)
    if existing_tag:
        await message.answer("❌ Такой тег уже существует! Введите другой тег:")
        return
    
    await state.update_data(tag=tag)
    await AddTagStates.waiting_for_deadline.set()
    await message.answer("Введите срок (в формате ДД.ММ):")

@dp.message_handler(state=AddTagStates.waiting_for_deadline)
async def process_deadline(message: types.Message, state: FSMContext):
    deadline = message.text.strip()
    
    try:
        datetime.strptime(deadline, "%d.%m")
    except ValueError:
        await message.answer("❌ Неверный формат! Используйте ДД.ММ (например, 31.12):")
        return
    
    data = await state.get_data()
    tag = data['tag']
    user_id = message.from_user.id
    
    add_tag(user_id, tag, deadline)
    
    await state.finish()
    await message.answer(
        f"✅ Тег '{tag}' успешно добавлен!\n"
        f"📅 Срок: {deadline}",
        reply_markup=get_main_keyboard(user_id)
    )

@dp.message_handler(lambda message: message.text == "💰 Добавить профит")
async def admin_add_profit_start(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user or not user[3]:
        await message.answer("❌ У вас нет прав для этого действия!")
        return
    
    await AdminAddProfit.waiting_for_tag.set()
    await message.answer(
        "Введите тег клиента:",
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.message_handler(state=AdminAddProfit.waiting_for_tag)
async def admin_process_tag(message: types.Message, state: FSMContext):
    tag_name = message.text.strip()
    tag = get_tag_by_name(tag_name)
    
    if not tag:
        await message.answer("❌ Тег не найден! Введите существующий тег:")
        return
    
    await state.update_data(tag_id=tag[0])
    await AdminAddProfit.waiting_for_usd.set()
    await message.answer("Введите сумму в $:")

@dp.message_handler(state=AdminAddProfit.waiting_for_usd)
async def admin_process_usd(message: types.Message, state: FSMContext):
    try:
        amount_usd = float(message.text.replace(',', '.'))
        await state.update_data(amount_usd=amount_usd)
        await AdminAddProfit.waiting_for_rub.set()
        await message.answer("Введите сумму в рублях:")
    except ValueError:
        await message.answer("❌ Введите корректное число:")

@dp.message_handler(state=AdminAddProfit.waiting_for_rub)
async def admin_process_rub(message: types.Message, state: FSMContext):
    try:
        amount_rub = float(message.text.replace(',', '.'))
        data = await state.get_data()
        tag_id = data['tag_id']
        amount_usd = data['amount_usd']
        
        profit_rub = calculate_profit(amount_rub)
        profit_usd = profit_rub / amount_rub * amount_usd
        
        add_payment(tag_id, amount_usd, amount_rub, profit_rub)
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM tags WHERE id = ?", (tag_id,))
        user_id = cursor.fetchone()[0]
        conn.close()
        
        await bot.send_message(
            user_id,
            f"💰 Новый профит!\n"
            f"Сумма: {amount_usd}$\n"
            f"Ваша выплата: {profit_usd:.2f}$"
        )
        
        await state.finish()
        await message.answer(
            f"✅ Профит успешно добавлен!\n"
            f"💵 Сумма: {amount_usd}$ = {amount_rub}₽\n"
            f"📊 Выплата: {profit_usd:.2f}$",
            reply_markup=get_main_keyboard(ADMIN_ID)
        )
        
    except ValueError:
        await message.answer("❌ Введите корректное число:")

@dp.message_handler(lambda message: message.text == "📝 Пометить отписавших")
async def mark_unsubscribed_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user or not user[3]:
        await message.answer("❌ У вас нет прав для этого действия!")
        return
    
    unsubscribed_tags = get_unsubscribed_tags()
    
    if not unsubscribed_tags:
        await message.answer("✅ Нет активных тегов для отметки!")
        return
    
    tags_list = "📋 Список клиентов для отметки:\n\n"
    for i, tag in enumerate(unsubscribed_tags, 1):
        tags_list += f"{i}. Тег: {tag[1]} (Пользователь: @{tag[2]})\n"
    
    tags_list += "\nВведите номера через запятую (например: 1,2,3,4,5)"
    
    await state.update_data(tags_list=unsubscribed_tags)
    await MarkUnsubscribed.waiting_for_selection.set()
    await message.answer(tags_list, reply_markup=types.ReplyKeyboardRemove())

@dp.message_handler(state=MarkUnsubscribed.waiting_for_selection)
async def process_unsubscribed_selection(message: types.Message, state: FSMContext):
    try:
        numbers = [int(x.strip()) for x in message.text.split(',')]
        data = await state.get_data()
        tags_list = data['tags_list']
        
        max_index = len(tags_list)
        invalid_numbers = [n for n in numbers if n < 1 or n > max_index]
        
        if invalid_numbers:
            await message.answer(f"❌ Некорректные номера: {', '.join(map(str, invalid_numbers))}\nВведите номера от 1 до {max_index}:")
            return
        
        marked_count = 0
        for num in numbers:
            tag_id = tags_list[num-1][0]
            add_unsubscribed(tag_id)
            marked_count += 1
        
        await state.finish()
        await message.answer(
            f"✅ Отмечено {marked_count} клиентов как отписавшиеся!",
            reply_markup=get_main_keyboard(ADMIN_ID)
        )
        
    except ValueError:
        await message.answer("❌ Введите номера через запятую (например: 1,2,3,4,5):")

@dp.message_handler(lambda message: message.text == "👥 Клиенты")
async def clients_menu(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(text="📋 Не отписавшиеся", callback_data="view_active"),
        InlineKeyboardButton(text="📋 Отписавшиеся", callback_data="view_unsubscribed"),
        InlineKeyboardButton(text="📋 Все клиенты", callback_data="view_all")
    )
    await message.answer("Выберите действие:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("view_active"))
async def view_active_clients(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    tags = get_user_active_tags(user_id)
    
    if not tags:
        await bot.send_message(callback_query.from_user.id, "У вас нет активных клиентов.")
        await callback_query.answer()
        return
    
    await callback_query.answer()
    await send_paginated_list(callback_query.from_user.id, tags, "active", "Активные клиенты")

@dp.callback_query_handler(lambda c: c.data.startswith("view_unsubscribed"))
async def view_unsubscribed_clients(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    tags = get_user_unsubscribed_tags(user_id)
    
    if not tags:
        await bot.send_message(callback_query.from_user.id, "У вас нет отписавшихся клиентов.")
        await callback_query.answer()
        return
    
    await callback_query.answer()
    await send_paginated_list(callback_query.from_user.id, tags, "unsubscribed", "Отписавшиеся клиенты")

@dp.callback_query_handler(lambda c: c.data.startswith("view_all"))
async def view_all_clients(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    tags = get_all_user_tags(user_id)
    
    if not tags:
        await bot.send_message(callback_query.from_user.id, "У вас нет клиентов.")
        await callback_query.answer()
        return
    
    await callback_query.answer()
    await send_paginated_list(callback_query.from_user.id, tags, "all", "Все клиенты")

async def send_paginated_list(user_id, tags, list_type, title):
    page = 1
    await send_list_page(user_id, tags, list_type, title, page)

async def send_list_page(user_id, tags, list_type, title, page):
    items, page, total_pages = paginate_items(tags, page)
    
    text = f"📋 {title} (стр. {page}/{total_pages}):\n\n"
    for item in items:
        if list_type == "active":
            text += f"🔹 Тег: {item[1]}\n📅 Срок: {item[3]}\n\n"
        elif list_type == "unsubscribed":
            text += f"🔹 Тег: {item[1]}\n📅 Срок: {item[3]}\n📆 Отписался: {item[-1]}\n\n"
        else:  # all
            is_unsubscribed = item[-1]
            status = "❌ Отписался" if is_unsubscribed else "✅ Активен"
            text += f"🔹 Тег: {item[1]}\n📅 Срок: {item[3]}\n📊 Статус: {status}\n\n"
    
    keyboard = get_pagination_keyboard(page, total_pages, list_type)
    await bot.send_message(user_id, text, reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("active_page_") or 
                                   c.data.startswith("unsubscribed_page_") or 
                                   c.data.startswith("all_page_"))
async def pagination_callback(callback_query: types.CallbackQuery):
    data = callback_query.data
    parts = data.split('_')
    list_type = parts[0]
    page = int(parts[2])
    
    user_id = callback_query.from_user.id
    
    if list_type == "active":
        tags = get_user_active_tags(user_id)
        title = "Активные клиенты"
    elif list_type == "unsubscribed":
        tags = get_user_unsubscribed_tags(user_id)
        title = "Отписавшиеся клиенты"
    else:
        tags = get_all_user_tags(user_id)
        title = "Все клиенты"
    
    await callback_query.message.delete()
    await send_list_page(user_id, tags, list_type, title, page)
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == "close")
async def close_callback(callback_query: types.CallbackQuery):
    await callback_query.message.delete()
    await callback_query.answer()

@dp.message_handler(lambda message: message.text == "📈 Личная статистика")
async def personal_stats(message: types.Message):
    user_id = message.from_user.id
    stats = get_user_stats(user_id)
    
    text = f"📊 Ваша личная статистика:\n\n"
    text += f"💰 Общая сумма выплат: {stats['total_payments']:.2f}₽\n"
    text += f"💵 Сумма профитов: {stats['total_profit']:.2f}₽\n"
    text += f"👥 Количество клиентов: {stats['clients_count']}\n"
    text += f"📉 Количество отписавшихся: {stats['unsubscribed_count']}\n"
    text += f"💲 Компенсация за отписавшихся: {stats['refund_amount']:.2f}$"
    
    await message.answer(text, reply_markup=get_main_keyboard(user_id))

@dp.message_handler(lambda message: message.text == "📊 Статистика команды")
async def team_stats(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user or not user[3]:
        await message.answer("❌ У вас нет прав для этого действия!")
        return
    
    stats = get_team_stats()
    
    text = f"📊 Статистика команды:\n\n"
    text += f"👥 Активных работников: {stats['active_workers']}\n"
    text += f"💰 Общая сумма оплат: {stats['total_payments']:.2f}₽\n"
    text += f"💵 Общая сумма профитов: {stats['total_profit']:.2f}₽\n"
    text += f"👤 Всего клиентов: {stats['total_clients']}\n"
    text += f"📉 Всего отписавшихся: {stats['total_unsubscribed']}"
    
    await message.answer(text, reply_markup=get_main_keyboard(user_id))

@dp.message_handler(lambda message: message.text == "Назад")
async def back_to_menu(message: types.Message):
    user_id = message.from_user.id
    await message.answer("Главное меню:", reply_markup=get_main_keyboard(user_id))

if __name__ == "__main__":
    init_db()
    print("Бот запущен!")
    executor.start_polling(dp, skip_updates=True)