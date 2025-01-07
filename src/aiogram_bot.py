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
from models import TelegramUser, UserMedia, MediaType, RankedProfiles, Likes
from data_science import vector_store


MESSAGES = {
    'ask_name': "Привет! Давайте создадим вашу анкету. Пожалуйста, введите ваше имя.",
    'ask_age': "Отлично! Теперь введите ваш возраст (число):",
    'ask_about': "Расскажите немного о себе:",
    'ask_looking': "Опишите, кого вы хотели бы найти:",
    'ask_media': """Теперь добавьте до 3 фотографии или одно видео к вашей анкете.
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
    'no_profiles': "К сожалению, пока нет других анкет для просмотра.",
    'profile_not_viewed': "Вы еще не долистали до анкеты под номером {}!",
    'unsupported_media': "Извините, этот формат файла не поддерживается. Пожалуйста, отправьте сжатое фото или видео.",
    'photo_too_large': "Фото слишком большое. Пожалуйста, отправьте фото размером до 3 МБ.",
    'video_too_large': "Видео слишком большое. Пожалуйста, отправьте видео размером до 30 МБ.",
    'video_too_long': "Видео слишком длинное. Пожалуйста, отправьте видео длительностью до 15 секунд.",
    'welcome': """Привет! Я ConnectBot — ваш маленький помощник в мире знакомств 💙

✨ Как я могу помочь?
1️⃣ Сначала вы создадите свою анкету с помощью команды /profile.
2️⃣ Я найду тех, кто идеально подойдёт под ваше описание, и покажу их анкеты.
3️⃣ Пропустили кого-то? Не беда! Просто используйте команды вроде /1, /2 и откройте нужную анкету снова.

Давайте начнем! 🚀""",
    'photo_limit_reached': "Достигнут лимит фотографий.",
    'photos_done': "Фото добавлено! Нажмите 'Моя анкета' для завершения.",
    'already_liked': "Вы уже поставили лайк этой анкете.",
    'new_like': "Ура, ты кому-то понравился. Количество лайков - {}. Показать, кто это?",
    'no_more_likes': "На этом пока все! Вы можете посмотреть анкеты других пользователей.",
    'show_likes': "Показать",
    'mutual_like': "Отлично! Надеюсь хорошо проведете время ;) Начинай общаться с 👉 {}" # {} will be replaced with profile link
}

# Add constants for media restrictions
MAX_PHOTO_SIZE = 3 * 1024 * 1024  # 3 MB in bytes
MAX_VIDEO_SIZE = 30 * 1024 * 1024  # 30 MB in bytes
MAX_VIDEO_DURATION = 15  # seconds

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
    viewing_likes = State()  # Add new state for viewing likes

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
    keyboard = [[
        types.KeyboardButton(text="❤️"),
        types.KeyboardButton(text="👎")
    ]]
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_start_keyboard():
    keyboard = [[types.KeyboardButton(text="Моя анкета")]]
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_show_likes_keyboard():
    keyboard = [[types.KeyboardButton(text=MESSAGES['show_likes'])]]
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_after_likes_keyboard():
    keyboard = [
        [
            types.KeyboardButton(text="1"),
            types.KeyboardButton(text="2")
        ]
    ]
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_view_profiles_keyboard():
    keyboard = [[types.KeyboardButton(text="Смотреть анкеты")]]
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_next_mutual_like_keyboard():
    keyboard = [[types.KeyboardButton(text="❤️")]]
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

async def send_profile_media(message: types.Message, user: TelegramUser, profile_text: str, rank: int | None = None):
    # Update rank_text to include username if available
    rank_text = f"/{rank}" if rank is not None else ""
    
    if not user.media_files:
        await message.answer(f"{rank_text}\n{profile_text}", reply_markup=get_next_profile_keyboard())
        return

    # Send media with rank
    if user.media_files[0].media_type == MediaType.VIDEO:
        await message.answer_video(
            user.media_files[0].file_id,
            caption=rank_text
        )
        await message.answer(profile_text, reply_markup=get_next_profile_keyboard())
        return

    media_group = []
    for i, media in enumerate(user.media_files):
        if media.media_type == MediaType.PHOTO:
            caption = rank_text if i == 0 else None
            media_group.append(
                types.InputMediaPhoto(
                    media=media.file_id,
                    caption=caption
                )
            )
    
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
        skip_to_index = data.get('skip_to_index')
        max_viewed_index = data.get('max_viewed_index', -1)
        
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

        if skip_to_index is not None:
            next_index = skip_to_index
            await state.update_data(skip_to_index=None)
        else:
            next_index = (current_index + 1) % len(ranked_profiles)
        
        # Update max viewed index
        max_viewed_index = max(max_viewed_index, next_index)
        await state.update_data(
            current_profile_index=next_index,
            max_viewed_index=max_viewed_index
        )
        
        # Get the target profile
        ranked_profile = ranked_profiles[next_index]
        profile = ranked_profile.target_user
        profile_text = format_profile_text(profile)
        
        await send_profile_media(message, profile, profile_text, rank=next_index + 1)

@dp.message(lambda message: message.text and message.text.startswith('/') and message.text[1:].isdigit())
async def handle_rank_command(message: types.Message, state: FSMContext):
    rank = int(message.text[1:]) - 1  # Convert to 0-based index
    
    # Check if user has viewed this profile
    data = await state.get_data()
    max_viewed_index = data.get('max_viewed_index', -1)
    
    if rank > max_viewed_index:
        await message.answer(MESSAGES['profile_not_viewed'].format(rank + 1))
        return
    
    with database_session() as db:
        viewer_id = message.from_user.id
        viewer = db.query(TelegramUser).filter(TelegramUser.telegram_id == viewer_id).first()
        
        if not viewer:
            await message.answer(MESSAGES['no_profile'])
            return
        
        # Get ranked profiles
        ranked_profiles = db.query(RankedProfiles).filter(
            RankedProfiles.user_id == viewer.id
        ).order_by(RankedProfiles.rank).all()
        
        if not ranked_profiles or rank >= len(ranked_profiles):
            await message.answer(MESSAGES['no_profiles'])
            return
        
        # Set viewing state and show profile
        await state.set_state(RegistrationStates.viewing_profiles)
        await state.update_data(current_profile_index=rank)
        
        profile = ranked_profiles[rank].target_user
        profile_text = format_profile_text(profile)
        await send_profile_media(message, profile, profile_text, rank=rank + 1)

def get_previous_value_keyboard(value: Any = None, text: str | None = None) -> types.ReplyKeyboardMarkup:
    if not value:
        return types.ReplyKeyboardRemove()
    keyboard = [[types.KeyboardButton(text=text or str(value))]]
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

async def handle_media_upload(message: types.Message, state: FSMContext, user: TelegramUser, db: SessionLocal):
    # Check if we've already reached the photo limit in this session
    state_data = await state.get_data()
    if state_data.get('photo_limit_reached'):
        await message.reply(MESSAGES['photo_limit_reached'])
        return

    # Check if message contains supported media type
    if not (message.photo or message.video):
        await message.reply(MESSAGES['unsupported_media'])
        return

    if message.photo:
        photo_limit_reached = await handle_photo_upload(message, user, db)
        if photo_limit_reached:
            # Just mark that we've reached the limit in this session
            await state.update_data(photo_limit_reached=True)
    elif message.video:
        if await handle_video_upload(message, user, db):
            await state.clear()  # Clear state before showing profile
            await handle_profile_display(message, user)

async def handle_photo_upload(message: types.Message, user: TelegramUser, db: SessionLocal) -> bool:
    # First check if photo limit is reached
    photo_count = sum(1 for media in user.media_files if media.media_type == MediaType.PHOTO)
    if photo_count >= 3:
        await message.reply(
            MESSAGES['photo_limit_reached'],
            reply_markup=get_profile_keyboard()
        )
        return True

    # Check photo size
    photo = message.photo[-1]
    if photo.file_size > MAX_PHOTO_SIZE:
        await message.reply(MESSAGES['photo_too_large'])
        return False

    if any(media.media_type == MediaType.VIDEO for media in user.media_files):
        await message.reply(MESSAGES['video_photo_conflict'])
        return False

    media = UserMedia(
        user_id=user.id,
        file_id=message.photo[-1].file_id,
        media_type=MediaType.PHOTO
    )
    db.add(media)
    db.commit()

    photos_left = 2 - photo_count  # Now we subtract from 2 since we just added one
    if photos_left > 0:
        await message.reply(
            MESSAGES['photo_added'].format(photos_left),
            reply_markup=get_profile_keyboard()
        )
        return False
    else:
        await message.reply(
            MESSAGES['photos_done'],
            reply_markup=get_profile_keyboard()
        )
        return True

async def handle_video_upload(message: types.Message, user: TelegramUser, db: SessionLocal) -> bool:
    # First check if user already has photos
    if any(media.media_type == MediaType.PHOTO for media in user.media_files):
        await message.reply(MESSAGES['video_photo_conflict'])
        return False

    # Then check for existing media
    if user.media_files:
        await message.reply(MESSAGES['media_limit'])
        return False

    # Finally check video parameters
    if message.video.file_size > MAX_VIDEO_SIZE:
        await message.reply(MESSAGES['video_too_large'])
        return False
    
    if message.video.duration > MAX_VIDEO_DURATION:
        await message.reply(MESSAGES['video_too_long'])
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
                await state.clear()
                await message.reply(
                    MESSAGES['profile_complete'],
                    reply_markup=get_profile_keyboard()
                )
                await handle_profile_display(message, user)
            else:
                # Reset photo limit flag when starting new media upload session
                await state.update_data(photo_limit_reached=False)
                await message.reply(
                    MESSAGES['continue_media'],
                    reply_markup=get_profile_keyboard()
                )
        else:
            if user:
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
                username=message.from_user.username,  # Add username
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
                
                # Add user to vector store after restoring media
                vector_store.update_user_vectors(user)
                await state.clear()
                await handle_profile_display(message, user)
        return

    if message.text == "Моя анкета":
        with database_session() as db:
            user = db.query(TelegramUser).filter(TelegramUser.telegram_id == message.from_user.id).first()
            if user and user.media_files:
                # Add user to vector store when completing profile
                vector_store.update_user_vectors(user)
                # Update rankings for the user
                vector_store.update_user_rankings(user)
                await state.clear()
                await handle_profile_display(message, user)
            else:
                await message.reply(
                    MESSAGES['continue_media'],
                    reply_markup=get_profile_keyboard()
                )
        return
    
    # Handle unsupported media types
    if not (message.photo or message.video or message.text):
        await message.reply(MESSAGES['unsupported_media'])
        return
    
    user_data = await state.get_data()
    
    with database_session() as db:
        user = db.query(TelegramUser).filter(TelegramUser.telegram_id == message.from_user.id).first()
        
        if not user:
            user = TelegramUser(
                telegram_id=message.from_user.id,
                username=message.from_user.username,  # Add username
                name=user_data['name'],
                age=user_data['age'],
                about_me=user_data['about_me'],
                looking_for=user_data['looking_for']
            )
            db.add(user)
            db.flush()
            db.refresh(user)  # Ensure we have the user's ID
            
        if message.photo or message.video:
            completed = await handle_media_upload(message, state, user, db)
            if completed:
                # Add new profile to vector store when media upload is complete
                vector_store.update_user_vectors(user)
        else:
            await message.reply(
                MESSAGES['continue_media'],
                reply_markup=get_profile_keyboard()
            )

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
        
        # Always update rankings when starting to view profiles
        vector_store.update_user_rankings(user)
        
        await state.set_state(RegistrationStates.viewing_profiles)
        await state.update_data(current_profile_index=-1)  # Reset index when starting to view
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

@dp.message(RegistrationStates.viewing_profiles, F.text == "👎")
async def handle_next_profile(message: types.Message, state: FSMContext):
    await view_next_profile(message, state)

async def notify_about_like(bot: Bot, user_id: int, likes_count: int):
    """Notify user about new like"""
    try:
        await bot.send_message(
            user_id,
            MESSAGES['new_like'].format(likes_count),
            reply_markup=get_show_likes_keyboard()
        )
    except Exception as e:
        logger.error(f"Failed to send like notification: {e}")

async def get_unviewed_likes(db: SessionLocal, user_id: int):
    """Get unviewed likes for user"""
    return db.query(Likes).filter(
        Likes.to_user_id == user_id,
        Likes.viewed == False
    ).all()

async def create_like(db: SessionLocal, from_user_id: int, to_user_id: int) -> bool:
    """Create a new like record. Returns True if created, False if already exists"""
    # Check if like already exists
    existing_like = db.query(Likes).filter(
        Likes.from_user_id == from_user_id,
        Likes.to_user_id == to_user_id
    ).first()
    
    if existing_like:
        return False
        
    like = Likes(
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        is_mutual=False,
        viewed=False
    )
    db.add(like)
    db.commit()

    # Get target user's telegram_id and count of unviewed likes
    target_user = db.query(TelegramUser).filter(TelegramUser.id == to_user_id).first()
    unviewed_likes_count = db.query(Likes).filter(
        Likes.to_user_id == to_user_id,
        Likes.viewed == False
    ).count()

    # Notify user about new like
    if target_user:
        await notify_about_like(bot, target_user.telegram_id, unviewed_likes_count)
    
    return True

@dp.message(F.text == MESSAGES['show_likes'])
async def start_viewing_likes(message: types.Message, state: FSMContext):
    with database_session() as db:
        viewer = db.query(TelegramUser).filter(TelegramUser.telegram_id == message.from_user.id).first()
        if not viewer:
            return
            
        # Get all unviewed likes once and store them in state
        unviewed_likes = await get_unviewed_likes(db, viewer.id)
        if not unviewed_likes:
            await message.answer(MESSAGES['no_more_likes'], reply_markup=get_view_profiles_keyboard())
            return
            
        await state.set_state(RegistrationStates.viewing_likes)
        # Store likes in state data
        await state.update_data(
            current_like_index=-1,
            unviewed_likes_ids=[like.id for like in unviewed_likes]
        )
        await view_next_like(message, state)

async def view_next_like(message: types.Message, state: FSMContext):
    """Show next profile that liked the user"""
    with database_session() as db:
        viewer = db.query(TelegramUser).filter(TelegramUser.telegram_id == message.from_user.id).first()
        if not viewer:
            return
            
        data = await state.get_data()
        current_like_index = data.get('current_like_index', -1)
        unviewed_likes_ids = data.get('unviewed_likes_ids', [])
        
        if not unviewed_likes_ids or current_like_index >= len(unviewed_likes_ids) - 1:
            # Mark all likes as viewed
            db.query(Likes).filter(
                Likes.id.in_(unviewed_likes_ids)
            ).update({Likes.viewed: True})
            db.commit()
            
            # Show end message
            await message.answer(MESSAGES['no_more_likes'], reply_markup=get_view_profiles_keyboard())
            await state.clear()
            return

        # Show next like
        next_index = current_like_index + 1
        await state.update_data(current_like_index=next_index)
        
        # Get the specific like by ID
        like = db.query(Likes).filter(Likes.id == unviewed_likes_ids[next_index]).first()
        if not like:
            return

        # Check if there's already a mutual like
        existing_mutual = db.query(Likes).filter(
            Likes.from_user_id == viewer.id,
            Likes.to_user_id == like.from_user_id,
            Likes.is_mutual == True
        ).first()
            
        from_user = db.query(TelegramUser).filter(TelegramUser.id == like.from_user_id).first()
        if from_user:
            profile_text = format_profile_text(from_user)
            # Choose keyboard based on mutual status
            keyboard = get_next_mutual_like_keyboard() if (existing_mutual or like.is_mutual) else get_next_profile_keyboard()
            
            # Send profile with appropriate keyboard
            if not from_user.media_files:
                await message.answer(profile_text, reply_markup=keyboard)
                return

            if from_user.media_files[0].media_type == MediaType.VIDEO:
                await message.answer_video(from_user.media_files[0].file_id)
                await message.answer(profile_text, reply_markup=keyboard)
                return

            media_group = [
                types.InputMediaPhoto(media=media.file_id)
                for media in from_user.media_files if media.media_type == MediaType.PHOTO
            ]
            if media_group:
                await message.answer_media_group(media_group)
                await message.answer(profile_text, reply_markup=keyboard)

@dp.message(RegistrationStates.viewing_likes, F.text == "❤️")
async def handle_like_in_likes_view(message: types.Message, state: FSMContext):
    with database_session() as db:
        viewer = db.query(TelegramUser).filter(TelegramUser.telegram_id == message.from_user.id).first()
        if not viewer:
            return

        data = await state.get_data()
        current_like_index = data.get('current_like_index', -1)
        unviewed_likes_ids = data.get('unviewed_likes_ids', [])
        
        if not unviewed_likes_ids or current_like_index >= len(unviewed_likes_ids):
            return

        # Get the specific like by ID
        like = db.query(Likes).filter(Likes.id == unviewed_likes_ids[current_like_index]).first()
        if not like:
            return

        from_user = db.query(TelegramUser).filter(TelegramUser.id == like.from_user_id).first()
        if not from_user:
            return

        # Check for existing mutual like
        existing_mutual = db.query(Likes).filter(
            Likes.from_user_id == viewer.id,
            Likes.to_user_id == from_user.id,
            Likes.is_mutual == True
        ).first()

        profile_link = get_user_profile_link(from_user)
        if existing_mutual or like.is_mutual:
            # If already mutual, just show the mutual like message
            await message.answer(
                MESSAGES['mutual_like'].format(profile_link),
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        else:
            # Handle new mutual like
            like.is_mutual = True
            
            # Create reciprocal like
            reciprocal_like = Likes(
                from_user_id=viewer.id,
                to_user_id=like.from_user_id,
                is_mutual=True,
                viewed=False
            )
            db.add(reciprocal_like)
            db.commit()

            await message.answer(
                MESSAGES['mutual_like'].format(profile_link),
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            
            # Count unviewed likes for the other user
            unviewed_likes_count = db.query(Likes).filter(
                Likes.to_user_id == from_user.id,
                Likes.viewed == False
            ).count()
            
            # Notify the other user about the mutual like
            await notify_about_like(bot, from_user.telegram_id, unviewed_likes_count)

        # Show next profile or finish
        await view_next_like(message, state)

@dp.message(F.text == "1")
async def handle_view_profiles(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == RegistrationStates.viewing_likes:
        await start_viewing_profiles(message, state)
    else:
        # Handle existing "1" button functionality
        await start_viewing_profiles(message, state)

@dp.message(F.text == "2")
async def handle_my_profile(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == RegistrationStates.viewing_likes:
        await cmd_profile(message, state)
    else:
        # Handle existing "2" button functionality
        await refill_profile(message, state)

@dp.message(RegistrationStates.viewing_profiles, F.text == "❤️")
async def handle_like_profile(message: types.Message, state: FSMContext):
    with database_session() as db:
        # Get current viewer
        viewer = db.query(TelegramUser).filter(TelegramUser.telegram_id == message.from_user.id).first()
        if not viewer:
            await message.answer(MESSAGES['no_profile'])
            return

        # Get current profile being viewed
        data = await state.get_data()
        current_index = data.get('current_profile_index', -1)
        
        ranked_profiles = db.query(RankedProfiles).filter(
            RankedProfiles.user_id == viewer.id
        ).order_by(RankedProfiles.rank).all()
        
        if not ranked_profiles or current_index >= len(ranked_profiles):
            await message.answer(MESSAGES['no_profiles'])
            return
            
        # Get the target profile and try to create like
        target_profile = ranked_profiles[current_index].target_user
        if not await create_like(db, viewer.id, target_profile.id):
            await message.answer(MESSAGES['already_liked'])
        
        # Show next profile
        await view_next_profile(message, state)

@dp.message(F.text == "Смотреть анкеты")
async def handle_view_profiles_button(message: types.Message, state: FSMContext):
    await start_viewing_profiles(message, state)

def get_user_profile_link(user: TelegramUser) -> str:
    """Generate HTML-formatted Telegram profile link using user's display name"""
    if user.username:
        # If user has a Telegram username, create a link with @username
        return f'<a href="https://t.me/{user.username}">{user.name}</a>'
    # Otherwise use tg://user?id= format
    return f'<a href="tg://user?id={user.telegram_id}">{user.name}</a>'

async def set_commands():
    commands = [
        types.BotCommand(command="profile", description="📝 Моя анкета")
    ]
    await bot.set_my_commands(commands)
    logger.info(MESSAGES['commands_set'])

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        MESSAGES['welcome'],
        reply_markup=get_start_keyboard()
    )

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