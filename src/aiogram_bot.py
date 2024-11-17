from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
import os
import asyncio
from database import SessionLocal
from models import TelegramUser, UserMedia, MediaType
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("Не установлена переменная окружения BOT_TOKEN")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class RegistrationStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_age = State()
    waiting_for_about_me = State()
    waiting_for_looking_for = State()
    waiting_for_media = State()

def get_profile_keyboard():
    keyboard = [[types.KeyboardButton(text="Моя анкета")]]
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_profile_actions_keyboard():
    keyboard = [
        [
            types.KeyboardButton(text="1"),
            types.KeyboardButton(text="2")
        ]
    ]
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_done_keyboard():
    keyboard = [[types.KeyboardButton(text="Готово ✅")]]
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

PROFILE_ACTIONS_MESSAGE = """Выберите действие:
1. Заполнить анкету заново
2. Удалить мою анкету"""

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(TelegramUser).filter(TelegramUser.telegram_id == message.from_user.id).first()
    
    if user:
        await message.reply("С возвращением! Используйте кнопку 'Моя анкета' для просмотра данных.", 
                          reply_markup=get_profile_keyboard())
    else:
        await message.reply("Привет! Пожалуйста, введите ваше имя.")
        await state.set_state(RegistrationStates.waiting_for_name)
    db.close()

@dp.message(RegistrationStates.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(RegistrationStates.waiting_for_age)
    await message.reply("Отлично! Теперь введите ваш возраст (число):")

@dp.message(RegistrationStates.waiting_for_age)
async def process_age(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or not (18 <= int(message.text) <= 100):
        await message.reply("Пожалуйста, введите корректный возраст (от 18 до 100):")
        return
    
    await state.update_data(age=int(message.text))
    await state.set_state(RegistrationStates.waiting_for_about_me)
    await message.reply("Расскажите немного о себе:")

@dp.message(RegistrationStates.waiting_for_about_me)
async def process_about_me(message: types.Message, state: FSMContext):
    await state.update_data(about_me=message.text)
    await state.set_state(RegistrationStates.waiting_for_looking_for)
    await message.reply("Опишите, кого вы хотели бы найти:")

@dp.message(RegistrationStates.waiting_for_looking_for)
async def process_looking_for(message: types.Message, state: FSMContext):
    await state.update_data(looking_for=message.text)
    await state.set_state(RegistrationStates.waiting_for_media)
    await message.reply(
        "Теперь добавьте фотографии или одно видео к вашей анкете.\n"
        "Вы можете отправить несколько фотографий по очереди, "
        "или одно видео. Когда закончите добавлять фото, нажмите /done"
    )

@dp.message(RegistrationStates.waiting_for_media)
async def process_media(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    
    db = SessionLocal()
    user = db.query(TelegramUser).filter(TelegramUser.telegram_id == message.from_user.id).first()
    
    if not user:
        user = TelegramUser(
            telegram_id=message.from_user.id,
            name=user_data['name'],
            age=user_data['age'],
            about_me=user_data['about_me'],
            looking_for=user_data['looking_for']
        )
        db.add(user)
        db.flush()
    
    if message.photo:
        media = UserMedia(
            user_id=user.id,
            file_id=message.photo[-1].file_id,
            media_type=MediaType.PHOTO
        )
        db.add(media)
        db.commit()
        await message.reply(
            "Фото добавлено! Вы можете добавить еще фото или нажать 'Готово ✅'.",
            reply_markup=get_done_keyboard()
        )
    elif message.video:
        if user.media_files:
            await message.reply(
                "Вы уже добавили фото. Продолжайте добавлять фото или нажмите /done для завершения."
            )
            db.close()
            return
            
        media = UserMedia(
            user_id=user.id,
            file_id=message.video.file_id,
            media_type=MediaType.VIDEO
        )
        db.add(media)
        db.commit()
        await state.clear()
        await message.reply(
            "Видео добавлено! Анкета успешно создана.",
            reply_markup=get_profile_keyboard()
        )
    elif message.text == "Готово ✅" or message.text == "/done":
        if not user.media_files:
            await message.reply(
                "Необходимо добавить хотя бы одно фото или видео. Пожалуйста, отправьте медиафайл."
            )
            db.close()
            return
            
        db.commit()
        await state.clear()
        await message.reply(
            "Спасибо за регистрацию! Теперь вы можете просматривать свою анкету.",
            reply_markup=get_profile_keyboard()
        )
    else:
        await message.reply(
            "Пожалуйста, отправьте фото или видео. "
            "Когда закончите добавлять фото, нажмите /done"
        )
    
    db.close()

@dp.message(F.text == "Моя анкета")
async def show_profile(message: types.Message):
    db = SessionLocal()
    user = db.query(TelegramUser).filter(TelegramUser.telegram_id == message.from_user.id).first()
    
    if user:
        # Сначала отправляем вводное сообщение
        await message.reply("Так выглядит твоя анкета:")
        
        # Формируем текст анкеты в новом формате
        profile_text = f"""{user.name}, {user.age} - {user.about_me}

В поисках:
{user.looking_for}"""
        
        # Отправляем медиафайлы с текстом анкеты
        if user.media_files:
            if user.media_files[0].media_type == MediaType.VIDEO:
                await message.answer_video(user.media_files[0].file_id, caption=profile_text)
            else:
                media_group = []
                for i, media in enumerate(user.media_files):
                    if media.media_type == MediaType.PHOTO:
                        input_media = types.InputMediaPhoto(
                            media=media.file_id,
                            caption=profile_text if i == 0 else None
                        )
                        media_group.append(input_media)
                
                await message.answer_media_group(media_group)
        else:
            # Если медиафайлов нет, отправляем т��лько текст
            await message.answer(profile_text)
        
        # Отправляем меню действий
        await message.answer(PROFILE_ACTIONS_MESSAGE, 
                           reply_markup=get_profile_actions_keyboard())
    else:
        await message.reply("Вы еще не зарегистрированы. Используйте /start для регистрации.",
                          reply_markup=get_profile_keyboard())
    db.close()

@dp.message(F.text == "1")
async def refill_profile(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(TelegramUser).filter(TelegramUser.telegram_id == message.from_user.id).first()
    if user:
        await message.reply("Пожалуйста, введите ваше имя заново:", 
                          reply_markup=types.ReplyKeyboardRemove())
        await state.set_state(RegistrationStates.waiting_for_name)
        # Удаляем старые данные
        db.delete(user)
        db.commit()
    db.close()

@dp.message(F.text == "2")
async def delete_profile(message: types.Message):
    db = SessionLocal()
    user = db.query(TelegramUser).filter(TelegramUser.telegram_id == message.from_user.id).first()
    if user:
        db.delete(user)
        db.commit()
        await message.reply("Ваша анкета успешно удалена. Используйте /start для создания новой.",
                          reply_markup=get_profile_keyboard())
    else:
        await message.reply("У вас нет активной анкеты.",
                          reply_markup=get_profile_keyboard())
    db.close()

async def set_commands():
    """Установка команд бота"""
    commands = [types.BotCommand(command="start", description="🚀 Запустить бота")]
    await bot.set_my_commands(commands)
    logger.info("Команды бота установлены")

async def main():
    logger.info("Запуск бота...")
    try:
        await set_commands()
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")