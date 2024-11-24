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

PROFILE_ACTIONS_MESSAGE = """Выберите действие:
1. Заполнить анкету заново
2. Удалить мою анкету"""

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(TelegramUser).filter(TelegramUser.telegram_id == message.from_user.id).first()
    
    # Check if user is in media upload state
    current_state = await state.get_state()
    if current_state == RegistrationStates.waiting_for_media and user and user.media_files:
        # Complete registration if user has uploaded media
        await state.clear()
        await message.reply(
            "Спасибо за регистрацию! Вот ваша анкета:",
            reply_markup=get_profile_keyboard()
        )
        # Show the profile
        profile_text = f"""{user.name}, {user.age} - {user.about_me}

В поисках:
{user.looking_for}"""
        
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
        
        await message.answer(PROFILE_ACTIONS_MESSAGE, 
                           reply_markup=get_profile_actions_keyboard())
    else:
        # Original profile command logic
        if user:
            # Show existing profile
            profile_text = f"""{user.name}, {user.age} - {user.about_me}

В поисках:
{user.looking_for}"""
            
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
                await message.answer(profile_text)
            
            # Only show action buttons for registered users
            await message.answer(PROFILE_ACTIONS_MESSAGE, 
                               reply_markup=get_profile_actions_keyboard())
        else:
            # Start profile creation without any buttons
            await message.reply("Привет! Давайте создадим вашу анкету. Пожалуйста, введите ваше имя.",
                              reply_markup=types.ReplyKeyboardRemove())
            await state.set_state(RegistrationStates.waiting_for_name)
    db.close()

def get_previous_value_keyboard(value: str | int | None = None, text: str | None = None) -> types.ReplyKeyboardMarkup:
    if not value:
        return types.ReplyKeyboardRemove()
    keyboard = [[types.KeyboardButton(text=text or str(value))]]
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

