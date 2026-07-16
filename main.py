import asyncio
import logging
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ================= НАСТРОЙКИ =================
API_TOKEN = '8660319488:AAFYUruQjHWONUcBtCtR7YhVVW6mvOAbXj4'
ADMIN_ID = 8668425707  # <-- Вставь сюда свой ID (лучше не хардкодить в других местах)
PASSWORD = "белый"     # Пароль для обычных пользователей
ADMIN_PASSWORD = "040824" # <-- НОВЫЙ: Пароль для входа в панель админа
DB_NAME = "support_bot.db"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Хранилище временных состояний (кто что сейчас делает)
users_temp_state = {} 

# ================= РАБОТА С БАЗОЙ ДАННЫХ =================

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                status TEXT DEFAULT 'pending'
            )
        ''')
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
        cursor = await db.execute('SELECT last_insert_rowid()')
        last_id = await cursor.fetchone()
        return last_id[0]

async def get_user_tickets(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('SELECT id, text, status FROM tickets WHERE user_id = ? ORDER BY id DESC', (user_id,))
        return await cursor.fetchall()

async def get_stats():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor_u = await db.execute('SELECT COUNT(*) FROM users')
        total_users = (await cursor_u.fetchone())[0]
        
        cursor_t = await db.execute('SELECT COUNT(*), SUM(CASE WHEN status = "new" THEN 1 ELSE 0 END) FROM tickets')
        res = await cursor_t.fetchone()
        total_tickets = res[0] or 0
        new_tickets = res[1] or 0
        
        return total_users, total_tickets, new_tickets

async def get_all_tickets():
    """Получает все тикеты для админа"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('SELECT id, user_id, text, status FROM tickets ORDER BY id DESC LIMIT 20')
        return await cursor.fetchall()

# ================= КЛАВИАТУРЫ =================

def get_main_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="🆘 Создать обращение", callback_data="create_ticket")
    builder.button(text="📂 Мои обращения", callback_data="my_tickets")
    builder.button(text="📩 Написать в ЛС (DM)", url=f"https://t.me/{ADMIN_ID}")
    builder.adjust(1, 1, 1)
    return builder.as_markup()

def get_back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="main_menu")
    return builder.as_markup()

# --- АДМИНСКАЯ ПАНЕЛЬ ---
def get_admin_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="admin_stats")
    builder.button(text="🎫 Все тикеты", callback_data="admin_all_tickets")
    builder.button(text="🚪 Выйти из панели", callback_data="admin_logout")
    builder.adjust(2, 1)
    return builder.as_markup()

# ================= ЛОГИКА БОТА =================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    status = await get_user_status(user_id)
    
    if status == 'verified':
        await message.answer("Добро пожаловать обратно! Выберите действие:", reply_markup=get_main_menu())
        return

    await message.answer("🔒 Для доступа к боту поддержки введите секретное слово:")
    users_temp_state[user_id] = 'waiting_password'

@dp.message(F.text)
async def check_password(message: types.Message):
    user_id = message.from_user.id
    state = users_temp_state.get(user_id)
    
    # 1. Проверка пароля обычного пользователя
    if state == 'waiting_password':
        if message.text.strip().lower() == PASSWORD.lower():
            await add_user(user_id, message.from_user.username, message.from_user.full_name)
            await message.answer("✅ Доступ разрешен! Добро пожаловать в службу поддержки.", reply_markup=get_main_menu())
            users_temp_state.pop(user_id, None)
        else:
            await message.answer("❌ Неверный пароль. Попробуйте еще раз.")
        return

    # 2. Проверка пароля Админа (если админ ввел команду /admin и ждет пароль)
    if state == f'waiting_admin_pw_{user_id}':
        if message.text.strip() == ADMIN_PASSWORD:
            users_temp_state[user_id] = 'admin_logged_in'
            await message.answer(
                f"🛡️ **Панель администратора активирована!**\n\n"
                f"Выберите действие:",
                parse_mode="Markdown",
                reply_markup=get_admin_menu()
            )
        else:
            await message.answer("❌ Неверный пароль администратора. Доступ запрещен.")
            users_temp_state.pop(user_id, None)
        return

    # 3. Обработка текста тикета (если мы в состоянии ожидания текста)
    if state == 'waiting_ticket_text':
        ticket_id = await create_ticket(user_id, message.text)
        
        admin_text = (
            f"📩 **НОВОЕ ОБРАЩЕНИЕ**\n\n"
            f"ID тикета: #{ticket_id}\n"
            f"Пользователь: @{message.from_user.username} ({message.from_user.full_name})\n"
            f"Текст: {message.text}"
        )
        try:
            await bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode="Markdown")
            await message.answer("✅ Ваше обращение успешно отправлено администратору!")
        except Exception as e:
            logging.error(e)
            await message.answer("Ошибка отправки. Администратор не найден.")
        
        users_temp_state.pop(user_id, None)

# Команда входа в админку
@dp.message(Command("admin"))
async def start_admin_login(message: types.Message):
    user_id = message.from_user.id
    
    # Если это не тот самый админ по ID, даже не спрашиваем пароль
    if user_id != ADMIN_ID:
        await message.answer("❌ У вас нет прав для доступа к админ-панели.")
        return

    await message.answer(f"🔐 Введите пароль администратора ({ADMIN_PASSWORD}):")
    users_temp_state[user_id] = f'waiting_admin_pw_{user_id}'

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

# --- ОБРАБОТЧИКИ АДМИН-ПАНЕЛИ ---

@dp.callback_query(F.data == "admin_logout")
async def admin_logout(callback: types.CallbackQuery):
    users_temp_state.pop(callback.from_user.id, None)
    await callback.message.edit_text("🚪 Вы вышли из панели администратора.", reply_markup=get_main_menu())

@dp.callback_query(F.data == "admin_stats")
async def admin_show_stats(callback: types.CallbackQuery):
    # Двойная проверка: вдруг кто-то нажал кнопку, не войдя в панель
    if users_temp_state.get(callback.from_user.id) != 'admin_logged_in':
        await callback.answer("Сессия истекла или вы не авторизованы", show_alert=True)
        return

    total_users, total_tickets, new_tickets = await get_stats()
    
    text = (
        f"📊 **Статистика бота**\n\n"
        f"✅ Всего пользователей: {total_users}\n"
        f"🎫 Всего обращений: {total_tickets}\n"
        f"❗ Новых обращений: {new_tickets}"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_admin_menu())

@dp.callback_query(F.data == "admin_all_tickets")
async def admin_show_all_tickets(callback: types.CallbackQuery):
    if users_temp_state.get(callback.from_user.id) != 'admin_logged_in':
        await callback.answer("Сессия истекла", show_alert=True)
        return

    all_tickets = await get_all_tickets()
    
    if not all_tickets:
        await callback.message.edit_text("Нет обращений.", reply_markup=get_admin_menu())
        return

    text = "🎫 **Все обращения (последние 20):**\n\n"
    for tid, uid, t_text, t_status in all_tickets:
        status_emoji = "📩" if t_status == 'new' else "✅"
        text += f"{status_emoji} #{tid} (User {uid}): {t_text[:30]}...\n"
    
    await callback.message.edit_text(text, reply_markup=get_admin_menu())

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
