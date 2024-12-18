import os
import asyncio
import logging

from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from contextlib import contextmanager
from typing import Any
from dotenv import load_dotenv
from database import SessionLocal
from models import TelegramUser, UserMedia, MediaType, RankedProfiles
from data_science import vector_store


MESSAGES = {
    'ask_name': "Привет! Давайте создадим вашу анкету. Пожалуйста, введите ваше имя.",
    'ask_age': "Отлично! Теперь введите ваш возраст (число):",
    'ask_about': "Расскажите немного о себе:",
    'ask_looking': "Опишите, кого вы хотели бы найти:",
    'ask_media': """Теперь добавьте фотографии или одно видео к вашей анкете.
Вы можете добавить до 3 фотографий или одно видео.
Когда закончите добавлять медиафайлы, нажмите кнопку 'Моя анкета'""",
    'profile_actions': """Выберите действие:
1. Смотреть анкеты
2. Заполнить анкету заново
3. Удалить мою анкету""",
    'profile_complete': "Ваша анкета готова!",
    'invalid_age': "Пожалуйста, введите корректный возраст (от 18 до 100):",
    'media_limit': "К анкете можно добавить либо до 3 фото, либо 1 видео.",
    'continue_media': "Пожалуйста, отправьте фото или видео. Когда закончите добавлять медиафайлы, нажмите 'Моя анкета'",
    'video_photo_conflict': "Вы уже добавили видео. Нельзя добавлять фото к видео.",
    'photo_added': "Фото добавлено! Вы можете добавить ещё {} фото или нажать 'Моя анкета' для завершения.",
    'enter_name_again': "Пожалуйста, введите ваше имя заново:",
    'profile_deleted': "Ваша анкета успешно удалена. Используйте /profile для создания новой.",
    'no_profile': "У вас нет активной анкеты. Используйте /profile для создания анкеты.",
    'keep_current': "Оставить текущий текст",
    'bot_start': "Запуск бота...",
    'bot_stop': "Бот остановлен",
    'commands_set': "Команды бота установлены",
    'token_missing': "Не установлена переменная окружения BOT_TOKEN",
    'no_profiles': "К сожалению, пока нет других анкет для просмотра."
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error(MESSAGES['token_missing'])
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class RegistrationStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_age = State()
    waiting_for_about_me = State()
    waiting_for_looking_for = State()
    waiting_for_media = State()
    viewing_profiles = State()

def get_profile_keyboard():
    keyboard = [[types.KeyboardButton(text="Моя анкета")]]
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_profile_actions_keyboard():
    keyboard = [
        [
            types.KeyboardButton(text="1"),
            types.KeyboardButton(text="2"),
            types.KeyboardButton(text="3")
        ]
    ]
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_next_profile_keyboard():
    keyboard = [[types.KeyboardButton(text="Далее")]]
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

@contextmanager
def database_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def format_profile_text(user: TelegramUser) -> str:
    return f"""{user.name}, {user.age} - {user.about_me}

В поисках:
{user.looking_for}"""

async def send_profile_media(message: types.Message, user: TelegramUser, profile_text: str):
    if not user.media_files:
        await message.answer(profile_text, reply_markup=get_next_profile_keyboard())
        return

    # Send media first
    if user.media_files[0].media_type == MediaType.VIDEO:
        await message.answer_video(user.media_files[0].file_id)
        await message.answer(profile_text, reply_markup=get_next_profile_keyboard())
        return

    media_group = [
        types.InputMediaPhoto(media=media.file_id)
        for media in user.media_files
        if media.media_type == MediaType.PHOTO
    ]
    if media_group:
        await message.answer_media_group(media_group)
        await message.answer(profile_text, reply_markup=get_next_profile_keyboard())

async def handle_profile_display(message: types.Message, user: TelegramUser):
    profile_text = format_profile_text(user)
    await send_profile_media(message, user, profile_text)
    await message.answer(
        MESSAGES['profile_actions'],
        reply_markup=get_profile_actions_keyboard()
    )

async def view_next_profile(message: types.Message, state: FSMContext):
    with database_session() as db:
        viewer_id = message.from_user.id
        viewer = db.query(TelegramUser).filter(TelegramUser.telegram_id == viewer_id).first()
        
        data = await state.get_data()
        current_index = data.get('current_profile_index', -1)
        
        # Get ranked profiles
        ranked_profiles = db.query(RankedProfiles).filter(
            RankedProfiles.user_id == viewer.id
        ).order_by(RankedProfiles.rank).all()
        
        if not ranked_profiles:
            await message.answer(
                MESSAGES['no_profiles'],
                reply_markup=get_profile_actions_keyboard()
            )
            await state.clear()
            return
        
        next_index = (current_index + 1) % len(ranked_profiles)
        await state.update_data(current_profile_index=next_index)
        
        # Get the target profile
        ranked_profile = ranked_profiles[next_index]
        profile = ranked_profile.target_user
        profile_text = format_profile_text(profile)
        
        await send_profile_media(message, profile, profile_text)

def get_previous_value_keyboard(value: Any = None, text: str | None = None) -> types.ReplyKeyboardMarkup:
    if not value:
        return types.ReplyKeyboardRemove()
    keyboard = [[types.KeyboardButton(text=text or str(value))]]
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

async def handle_media_upload(message: types.Message, state: FSMContext, user: TelegramUser, db: SessionLocal):
    if message.photo:
        if await handle_photo_upload(message, user, db):
            await state.clear()  # Clear state before showing profile
            await handle_profile_display(message, user)
    elif message.video:
        if await handle_video_upload(message, user, db):
            await state.clear()  # Clear state before showing profile
            await handle_profile_display(message, user)

async def handle_photo_upload(message: types.Message, user: TelegramUser, db: SessionLocal) -> bool:
    if any(media.media_type == MediaType.VIDEO for media in user.media_files):
        await message.reply(MESSAGES['video_photo_conflict'])
        return False

    photo_count = sum(1 for media in user.media_files if media.media_type == MediaType.PHOTO)
    if photo_count >= 3:
        return True

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
            MESSAGES['photo_added'].format(photos_left),
            reply_markup=get_profile_keyboard()
        )
        return False
    return True

