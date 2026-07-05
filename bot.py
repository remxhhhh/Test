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
import pytz

# Конфигурация
TOKEN = "8623083352:AAHPhZkAFymFxs272OO_YYECCeXQUXfH8is"
ADMIN_ID = 2010296191
TIMEZONE = pytz.timezone('Europe/Moscow')

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота
storage = MemoryStorage()
bot = Bot(token=TOKEN)
dp = Dispatcher(bot, storage=storage)

# Состояния для FSM
class AddTagStates(StatesGroup):
    waiting_for_tag_and_deadline = State()

class AdminAddProfit(StatesGroup):
    waiting_for_tag = State()
    waiting_for_usd = State()
    waiting_for_rub = State()

class MarkUnsubscribed(StatesGroup):
    waiting_for_selection = State()

class ClientListState(StatesGroup):
    viewing = State()

class CheckTagState(StatesGroup):
    waiting_for_tag = State()

class PayoffState(StatesGroup):
    waiting_for_worker_tag = State()
    waiting_for_confirmation = State()

# Инициализация БД
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        is_admin BOOLEAN DEFAULT 0
    )
    ''')
    
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
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS unsubscribed (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tag_id INTEGER,
        unsubscribed_date TEXT,
        FOREIGN KEY (tag_id) REFERENCES tags (id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS payoffs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        payoff_date TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
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

def get_user_by_username(username):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username LIKE ?", (f"%{username}%",))
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

def get_tag_info(tag_name):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT t.tag, t.deadline, u.username, u.user_id,
           CASE WHEN u2.tag_id IS NOT NULL THEN 1 ELSE 0 END as is_unsubscribed
    FROM tags t 
    JOIN users u ON t.user_id = u.user_id 
    LEFT JOIN unsubscribed u2 ON t.id = u2.tag_id
    WHERE t.tag = ? AND t.is_active = 1
    ''', (tag_name,))
    tag = cursor.fetchone()
    conn.close()
    return tag