@dp.message(RegistrationStates.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    old_age = user_data.get('old_age')
    
    await state.update_data(name=message.text)
    await state.set_state(RegistrationStates.waiting_for_age)
    await message.reply(
        "Отлично! Теперь введите ваш возраст (число):",
        reply_markup=get_previous_value_keyboard(old_age) if old_age else types.ReplyKeyboardRemove()
    )

@dp.message(RegistrationStates.waiting_for_age)
async def process_age(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or not (18 <= int(message.text) <= 100):
        await message.reply("Пожалуйста, введите корректный возраст (от 18 до 100):")
        return
    
    user_data = await state.get_data()
    old_about_me = user_data.get('old_about_me')
    
    await state.update_data(age=int(message.text))
    await state.set_state(RegistrationStates.waiting_for_about_me)
    await message.reply(
        "Расскажите немного о себе:",
        reply_markup=get_previous_value_keyboard(old_about_me, "Оставить текущий текст") if old_about_me else types.ReplyKeyboardRemove()
    )

@dp.message(RegistrationStates.waiting_for_about_me)
async def process_about_me(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    old_looking_for = user_data.get('old_looking_for')
    
    if message.text == "Оставить текущий текст":
        await state.update_data(about_me=user_data['old_about_me'])
    else:
        await state.update_data(about_me=message.text)
    
    await state.set_state(RegistrationStates.waiting_for_looking_for)
    await message.reply(
        "Опишите, кого вы хотели бы найти:",
        reply_markup=get_previous_value_keyboard(old_looking_for, "Оставить текущий текст") if old_looking_for else types.ReplyKeyboardRemove()
    )

@dp.message(RegistrationStates.waiting_for_looking_for)
async def process_looking_for(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    has_media = user_data.get('has_media')
    
    if message.text == "Оставить текущий текст":
        await state.update_data(looking_for=user_data['old_looking_for'])
    else:
        await state.update_data(looking_for=message.text)
    
    await state.set_state(RegistrationStates.waiting_for_media)
    media_keyboard = None
    if has_media:
        media_keyboard = get_previous_value_keyboard(True, "Оставить текущее")
    else:
        media_keyboard = get_profile_keyboard()
        
    await message.reply(
        "Теперь добавьте фотографии или одно видео к вашей анкете.\n"
        "Вы можете добавить до 3 фотографий или одно видео.\n"
        "Когда закончите добавлять медиафайлы, нажмите кнопку 'Моя анкета'",
        reply_markup=media_keyboard
    )

@dp.message(RegistrationStates.waiting_for_media)
async def process_media(message: types.Message, state: FSMContext):
    if message.text == "Оставить текущее":
        # Complete registration with saved data and media
        user_data = await state.get_data()
        db = SessionLocal()
        
        user = TelegramUser(
            telegram_id=message.from_user.id,
            name=user_data['name'],
            age=user_data['age'],
            about_me=user_data['about_me'],
            looking_for=user_data['looking_for']
        )
        db.add(user)
        db.flush()  # Flush to get user.id

        # Restore media files
        if old_media := user_data.get('old_media'):
            for media_item in old_media:
                media = UserMedia(
                    user_id=user.id,
                    file_id=media_item['file_id'],
                    media_type=media_item['media_type']
                )
                db.add(media)
        
        db.commit()
        await state.clear()
        
        # Show updated profile
        profile_text = f"""{user.name}, {user.age} - {user.about_me}

В поисках:
{user.looking_for}"""

        if old_media:
            if old_media[0]['media_type'] == MediaType.VIDEO:
                await message.answer_video(old_media[0]['file_id'], caption=profile_text)
            else:
                media_group = []
                for i, media in enumerate(old_media):
                    if media['media_type'] == MediaType.PHOTO:
                        input_media = types.InputMediaPhoto(
                            media=media['file_id'],
                            caption=profile_text if i == 0 else None
                        )
                        media_group.append(input_media)
                await message.answer_media_group(media_group)
        
        await message.answer(PROFILE_ACTIONS_MESSAGE, 
                           reply_markup=get_profile_actions_keyboard())
        db.close()
        return

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
        # Check if user already has video
        if any(media.media_type == MediaType.VIDEO for media in user.media_files):
            await message.reply(
                "Вы уже добавили видео. Нельзя добавлять фото к видео."
            )
            db.close()
            return
        
        # Check number of existing photos
        photo_count = sum(1 for media in user.media_files if media.media_type == MediaType.PHOTO)
        if photo_count >= 3:
            await state.clear()
            await message.reply(
                "Спасибо за регистрацию! Используйте кнопку 'Моя анкета' для просмотра анкеты.",
                reply_markup=get_profile_keyboard()
            )
            db.close()
            return
            
        media = UserMedia(
            user_id=user.id,
            file_id=message.photo[-1].file_id,
            media_type=MediaType.PHOTO
        )
        db.add(media)
        db.commit()
        
        photos_left = 3 - (photo_count + 1)
        if photos_left > 0:
            await message.reply(
                f"Фото добавлено! Вы можете добавить ещё {photos_left} фото или нажать 'Моя анкета' для завершения.",
                reply_markup=get_profile_keyboard()
            )
        else:
            # Auto-complete registration when photo limit is reached
            await state.clear()
            await message.reply(
                "Спасибо за регистрацию! Используйте кнопку 'Моя анкета' для просмотра анкеты.",
                reply_markup=get_profile_keyboard()
            )
            
    elif message.video:
        if user.media_files:
            await message.reply(
                "К анкете можно добавить либо до 3 фото, либо 1 видео."
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
    else:
        await message.reply(
            "Пожалуйста, отправьте фото или видео. "
            "Когда закончите добавлять медиафайлы, нажмите 'Моя анкета'",
            reply_markup=get_profile_keyboard()
        )
    
    db.close()

@dp.message(F.text == "Моя анкета")
async def show_profile(message: types.Message, state: FSMContext):
    # Just redirect to /profile command
    await cmd_profile(message, state=state)

@dp.message(F.text == "1")
async def refill_profile(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(TelegramUser).filter(TelegramUser.telegram_id == message.from_user.id).first()
    if user:
        # Store old values in state including media data
        media_data = [
            {"file_id": media.file_id, "media_type": media.media_type}
            for media in user.media_files
        ]
        await state.update_data(
            old_name=user.name,
            old_age=user.age,
            old_about_me=user.about_me,
            old_looking_for=user.looking_for,
            has_media=bool(user.media_files),
            old_media=media_data
        )
        await message.reply(
            "Пожалуйста, введите ваше имя заново:",
            reply_markup=get_previous_value_keyboard(user.name)
        )
        await state.set_state(RegistrationStates.waiting_for_name)
        # Delete old profile
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
        await message.reply(
            "Ваша анкета успешно удалена. Используйте /profile для создания новой.",
            reply_markup=types.ReplyKeyboardRemove()
        )
    else:
        await message.reply(
            "У вас нет активной анкеты. Используйте /profile для создания анкеты.",
            reply_markup=types.ReplyKeyboardRemove()
        )
    db.close()

async def set_commands():
    """Установка команд бота"""
    commands = [types.BotCommand(command="profile", description="📝 Моя анкета")]
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