import asyncio
import logging
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ================= НАСТРОЙКИ =================
API_TOKEN = '8660319488:AAFYUruQjHWONUcBtCtR7YhVVW6mvOAbXj4' 
ADMIN_ID = 8668425707  # <-- ВСТАВЬ СВОЙ ID
PASSWORD = "белый"
DB_NAME = "support_bot.db"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ================= РАБОТА С БАЗОЙ ДАННЫХ (Асинхронно) =================

async def init_db():
    """Создает таблицы, если их нет"""
    async with aiosqlite.connect(DB_NAME) as db:
        # Таблица пользователей (кто прошел пароль)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                status TEXT DEFAULT 'pending'
            )
        ''')
        # Таблица обращений (тикеты)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                text TEXT,
                status TEXT DEFAULT 'new',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.commit()
        logging.info("База данных инициализирована.")

async def add_user(user_id, username, full_name):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('INSERT OR IGNORE INTO users (user_id, username, full_name, status) VALUES (?, ?, ?, ?)',
                         (user_id, username, full_name, 'verified'))
        await db.commit()

async def get_user_status(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('SELECT status FROM users WHERE user_id = ?', (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def create_ticket(user_id, text):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('INSERT INTO tickets (user_id, text, status) VALUES (?, ?, ?)',
                         (user_id, text, 'new'))
        await db.commit()
        # Получаем ID последнего созданного тикета
        cursor = await db.execute('SELECT last_insert_rowid()')
        last_id = await cursor.fetchone()
        return last_id[0]

async def get_user_tickets(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('SELECT id, text, status FROM tickets WHERE user_id = ? ORDER BY id DESC', (user_id,))
        return await cursor.fetchall()

async def get_stats():
    async with aiosqlite.connect(DB_NAME) as db:
        # Кол-во пользователей
        cursor_u = await db.execute('SELECT COUNT(*) FROM users')
        total_users = (await cursor_u.fetchone())[0]
        
        # Кол-во тикетов
        cursor_t = await db.execute('SELECT COUNT(*), SUM(CASE WHEN status = "new" THEN 1 ELSE 0 END) FROM tickets')
        res = await cursor_t.fetchone()
        total_tickets = res[0] or 0
        new_tickets = res[1] or 0
        
        return total_users, total_tickets, new_tickets

# ================= КЛАВИАТУРЫ =================
def get_main_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="🆘 Создать обращение", callback_data="create_ticket")
    builder.button(text="📂 Мои обращения", callback_data="my_tickets")
    builder.button(text="📩 Написать в ЛС (DM)", url=f"t.me/belovP2P")
    builder.adjust(1, 1, 1)
    return builder.as_markup()

def get_back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="main_menu")
    return builder.as_markup()

# ================= ЛОГИКА БОТА =================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    status = await get_user_status(user_id)
    
    if status == 'verified':
        await message.answer("Добро пожаловать обратно! Выберите действие:", reply_markup=get_main_menu())
        return

    await message.answer("🔒 Для доступа к боту поддержки введите секретное слово:белый")
    # Сохраняем временное состояние в памяти (для простоты), можно тоже в БД
    users_temp_state[user_id] = 'waiting_password'

@dp.message(F.text)
async def check_password(message: types.Message):
    user_id = message.from_user.id
    state = users_temp_state.get(user_id)
    
    if state == 'waiting_password':
        if message.text.strip().lower() == PASSWORD.lower():
            await add_user(user_id, message.from_user.username, message.from_user.full_name)
            await message.answer("✅ Доступ разрешен! Добро пожаловать в службу поддержки.", reply_markup=get_main_menu())
            users_temp_state.pop(user_id, None)
        else:
            await message.answer("❌ Неверный пароль. Попробуйте еще раз.")
        return
    
    # Если пользователь уже авторизован, но просто пишет текст без команды - игнорируем,
    # так как создание тикета запускается через кнопку.
    if state != 'waiting_ticket_text':
        return

    # Обработка текста тикета (если мы в состоянии ожидания текста)
    if users_temp_state.get(user_id) == 'waiting_ticket_text':
        ticket_id = await create_ticket(user_id, message.text)
        
        admin_text = (
            f"📩 **НОВОЕ ОБРАЩЕНИЕ**\n\n"
            f"ID тикета: #{ticket_id}\n"
            f"Пользователь: @{message.from_user.username} ({message.from_user.full_name})\n"
            f"Текст: {message.text}"
        )
        try:
            await bot.send_message(chat_id=8668425707, text=admin_text, parse_mode="Markdown")
            await message.answer("✅ Ваше обращение успешно отправлено администратору!")
        except Exception as e:
            logging.error(e)
            await message.answer("Ошибка отправки. Администратор не найден.")
        
        users_temp_state.pop(user_id, None)

# Глобальное хранилище временных состояний (кто что сейчас делает)
users_temp_state = {}

@dp.callback_query(F.data == "main_menu")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text("Главное меню поддержки:", reply_markup=get_main_menu())

@dp.callback_query(F.data == "create_ticket")
async def start_create_ticket(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if await get_user_status(user_id) != 'verified':
        await callback.answer("Сначала пройдите авторизацию!", show_alert=True)
        return
        
    await callback.message.edit_text("📝 Напишите суть вашего обращения:")
    users_temp_state[user_id] = 'waiting_ticket_text'

@dp.callback_query(F.data == "my_tickets")
async def show_my_tickets(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    tickets_list = await get_user_tickets(user_id)
    
    if not tickets_list:
        await callback.message.edit_text("У вас пока нет обращений.", reply_markup=get_back_keyboard())
        return

    text = "📂 **Ваши обращения:**\n\n"
    for tid, t_text, t_status in tickets_list:
        status_emoji = "📩" if t_status == 'new' else "✅"
        preview = t_text[:40] + "..." if len(t_text) > 40 else t_text
        text += f"{status_emoji} ID #{tid}: {preview}\n"
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_back_keyboard())

@dp.message(Command("stats"))
async def admin_stats(message: types.Message):
    if message.from_user.id != 8668425707:
        return
    
    total_users, total_tickets, new_tickets = await get_stats()
    
    text = (
        f"📊 **Статистика бота**\n\n"
        f"✅ Всего пользователей: {total_users}\n"
        f"🎫 Всего обращений: {total_tickets}\n"
        f"❗ Новых обращений: {new_tickets}"
    )
    await message.answer(text, parse_mode="Markdown")

async def main():
    await init_db()  # Инициализируем БД при старте
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
