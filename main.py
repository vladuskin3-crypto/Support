import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ================= НАСТРОЙКИ =================
BOT_TOKEN = "8660319488:AAFYUruQjHWONUcBtCtR7YhVVW6mvOAbXj4"
ADMIN_ID = 8668425707  # Вставь сюда числовой ID админа
# =============================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Машина состояний: ждём сообщение для обращения
class AppealState(StatesGroup):
    waiting_for_appeal = State()

def get_main_keyboard():
    kb = [
        [
            InlineKeyboardButton(text="Мой ЛС", callback_data="my_ls"),
            InlineKeyboardButton(text="Написать обращение", callback_data="send_appeal"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Приветствую!напиши свой силовой вопрос и я как смогу сразу отвечу тебе Брух)!",
        reply_markup=get_main_keyboard()
    )

@dp.callback_query(F.data == "my_ls")
async def cb_my_ls(callback: types.CallbackQuery):
    await callback.message.answer("Мои личные сообщения: @belovP2P")
    await callback.answer()

@dp.callback_query(F.data == "send_appeal")
async def cb_send_appeal(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Напишите ваше обращение, и я перешлю его админу."
    )
    await state.set_state(AppealState.waiting_for_appeal)
    await callback.answer()

@dp.message(AppealState.waiting_for_appeal)
async def process_appeal(message: types.Message, state: FSMContext):
    user_info = (
        f"Пользователь: {message.from_user.full_name} "
        f"(ID: {message.from_user.id})"
    )
    # Пересылаем админу сообщение пользователя (с подписью от кого)
    try:
        await bot.send_message(
            chat_id=8668425707,
            text=user_info,
        )
        await message.copy_to(chat_id=ADMIN_ID)  # пересылка самого сообщения
    except Exception as e:
        # Если бот не может написать админу (например, админ не запускал бота)
        await message.answer("Не удалось отправить обращение: админ не запустил бота.")
        print("Ошибка отправки админу:", e)
        await state.clear()
        return

    await message.answer("Ваше обращение отправлено админу, скоро будет ответ!")
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