async def handle_video_upload(message: types.Message, user: TelegramUser, db: SessionLocal) -> bool:
    if user.media_files:
        await message.reply(MESSAGES['media_limit'])
        return False

    media = UserMedia(
        user_id=user.id,
        file_id=message.video.file_id,
        media_type=MediaType.VIDEO
    )
    db.add(media)
    db.commit()
    return True

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message, state: FSMContext):
    # Don't clear viewing state anymore, just pause it
    current_state = await state.get_state()
    saved_data = None
    
    if current_state == RegistrationStates.viewing_profiles:
        saved_data = await state.get_data()
        await state.clear()
    
    with database_session() as db:
        user = db.query(TelegramUser).filter(TelegramUser.telegram_id == message.from_user.id).first()
        
        current_state = await state.get_state()
        if current_state == RegistrationStates.waiting_for_media:
            if user and user.media_files:
                # Clear saved viewing position when profile is completed
                await state.clear()
                await message.reply(
                    MESSAGES['profile_complete'],
                    reply_markup=get_profile_keyboard()
                )
                await handle_profile_display(message, user)
            else:
                await message.reply(
                    MESSAGES['continue_media'],
                    reply_markup=get_profile_keyboard()
                )
        else:
            if user:
                # Restore saved viewing state if it exists
                if saved_data:
                    await state.set_data(saved_data)
                await handle_profile_display(message, user)
            else:
                await message.reply(MESSAGES['ask_name'], reply_markup=types.ReplyKeyboardRemove())
                await state.set_state(RegistrationStates.waiting_for_name)

