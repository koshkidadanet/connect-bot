import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram import Bot, Dispatcher
from aiogram.types import Message, User, Chat
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram_bot import (
    cmd_start,
    cmd_profile,
    process_name,
    process_age,
    process_about_me,
    process_looking_for,
    RegistrationStates
)

# Mock bot token for testing
TEST_BOT_TOKEN = "test_token"

@pytest.fixture
def bot():
    return Bot(token=TEST_BOT_TOKEN)

@pytest.fixture
def dp():
    storage = MemoryStorage()
    return Dispatcher(storage=storage)

@pytest.fixture
def user():
    return User(
        id=123456789,
        is_bot=False,
        first_name="Test",
        username="testuser"
    )

@pytest.fixture
def chat():
    return Chat(
        id=123456789,
        type="private"
    )

@pytest.fixture
async def message_mock():
    message = AsyncMock()
    message.answer = AsyncMock()
    message.reply = AsyncMock()
    message.from_user = MagicMock()
    message.from_user.id = 123456789
    message.from_user.username = "testuser"
    message.text = "test message"
    return message

@pytest.fixture
async def state_mock():
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.finish = AsyncMock()
    return state

@pytest.mark.asyncio
async def test_start_command(message_mock):
    await cmd_start(message_mock)
    message_mock.answer.assert_called_once()
    assert "ConnectBot" in message_mock.answer.call_args[0][0]

@pytest.mark.asyncio
@patch('aiogram_bot.database_session')
async def test_profile_command(db_mock, message_mock, state_mock):
    db_session = AsyncMock()
    db_session.query.return_value.filter.return_value.first.return_value = None
    db_mock.return_value.__enter__.return_value = db_session
    
    await cmd_profile(message_mock, state_mock)
    message_mock.reply.assert_called_once()
    assert "введите ваше имя" in message_mock.reply.call_args[0][0].lower()

@pytest.mark.asyncio
async def test_registration_flow(message_mock, state_mock):
    # Test name input
    message_mock.text = "John Doe"
    await process_name(message_mock, state_mock)
    assert "возраст" in message_mock.reply.call_args[0][0].lower()
    
    # Test age input
    message_mock.text = "25"
    await process_age(message_mock, state_mock)
    assert "о себе" in message_mock.reply.call_args[0][0].lower()
    
    # Test about_me input
    message_mock.text = "I am a test user"
    await process_about_me(message_mock, state_mock)
    assert "в поисках" in message_mock.reply.call_args[0][0].lower()

@pytest.mark.asyncio
async def test_invalid_age(message_mock, state_mock):
    message_mock.text = "invalid"
    await process_age(message_mock, state_mock)
    assert "корректный возраст" in message_mock.reply.call_args[0][0].lower()
