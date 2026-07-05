import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

TOKEN = "8623083352:AAHPhZkAFymFxs272OO_YYECCeXQUXfH8is"
ADMIN_IDS = {2010296191}  # сюда Telegram ID админа
DB = "bot.db"

bot = Bot(TOKEN)
dp = Dispatcher(storage=MemoryStorage())


class AddTag(StatesGroup):
    tag = State()
    term = State()


class AddProfit(StatesGroup):
    tag = State()
    usd = State()
    rub = State()


class MarkUnsub(StatesGroup):
    numbers = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def payout_percent(rub: float) -> float:
    if rub <= 1000:
        return 0.80
    if rub <= 5000:
        return 0.70
    if rub <= 10000:
        return 0.60
    return 0.50


async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tag TEXT UNIQUE NOT NULL,
            term TEXT NOT NULL,
            is_unsub INTEGER DEFAULT 0
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS profits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            usd REAL NOT NULL,
            rub REAL NOT NULL,
            payout REAL NOT NULL
        )
        """)
        await db.commit()


def main_kb(user_id: int):
    buttons = [
        [KeyboardButton(text="➕ Вбить тег")],
        [KeyboardButton(text="👥 Клиенты")],
        [KeyboardButton(text="📊 Посмотреть личную статистику")]
    ]

    if is_admin(user_id):
        buttons += [
            [KeyboardButton(text="💰 Добавить профит")],
            [KeyboardButton(text="🚫 Пометить отписавших")],
            [KeyboardButton(text="📈 Статистика команды")]
        ]

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def clients_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Посмотреть не отписавших")],
            [KeyboardButton(text="🚫 Посмотреть отписавших")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Бот запущен.",
        reply_markup=main_kb(message.from_user.id)
    )


@dp.message(F.text == "⬅️ Назад")
async def back(message: Message):
    await message.answer("Главное меню:", reply_markup=main_kb(message.from_user.id))


@dp.message(F.text == "➕ Вбить тег")
async def add_tag_start(message: Message, state: FSMContext):
    await state.set_state(AddTag.tag)
    await message.answer("Впишите тег:")


@dp.message(AddTag.tag)
async def add_tag_get_tag(message: Message, state: FSMContext):
    tag = message.text.strip()

    if not tag:
        await message.answer("Тег не может быть пустым.")
        return

    await state.update_data(tag=tag)
    await state.set_state(AddTag.term)
    await message.answer("Впишите срок в формате 01.01:")


@dp.message(AddTag.term)
async def add_tag_get_term(message: Message, state: FSMContext):
    data = await state.get_data()
    tag = data["tag"]
    term = message.text.strip()

    async with aiosqlite.connect(DB) as db:
        try:
            await db.execute(
                "INSERT INTO clients (user_id, tag, term) VALUES (?, ?, ?)",
                (message.from_user.id, tag, term)
            )
            await db.commit()
            await message.answer(
                f"Тег добавлен:\n\nТег: {tag}\nСрок: {term}",
                reply_markup=main_kb(message.from_user.id)
            )
        except aiosqlite.IntegrityError:
            await message.answer(
                "Такой тег уже есть в базе.",
                reply_markup=main_kb(message.from_user.id)
            )

    await state.clear()


@dp.message(F.text == "👥 Клиенты")
async def clients_menu(message: Message):
    await message.answer("Выберите раздел:", reply_markup=clients_kb())


async def show_clients(message: Message, unsub_status: int):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            """
            SELECT tag, term FROM clients
            WHERE user_id = ? AND is_unsub = ?
            ORDER BY id DESC
            """,
            (message.from_user.id, unsub_status)
        )
        rows = await cursor.fetchall()

    if not rows:
        await message.answer("Список пуст.")
        return

    text = ""
    for i, (tag, term) in enumerate(rows, 1):
        text += f"{i}. {tag} — срок {term}\n"

    await message.answer(text)


@dp.message(F.text == "✅ Посмотреть не отписавших")
async def active_clients(message: Message):
    await show_clients(message, 0)


@dp.message(F.text == "🚫 Посмотреть отписавших")
async def unsub_clients(message: Message):
    await show_clients(message, 1)


@dp.message(F.text == "💰 Добавить профит")
async def add_profit_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.set_state(AddProfit.tag)
    await message.answer("Введите тег:")


@dp.message(AddProfit.tag)
async def add_profit_tag(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    tag = message.text.strip()

    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT user_id FROM clients WHERE tag = ?",
            (tag,)
        )
        row = await cursor.fetchone()

    if not row:
        await message.answer("Такого тега нет в базе.")
        await state.clear()
        return

    await state.update_data(tag=tag, worker_id=row[0])
    await state.set_state(AddProfit.usd)
    await message.answer("Напишите сумму в $:")


@dp.message(AddProfit.usd)
async def add_profit_usd(message: Message, state: FSMContext):
    try:
        usd = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Введите число.")
        return

    await state.update_data(usd=usd)
    await state.set_state(AddProfit.rub)
    await message.answer("Введите сумму в рублях:")


@dp.message(AddProfit.rub)
async def add_profit_rub(message: Message, state: FSMContext):
    try:
        rub = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Введите число.")
        return

    data = await state.get_data()
    tag = data["tag"]
    worker_id = data["worker_id"]
    usd = data["usd"]

    payout = rub * payout_percent(rub)

    async with aiosqlite.connect(DB) as db:
        await db.execute(
            """
            INSERT INTO profits (user_id, tag, usd, rub, payout)
            VALUES (?, ?, ?, ?, ?)
            """,
            (worker_id, tag, usd, rub, payout)
        )
        await db.commit()

    await bot.send_message(
        worker_id,
        f"💰 Новый профит: {payout:.2f}₽\nТег: {tag}"
    )

    await message.answer(
        f"Профит добавлен.\n\nСумма: {rub:.2f}₽\nВыплата: {payout:.2f}₽",
        reply_markup=main_kb(message.from_user.id)
    )
    await state.clear()


@dp.message(F.text == "🚫 Пометить отписавших")
async def mark_unsub_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            """
            SELECT id, tag FROM clients
            WHERE is_unsub = 0
            ORDER BY id ASC
            """
        )
        rows = await cursor.fetchall()

    if not rows:
        await message.answer("Нет активных тегов.")
        return

    await state.update_data(rows=rows)

    text = "Выберите номера отписавших в формате 1,2,3:\n\n"
    for i, (_, tag) in enumerate(rows, 1):
        text += f"{i}. {tag}\n"

    await state.set_state(MarkUnsub.numbers)
    await message.answer(text)


@dp.message(MarkUnsub.numbers)
async def mark_unsub_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    rows = data["rows"]

    try:
        nums = [
            int(x.strip())
            for x in message.text.split(",")
            if x.strip()
        ]
    except ValueError:
        await message.answer("Введите номера в формате 1,2,3")
        return

    selected_ids = []

    for num in nums:
        if 1 <= num <= len(rows):
            selected_ids.append(rows[num - 1][0])

    if not selected_ids:
        await message.answer("Не выбрано ни одного корректного номера.")
        return

    async with aiosqlite.connect(DB) as db:
        for client_id in selected_ids:
            await db.execute(
                "UPDATE clients SET is_unsub = 1 WHERE id = ?",
                (client_id,)
            )
        await db.commit()

    await message.answer(
        f"Отмечено отписавших: {len(selected_ids)}",
        reply_markup=main_kb(message.from_user.id)
    )
    await state.clear()


@dp.message(F.text == "📊 Посмотреть личную статистику")
async def personal_stats(message: Message):
    user_id = message.from_user.id

    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM clients WHERE user_id = ?",
            (user_id,)
        )
        clients_count = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COUNT(*) FROM clients WHERE user_id = ? AND is_unsub = 1",
            (user_id,)
        )
        unsub_count = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COALESCE(SUM(payout), 0) FROM profits WHERE user_id = ?",
            (user_id,)
        )
        payout_sum = (await cursor.fetchone())[0]

    transfer_payment = unsub_count * 0.5

    text = (
        "📊 Личная статистика\n\n"
        f"Сумма выплат: {payout_sum:.2f}₽\n"
        f"Количество клиентов: {clients_count}\n"
        f"Количество отписавших: {unsub_count}\n"
        f"Оплата за переведённых: {transfer_payment:.2f}$"
    )

    await message.answer(text)


@dp.message(F.text == "📈 Статистика команды")
async def team_stats(message: Message):
    if not is_admin(message.from_user.id):
        return

    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT COUNT(DISTINCT user_id) FROM clients"
        )
        workers_count = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COALESCE(SUM(rub), 0) FROM profits"
        )
        total_payments = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COALESCE(SUM(payout), 0) FROM profits"
        )
        total_profits = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COUNT(*) FROM clients"
        )
        clients_count = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COUNT(*) FROM clients WHERE is_unsub = 1"
        )
        unsub_count = (await cursor.fetchone())[0]

    text = (
        "📈 Статистика команды\n\n"
        f"Активных работников: {workers_count}\n"
        f"Сумма оплат без вычета %: {total_payments:.2f}₽\n"
        f"Сумма профитов с вычетом %: {total_profits:.2f}₽\n"
        f"Количество клиентов: {clients_count}\n"
        f"Количество отписавших: {unsub_count}"
    )

    await message.answer(text)


async def main():
    await init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())