def get_all_user_tags_with_status(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT t.id, t.tag, t.deadline, t.created_at,
           CASE WHEN u.tag_id IS NOT NULL THEN 1 ELSE 0 END as is_unsubscribed,
           CASE WHEN p.tag_id IS NOT NULL THEN 1 ELSE 0 END as has_payment
    FROM tags t 
    LEFT JOIN unsubscribed u ON t.id = u.tag_id 
    LEFT JOIN payments p ON t.id = p.tag_id
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
    
    cursor.execute("SELECT id FROM tags WHERE user_id = ? AND is_active = 1", (user_id,))
    tags = cursor.fetchall()
    tag_ids = [tag[0] for tag in tags]
    
    stats = {
        'total_payments_usd': 0,
        'total_payments_rub': 0,
        'total_profit_usd': 0,
        'total_profit_rub': 0,
        'clients_count': len(tags),
        'unsubscribed_count': 0,
        'refund_amount': 0,
        'total_payoffs': 0
    }
    
    if tag_ids:
        placeholders = ','.join('?' * len(tag_ids))
        
        cursor.execute(f"SELECT SUM(amount_rub) FROM payments WHERE tag_id IN ({placeholders})", tag_ids)
        result = cursor.fetchone()[0]
        stats['total_payments_rub'] = result if result else 0
        
        cursor.execute(f"SELECT SUM(amount_usd) FROM payments WHERE tag_id IN ({placeholders})", tag_ids)
        result = cursor.fetchone()[0]
        stats['total_payments_usd'] = result if result else 0
        
        cursor.execute(f"SELECT SUM(profit) FROM payments WHERE tag_id IN ({placeholders})", tag_ids)
        result = cursor.fetchone()[0]
        stats['total_profit_rub'] = result if result else 0
        
        cursor.execute(f"SELECT SUM(amount_usd * profit / amount_rub) FROM payments WHERE tag_id IN ({placeholders}) AND amount_rub > 0", tag_ids)
        result = cursor.fetchone()[0]
        stats['total_profit_usd'] = result if result else 0
        
        cursor.execute(f"SELECT COUNT(*) FROM unsubscribed WHERE tag_id IN ({placeholders})", tag_ids)
        stats['unsubscribed_count'] = cursor.fetchone()[0]
        
        stats['refund_amount'] = stats['unsubscribed_count'] * 0.5
    
    cursor.execute("SELECT SUM(amount) FROM payoffs WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()[0]
    stats['total_payoffs'] = result if result else 0
    
    conn.close()
    return stats

def get_worker_unsubscribed_amount(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM tags WHERE user_id = ? AND is_active = 1", (user_id,))
    tags = cursor.fetchall()
    tag_ids = [tag[0] for tag in tags]
    
    amount = 0
    if tag_ids:
        placeholders = ','.join('?' * len(tag_ids))
        cursor.execute(f"SELECT COUNT(*) FROM unsubscribed WHERE tag_id IN ({placeholders})", tag_ids)
        count = cursor.fetchone()[0]
        amount = count * 0.5
    
    conn.close()
    return amount

def add_payoff(user_id, amount):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO payoffs (user_id, amount, payoff_date) VALUES (?, ?, ?)", 
                  (user_id, amount, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_team_stats():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    stats = {
        'active_workers': 0,
        'total_payments_usd': 0,
        'total_payments_rub': 0,
        'total_profit_usd': 0,
        'total_profit_rub': 0,
        'total_clients': 0,
        'total_unsubscribed': 0
    }
    
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM tags WHERE is_active = 1")
    stats['active_workers'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(amount_rub) FROM payments")
    result = cursor.fetchone()[0]
    stats['total_payments_rub'] = result if result else 0
    
    cursor.execute("SELECT SUM(amount_usd) FROM payments")
    result = cursor.fetchone()[0]
    stats['total_payments_usd'] = result if result else 0
    
    cursor.execute("SELECT SUM(profit) FROM payments")
    result = cursor.fetchone()[0]
    stats['total_profit_rub'] = result if result else 0
    
    cursor.execute("SELECT SUM(amount_usd * profit / amount_rub) FROM payments WHERE amount_rub > 0")
    result = cursor.fetchone()[0]
    stats['total_profit_usd'] = result if result else 0
    
    cursor.execute("SELECT COUNT(*) FROM tags WHERE is_active = 1")
    stats['total_clients'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM unsubscribed")
    stats['total_unsubscribed'] = cursor.fetchone()[0]
    
    conn.close()
    return stats

# Функции для пагинации
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

def get_pagination_keyboard(current_page, total_pages):
    keyboard = InlineKeyboardMarkup(row_width=3)
    buttons = []
    
    if current_page > 1:
        buttons.append(InlineKeyboardButton("⬅️", callback_data=f"page_{current_page-1}"))
    
    buttons.append(InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="current"))
    
    if current_page < total_pages:
        buttons.append(InlineKeyboardButton("➡️", callback_data=f"page_{current_page+1}"))
    
    if buttons:
        keyboard.row(*buttons)
    
    keyboard.row(InlineKeyboardButton("🔄 Обновить", callback_data="refresh"))
    keyboard.row(InlineKeyboardButton("❌ Закрыть", callback_data="close"))
    return keyboard

# Меню с кнопкой "Назад"
def get_main_keyboard(user_id):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    user = get_user(user_id)
    is_admin = user[3] if user else 0
    
    if is_admin:
        buttons_row1 = [KeyboardButton("📝 Добавить мамонта")]
        buttons_row2 = [
            KeyboardButton("💰 Добавить профит"),
            KeyboardButton("📌 Отметить отписку")
        ]
        buttons_row3 = [
            KeyboardButton("📊 Статистика команды"),
            KeyboardButton("👥 Мои мамонты")
        ]
        buttons_row4 = [
            KeyboardButton("🔍 Проверить тег"),
            KeyboardButton("💸 Списать переведенных")
        ]
        buttons_row5 = [KeyboardButton("📈 Личная статистика")]
        
        keyboard.row(*buttons_row1)
        keyboard.row(*buttons_row2)
        keyboard.row(*buttons_row3)
        keyboard.row(*buttons_row4)
        keyboard.row(*buttons_row5)
    else:
        buttons_row1 = [KeyboardButton("📝 Добавить мамонта")]
        buttons_row2 = [KeyboardButton("👥 Мои мамонты")]
        buttons_row3 = [KeyboardButton("📈 Личная статистика")]
        
        keyboard.row(*buttons_row1)
        keyboard.row(*buttons_row2)
        keyboard.row(*buttons_row3)
    
    return keyboard

# Обработчик кнопки "Назад" (возврат в меню)
@dp.message_handler(lambda message: message.text == "◀️ Назад" or message.text == "Назад")
async def back_to_menu(message: types.Message, state: FSMContext):
    await state.finish()
    user_id = message.from_user.id
    await message.answer(
        "📋 Главное меню:",
        reply_markup=get_main_keyboard(user_id)
    )

# Обработчики команд
@dp.message_handler(commands=["start"])
async def start_command(message: types.Message, state: FSMContext):
    await state.finish()
    
    user_id = message.from_user.id
    username = message.from_user.username or "unknown"
    full_name = message.from_user.full_name
    
    add_user(user_id, username, full_name)
    
    await message.answer(
        "🔄 Бот перезапущен!\n\n"
        "👋 Добро пожаловать в игру Мамонты!\n"
        "Выберите действие в меню:",
        reply_markup=get_main_keyboard(user_id)
    )

@dp.message_handler(state='*', commands=["start"])
async def start_state_handler(message: types.Message, state: FSMContext):
    await state.finish()
    await start_command(message, state)

@dp.message_handler(lambda message: message.text == "📝 Добавить мамонта")
async def add_tag_start(message: types.Message):
    await AddTagStates.waiting_for_tag_and_deadline.set()
    await message.answer(
        "Введите тег мамонта и срок одним сообщением:\n"
        "Формат: @user ДД.ММ\n"
        "Пример: @username 31.12",
        reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("◀️ Назад"))
    )

@dp.message_handler(state=AddTagStates.waiting_for_tag_and_deadline)
async def process_tag_and_deadline(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await back_to_menu(message, state)
        return
    
    text = message.text.strip()
    parts = text.split()
    
    if len(parts) < 2:
        await message.answer(
            "❌ Неверный формат!\n"
            "Введите: @user ДД.ММ\n"
            "Пример: @username 31.12"
        )
        return
    
    tag = parts[0]
    if not tag.startswith('@'):
        await message.answer(
            "❌ Тег должен начинаться с @\n"
            "Введите: @user ДД.ММ\n"
            "Пример: @username 31.12"
        )
        return
    
    deadline = ' '.join(parts[1:])
    
    try:
        datetime.strptime(deadline, "%d.%m")
    except ValueError:
        await message.answer(
            "❌ Неверный формат даты!\n"
            "Используйте ДД.ММ\n"
            "Пример: 31.12"
        )
        return
    
    existing_tag = get_tag_by_name(tag)
    if existing_tag:
        await message.answer("❌ Такой тег уже существует! Введите другой тег:")
        return
    
    user_id = message.from_user.id
    add_tag(user_id, tag, deadline)
    
    await state.finish()
    await message.answer(
        f"✅ Мамонт {tag} успешно добавлен!\n"
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
        "Введите тег мамонта:",
        reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("◀️ Назад"))
    )

@dp.message_handler(state=AdminAddProfit.waiting_for_tag)
async def admin_process_tag(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await back_to_menu(message, state)
        return
    
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
    if message.text == "◀️ Назад":
        await back_to_menu(message, state)
        return
    
    try:
        amount_usd = float(message.text.replace(',', '.'))
        await state.update_data(amount_usd=amount_usd)
        await AdminAddProfit.waiting_for_rub.set()
        await message.answer("Введите сумму в рублях:")
    except ValueError:
        await message.answer("❌ Введите корректное число:")

@dp.message_handler(state=AdminAddProfit.waiting_for_rub)
async def admin_process_rub(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await back_to_menu(message, state)
        return
    
    try:
        amount_rub = float(message.text.replace(',', '.'))
        data = await state.get_data()
        tag_id = data['tag_id']
        amount_usd = data['amount_usd']
        
        profit_rub = calculate_profit(amount_rub)
        profit_usd = (profit_rub / amount_rub) * amount_usd if amount_rub > 0 else 0
        
        add_payment(tag_id, amount_usd, amount_rub, profit_rub)
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM tags WHERE id = ?", (tag_id,))
        user_id = cursor.fetchone()[0]
        conn.close()
        
        await bot.send_message(
            user_id,
            f"💰 Новый профит!\n\n"
            f"💵 Сумма: {amount_rub}₽\n"
            f"💲 Твоя выплата: {profit_usd:.2f}$"
        )
        
        await state.finish()
        await message.answer(
            f"✅ Профит успешно добавлен!\n\n"
            f"💵 Сумма в $: {amount_usd}$\n"
            f"💵 Сумма в ₽: {amount_rub}₽\n"
            f"💲 Выплата: {profit_usd:.2f}$",
            reply_markup=get_main_keyboard(ADMIN_ID)
        )
        
    except ValueError:
        await message.answer("❌ Введите корректное число:")

@dp.message_handler(lambda message: message.text == "📌 Отметить отписку")
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
    
    tags_list = "📋 Список мамонтов для отметки отписки:\n\n"
    for i, tag in enumerate(unsubscribed_tags, 1):
        tags_list += f"{i}. {tag[1]} (@{tag[2]})\n"
    
    tags_list += "\nВведите номера через запятую (например: 1,2,3,4,5)"
    
    await state.update_data(tags_list=unsubscribed_tags)
    await MarkUnsubscribed.waiting_for_selection.set()
    await message.answer(tags_list, reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("◀️ Назад")))

@dp.message_handler(state=MarkUnsubscribed.waiting_for_selection)
async def process_unsubscribed_selection(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await back_to_menu(message, state)
        return
    
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
            f"✅ Отмечено {marked_count} мамонтов как отписавшиеся!",
            reply_markup=get_main_keyboard(ADMIN_ID)
        )
        
    except ValueError:
        await message.answer("❌ Введите номера через запятую (например: 1,2,3,4,5):")

@dp.message_handler(lambda message: message.text == "👥 Мои мамонты")
async def view_all_clients(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    tags = get_all_user_tags_with_status(user_id)
    
    if not tags:
        await message.answer("У вас нет мамонтов.")
        return
    
    await state.update_data(clients_list=tags)
    await ClientListState.viewing.set()
    
    moscow_time = datetime.now(TIMEZONE).strftime("%H:%M")
    page = 1
    await send_clients_page(message, user_id, tags, page, moscow_time)

async def send_clients_page(message_or_callback, user_id, tags, page, update_time):
    items, page, total_pages = paginate_items(tags, page)
    
    text = f"📋 Список мамонтов\n"
    text += f"🕐 Последнее обновление: {update_time} UTC+3\n\n"
    
    for item in items:
        tag_name = item[1]
        deadline = item[2]
        is_unsubscribed = item[4]
        has_payment = item[5]
        
        if has_payment:
            status = "💰"
        elif is_unsubscribed:
            status = "✅"
        else:
            status = "❌"
        
        text += f"{status} {tag_name} | 📅 {deadline}\n"
    
    text += f"\nСтраница {page}/{total_pages}"
    
    keyboard = get_pagination_keyboard(page, total_pages)
    
    if isinstance(message_or_callback, types.Message):
        await message_or_callback.answer(text, reply_markup=keyboard)
    else:
        await message_or_callback.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("page_"), state=ClientListState.viewing)
async def pagination_callback(callback_query: types.CallbackQuery, state: FSMContext):
    page = int(callback_query.data.split('_')[1])
    user_id = callback_query.from_user.id
    
    data = await state.get_data()
    tags = data.get('clients_list', [])
    
    if not tags:
        await callback_query.message.edit_text("❌ Список мамонтов не найден. Нажмите 'Мои мамонты' заново.")
        await callback_query.answer()
        await state.finish()
        return
    
    moscow_time = datetime.now(TIMEZONE).strftime("%H:%M")
    await send_clients_page(callback_query, user_id, tags, page, moscow_time)
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == "refresh", state=ClientListState.viewing)
async def refresh_callback(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    tags = get_all_user_tags_with_status(user_id)
    
    if not tags:
        await callback_query.message.edit_text("У вас нет мамонтов.")
        await callback_query.answer()
        await state.finish()
        return
    
    await state.update_data(clients_list=tags)
    
    moscow_time = datetime.now(TIMEZONE).strftime("%H:%M")
    page = 1
    await send_clients_page(callback_query, user_id, tags, page, moscow_time)
    await callback_query.answer("🔄 Список обновлен!")

@dp.callback_query_handler(lambda c: c.data == "close", state=ClientListState.viewing)
async def close_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.delete()
    await state.finish()
    user_id = callback_query.from_user.id
    await bot.send_message(user_id, "📋 Главное меню:", reply_markup=get_main_keyboard(user_id))
    await callback_query.answer()

@dp.message_handler(lambda message: message.text == "🔍 Проверить тег")
async def check_tag_start(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user or not user[3]:
        await message.answer("❌ У вас нет прав для этого действия!")
        return
    
    await CheckTagState.waiting_for_tag.set()
    await message.answer(
        "Введите тег для проверки:",
        reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("◀️ Назад"))
    )

@dp.message_handler(state=CheckTagState.waiting_for_tag)
async def check_tag_process(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await back_to_menu(message, state)
        return
    
    tag_name = message.text.strip()
    tag_info = get_tag_info(tag_name)
    
    if not tag_info:
        await message.answer("❌ Тег не найден в базе данных!")
        await state.finish()
        await message.answer("📋 Главное меню:", reply_markup=get_main_keyboard(message.from_user.id))
        return
    
    tag, deadline, username, user_id, is_unsubscribed = tag_info
    status = "✅ Отписался" if is_unsubscribed else "❌ Не отписался"
    
    await state.finish()
    await message.answer(
        f"🔍 Информация о теге:\n\n"
        f"📌 Тег: {tag}\n"
        f"📅 Срок: {deadline}\n"
        f"👤 Воркер: @{username}\n"
        f"📊 Статус: {status}",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@dp.message_handler(lambda message: message.text == "💸 Списать переведенных")
async def payoff_start(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user or not user[3]:
        await message.answer("❌ У вас нет прав для этого действия!")
        return
    
    await PayoffState.waiting_for_worker_tag.set()
    await message.answer(
        "Введите тег воркера (например: @username):",
        reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("◀️ Назад"))
    )

@dp.message_handler(state=PayoffState.waiting_for_worker_tag)
async def payoff_process_worker(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await back_to_menu(message, state)
        return
    
    worker_tag = message.text.strip()
    
    if not worker_tag.startswith('@'):
        worker_tag = '@' + worker_tag
    
    # Ищем воркера
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username FROM users WHERE username LIKE ?", (f"%{worker_tag[1:]}%",))
    worker = cursor.fetchone()
    conn.close()
    
    if not worker:
        await message.answer("❌ Воркер не найден! Проверьте тег.")
        return
    
    worker_id, worker_username = worker
    
    # Считаем сумму за отписавшихся
    amount = get_worker_unsubscribed_amount(worker_id)
    
    if amount == 0:
        await message.answer(
            f"📊 У воркера @{worker_username} нет отписавшихся мамонтов.\n"
            f"Сумма к списанию: 0$"
        )
        await state.finish()
        await message.answer("📋 Главное меню:", reply_markup=get_main_keyboard(message.from_user.id))
        return
    
    await state.update_data(worker_id=worker_id, worker_username=worker_username, amount=amount)
    await PayoffState.waiting_for_confirmation.set()
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ Выплатил", callback_data="confirm_payoff"),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_payoff")
    )
    
    await message.answer(
        f"📊 Информация о списании:\n\n"
        f"👤 Воркер: @{worker_username}\n"
        f"🦣 Отписавшихся мамонтов: {int(amount/0.5)}\n"
        f"💲 Сумма к списанию: {amount:.2f}$\n\n"
        f"Подтвердите списание:",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data == "confirm_payoff", state=PayoffState.waiting_for_confirmation)
async def confirm_payoff(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    worker_id = data.get('worker_id')
    worker_username = data.get('worker_username')
    amount = data.get('amount')
    
    if not worker_id or not amount:
        await callback_query.message.edit_text("❌ Ошибка! Попробуйте заново.")
        await state.finish()
        await callback_query.answer()
        return
    
    # Сохраняем списание
    add_payoff(worker_id, amount)
    
    await state.finish()
    await callback_query.message.edit_text(
        f"✅ Списание выполнено!\n\n"
        f"👤 Воркер: @{worker_username}\n"
        f"💲 Сумма: {amount:.2f}$\n"
        f"📅 Дата: {datetime.now(TIMEZONE).strftime('%d.%m.%Y %H:%M')}"
    )
    
    # Отправляем уведомление воркеру
    await bot.send_message(
        worker_id,
        f"📢 Вам начислена выплата за переведенных мамонтов!\n\n"
        f"💰 Сумма: {amount:.2f}$"
    )
    
    await callback_query.answer("✅ Списание подтверждено!")
    await bot.send_message(callback_query.from_user.id, "📋 Главное меню:", reply_markup=get_main_keyboard(callback_query.from_user.id))

@dp.callback_query_handler(lambda c: c.data == "cancel_payoff", state=PayoffState.waiting_for_confirmation)
async def cancel_payoff(callback_query: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await callback_query.message.edit_text("❌ Списание отменено.")
    await callback_query.answer()
    await bot.send_message(callback_query.from_user.id, "📋 Главное меню:", reply_markup=get_main_keyboard(callback_query.from_user.id))

@dp.message_handler(lambda message: message.text == "📈 Личная статистика")
async def personal_stats(message: types.Message):
    user_id = message.from_user.id
    stats = get_user_stats(user_id)
    
    text = f"📊 Ваша личная статистика:\n\n"
    text += f"💵 Сумма профитов: ${stats['total_profit_usd']:.2f}\n"
    text += f"🦣 Количество мамонтов: {stats['clients_count']}\n"
    text += f"📝 Количество переведенных: {stats['unsubscribed_count']}\n"
    text += f"🗂️ Оплата за переведенных: ${stats['refund_amount']:.2f}\n"
    text += f"💸 Заработок с переведенных: ${stats['total_payoffs']:.2f}"
    
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
    text += f"👥 Активных воркеров: {stats['active_workers']}\n"
    text += f"💰 Общая сумма оплат: ${stats['total_payments_usd']:.2f}\n"
    text += f"💵 Общая сумма профитов: ${stats['total_profit_usd']:.2f}\n"
    text += f"🦣 Всего мамонтов: {stats['total_clients']}\n"
    text += f"📉 Всего отписавшихся: {stats['total_unsubscribed']}"
    
    await message.answer(text, reply_markup=get_main_keyboard(user_id))

@dp.message_handler(state='*')
async def handle_all_states(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.finish()
        user_id = message.from_user.id
        await message.answer(
            "🔄 Действие отменено. Возврат в главное меню.",
            reply_markup=get_main_keyboard(user_id)
        )

if __name__ == "__main__":
    init_db()
    print("🚀 Бот запущен!")
    executor.start_polling(dp, skip_updates=True)