@dp.message(RegistrationStates.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    old_age = user_data.get('old_age')
    
    await state.update_data(name=message.text)
    await state.set_state(RegistrationStates.waiting_for_age)
    await message.reply(
        MESSAGES['ask_age'],
        reply_markup=get_previous_value_keyboard(old_age) if old_age else types.ReplyKeyboardRemove()
    )

@dp.message(RegistrationStates.waiting_for_age)
async def process_age(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or not (18 <= int(message.text) <= 100):
        await message.reply(MESSAGES['invalid_age'])
        return
    
    user_data = await state.get_data()
    old_about_me = user_data.get('old_about_me')
    
    await state.update_data(age=int(message.text))
    await state.set_state(RegistrationStates.waiting_for_about_me)
    await message.reply(
        MESSAGES['ask_about'],
        reply_markup=get_previous_value_keyboard(old_about_me, MESSAGES['keep_current']) if old_about_me else types.ReplyKeyboardRemove()
    )

@dp.message(RegistrationStates.waiting_for_about_me)
async def process_about_me(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    old_looking_for = user_data.get('old_looking_for')
    
    if message.text == MESSAGES['keep_current']:
        await state.update_data(about_me=user_data['old_about_me'])
    else:
        await state.update_data(about_me=message.text)
    
    await state.set_state(RegistrationStates.waiting_for_looking_for)
    await message.reply(
        MESSAGES['ask_looking'],
        reply_markup=get_previous_value_keyboard(old_looking_for, MESSAGES['keep_current']) if old_looking_for else types.ReplyKeyboardRemove()
    )

@dp.message(RegistrationStates.waiting_for_looking_for)
async def process_looking_for(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    has_media = user_data.get('has_media')
    
    if message.text == MESSAGES['keep_current']:
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
        MESSAGES['ask_media'],
        reply_markup=media_keyboard
    )

@dp.message(RegistrationStates.waiting_for_media)
async def process_media(message: types.Message, state: FSMContext):
    if message.text == "Оставить текущее":
        user_data = await state.get_data()
        with database_session() as db:
            user = TelegramUser(
                telegram_id=message.from_user.id,
                name=user_data['name'],
                age=user_data['age'],
                about_me=user_data['about_me'],
                looking_for=user_data['looking_for']
            )
            db.add(user)
            db.flush()  # Get user.id before adding media

            # Restore old media files
            if old_media := user_data.get('old_media'):
                for media_item in old_media:
                    media = UserMedia(
                        user_id=user.id,
                        file_id=media_item['file_id'],
                        media_type=media_item['media_type']
                    )
                    db.add(media)
                db.commit()
                
                # Update vector store
                vector_store.handle_user_update(user)
                
                await state.clear()
                await handle_profile_display(message, user)
        return

    if message.text == "Моя анкета":
        with database_session() as db:
            user = db.query(TelegramUser).filter(TelegramUser.telegram_id == message.from_user.id).first()
            if user and user.media_files:
                vector_store.handle_user_update(user)
                await state.clear()
                # Set flag for ranking update
                await state.update_data(needs_ranking_update=True)
                await handle_profile_display(message, user)
            else:
                await message.reply(
                    MESSAGES['continue_media'],
                    reply_markup=get_profile_keyboard()
                )
        return
    
    user_data = await state.get_data()
    
    with database_session() as db:
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
            # Update vector store when new profile is created
            vector_store.handle_user_update(user)
            
        await handle_media_upload(message, state, user, db)

@dp.message(F.text == "Моя анкета")
async def show_profile(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == RegistrationStates.waiting_for_media:
        # If in media upload state, handle through process_media
        await process_media(message, state)
    else:
        # Otherwise use normal profile command
        await cmd_profile(message, state=state)

@dp.message(F.text == "1")
async def start_viewing_profiles(message: types.Message, state: FSMContext):
    with database_session() as db:
        user = db.query(TelegramUser).filter(TelegramUser.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer(MESSAGES['no_profile'])
            return
        
        # Get existing state data
        data = await state.get_data()
        current_index = data.get('current_profile_index', -1)
        needs_ranking_update = data.get('needs_ranking_update', True)
        
        # Update rankings only if needed
        if needs_ranking_update:
            vector_store.update_user_rankings(user)
            current_index = -1  # Reset index when rankings are updated
        
        await state.set_state(RegistrationStates.viewing_profiles)
        await state.update_data(
            current_profile_index=current_index,
            needs_ranking_update=False
        )
        await view_next_profile(message, state)

@dp.message(F.text == "2")
async def refill_profile(message: types.Message, state: FSMContext):
    with database_session() as db:
        user = db.query(TelegramUser).filter(TelegramUser.telegram_id == message.from_user.id).first()
        if user:
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
                old_media=media_data,
                needs_ranking_update=True  # Set flag for ranking update
            )
            await message.reply(
                MESSAGES['enter_name_again'],
                reply_markup=get_previous_value_keyboard(user.name)
            )
            await state.set_state(RegistrationStates.waiting_for_name)
            
            # Delete from vector store before deleting from database
            vector_store.handle_user_update(user, delete=True)
            
            db.delete(user)
            db.commit()

@dp.message(F.text == "3")
async def delete_profile(message: types.Message):
    with database_session() as db:
        user = db.query(TelegramUser).filter(TelegramUser.telegram_id == message.from_user.id).first()
        if user:
            # Delete from vector store before deleting from database
            vector_store.handle_user_update(user, delete=True)
            
            db.delete(user)
            db.commit()
            await message.reply(
                MESSAGES['profile_deleted'],
                reply_markup=types.ReplyKeyboardRemove()
            )
        else:
            await message.reply(
                MESSAGES['no_profile'],
                reply_markup=types.ReplyKeyboardRemove()
            )

@dp.message(RegistrationStates.viewing_profiles, F.text == "Далее")
async def handle_next_profile(message: types.Message, state: FSMContext):
    await view_next_profile(message, state)

async def set_commands():
    commands = [types.BotCommand(command="profile", description="📝 Моя анкета")]
    await bot.set_my_commands(commands)
    logger.info(MESSAGES['commands_set'])

async def main():
    logger.info(MESSAGES['bot_start'])
    try:
        await set_commands()
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info(MESSAGES['bot_stop'])