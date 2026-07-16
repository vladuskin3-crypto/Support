import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ================= НАСТРОЙКИ =================
API_TOKEN = '8660319488:AAFYUruQjHWONUcBtCtR7YhVVW6mvOAbXj4'  # <-- Вставь токен
ADMIN_ID = 8668425707                   # <-- ВСТАВЬ СЮДА СВОЙ ЧИСЛОВОЙ ID (не юзернейм!)
PASSWORD = "белый"                     # <-- Пароль для входа

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ================= БАЗА ДАННЫХ (В ПАМЯТИ) =================
# users: { user_id: {status: 'verified', name: '...'} }
users = {} 
# tickets: { ticket_id: {user_id, text, status} }
tickets = {}
# ticket_history: { user_id: [ticket_ids...] }
ticket_history = {}

next_ticket_id = 1

# ================= КЛАВИАТУРЫ =================

def get_main_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="🆘 Создать обращение", callback_data="create_ticket")
    builder.button(text="📂 Мои обращения", callback_data="my_tickets")
    builder.button(text="📩 Написать в ЛС (DM)", url=f"https://t.me/belovP2P") # Ссылка на админа
    builder.adjust(1, 1, 1)
    return builder.as_markup()

def get_back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="main_menu")
    return builder.as_markup()

# ================= ЛОГИКА ПАРОЛЯ =================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    # Если пользователь уже прошел проверку
    if users.get(user_id) and users[user_id].get('status') == 'verified':
        await message.answer(
            "Добро пожаловать обратно! Выберите действие:",
            reply_markup=get_main_menu()
        )
        return

    # Просим ввести пароль
    await message.answer("🔒 Для доступа к боту поддержки введите секретное слово белый:")
    users[user_id] = {'status': 'waiting_password', 'name': message.from_user.full_name}

@dp.message(F.text)
async def check_password(message: types.Message):
    user_id = message.from_user.id
    user_data = users.get(user_id)
    
    if user_data and user_data['status'] == 'waiting_password':
        if message.text.strip().lower() == PASSWORD.lower():
            users[user_id]['status'] = 'verified'
            await message.answer(
                "✅ Доступ разрешен! Добро пожаловать в службу поддержки.",
                reply_markup=get_main_menu()
            )
        else:
            await message.answer("❌ Неверный пароль. Попробуйте еще раз или свяжитесь с администрацией.")
        return
    
    # Если пароль уже введен, игнорируем обычные текстовые сообщения без команд
    # (Логика обработки билетов идет через callback_query или отдельные состояния)

# ================= ФУНКЦИОНАЛ ОБРАЩЕНИЙ =================

@dp.callback_query(F.data == "main_menu")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Главное меню поддержки:",
        reply_markup=get_main_menu()
    )

@dp.callback_query(F.data == "create_ticket")
async def start_create_ticket(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if users.get(user_id, {}).get('status') != 'verified':
        await callback.answer("Сначала пройдите авторизацию!", show_alert=True)
        return
        
    await callback.message.edit_text("📝 Напишите суть вашего обращения и что вы хотите получить:")
    users[user_id]['temp_status'] = 'waiting_ticket_text'

@dp.message(F.text)
async def process_ticket_text(message: types.Message):
    user_id = message.from_user.id
    user_data = users.get(user_id)

    if user_data and user_data.get('temp_status') == 'waiting_ticket_text':
        global next_ticket_id
        
        # Создаем тикет
        ticket_id = next_ticket_id
        next_ticket_id += 1
        
        tickets[ticket_id] = {
            'user_id': user_id,
            'text': message.text,
            'status': 'new' # new, answered, closed
        }
        
        if user_id not in ticket_history:
            ticket_history[user_id] = []
        ticket_history[user_id].append(ticket_id)
        
        # Отправляем тикет Админу
        admin_text = (
            f"📩 **НОВОЕ ОБРАЩЕНИЕ**\n\n"
            f"ID тикета: #{ticket_id}\n"
            f"Пользователь: @{message.from_user.username} ({message.from_user.full_name})\n"
            f"Текст: {message.text}"
        )
        try:
            await bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode="Markdown")
            await message.answer("✅ Ваше обращение успешно отправлено администратору! Ожидайте ответа.")
        except Exception as e:
            await message.answer("Ошибка отправки. Администратор не найден или заблокировал бота.")
            logging.error(e)
            
        users[user_id]['temp_status'] = None
    else:
        # Если написали текст не в процессе создания тикета, игнорируем или возвращаем в меню
        pass

# ================= МОИ ОБРАЩЕНИЯ =================

@dp.callback_query(F.data == "my_tickets")
async def show_my_tickets(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    my_ids = ticket_history.get(user_id, [])
    
    if not my_ids:
        await callback.message.edit_text("У вас пока нет обращений.", reply_markup=get_back_keyboard())
        return

    text = "📂 **Ваши обращения:**\n\n"
    for tid in my_ids:
        t = tickets.get(tid)
        status_emoji = "📩" if t['status'] == 'new' else "✅"
        text += f"{status_emoji} ID #{tid}: {t['text'][:50]}...\n"
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_back_keyboard())

# ================= АДМИН ПАНЕЛЬ =================

# Команда /stats для админа
@dp.message(Command("stats"))
async def admin_stats(message: types.Message):
    if message.from_user.id != 8668425707:
        return # Игнорируем, если не админ
    
    total_users = len([u for u in users.values() if u['status'] == 'verified'])
    total_tickets = len(tickets)
    new_tickets = len([t for t in tickets.values() if t['status'] == 'new'])
    
    text = (
        f"📊 **Статистика бота**\n\n"
        f"✅ Всего пользователей: {total_users}\n"
        f"🎫 Всего обращений: {total_tickets}\n"
        f"❗ Новых обращений: {new_tickets}"
    )
    await message.answer(text, parse_mode="Markdown")

# Обработка ответа админа (упрощенно: если админ пишет в ЛС боту)
# Примечание: В полноценной версии тут нужна сложная логика привязки ответа к тикету.
# Здесь реализована только отправка тикета админу.

# ================= ЗАПУСК =================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
