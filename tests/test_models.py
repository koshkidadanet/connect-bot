import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, TelegramUser, UserMedia, MediaType, RankedProfiles, Likes

# Use SQLite in-memory database for testing
TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture
def db_session():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)

def test_create_user(db_session):
    user = TelegramUser(
        telegram_id=123456789,
        username="testuser",
        name="Test User",
        age=25,
        about_me="Test about me",
        looking_for="Test looking for"
    )
    db_session.add(user)
    db_session.commit()
    
    saved_user = db_session.query(TelegramUser).first()
    assert saved_user.telegram_id == 123456789
    assert saved_user.username == "testuser"
    assert saved_user.age == 25

def test_user_media_relationship(db_session):
    user = TelegramUser(
        telegram_id=123456789,
        name="Test User",
        age=25,
        about_me="Test",
        looking_for="Test"
    )
    db_session.add(user)
    db_session.commit()
    
    media = UserMedia(
        user_id=user.id,
        file_id="test_file_id",
        media_type=MediaType.PHOTO
    )
    db_session.add(media)
    db_session.commit()
    
    assert len(user.media_files) == 1
    assert user.media_files[0].file_id == "test_file_id"

def test_likes_relationship(db_session):
    user1 = TelegramUser(telegram_id=1, name="User1", age=25, about_me="Test", looking_for="Test")
    user2 = TelegramUser(telegram_id=2, name="User2", age=26, about_me="Test", looking_for="Test")
    
    db_session.add_all([user1, user2])
    db_session.commit()
    
    like = Likes(
        from_user_id=user1.id,
        to_user_id=user2.id,
        is_mutual=False
    )
    db_session.add(like)
    db_session.commit()
    
    assert len(user1.likes_given) == 1
    assert len(user2.likes_received) == 1
