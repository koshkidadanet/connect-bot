import sys
import os

parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)


from database import SessionLocal, engine
from models import Base, TelegramUser, UserMedia, MediaType

# Test data
test_profiles = [
    {
        "telegram_id": 100001,
        "name": "Райан Гослинг",
        "age": 42,
        "about_me": "Буквально я. Профессионально вожу и ношу куртку со скорпионом. Умею эффектно есть хлопья и молчать.",
        "looking_for": "Ищу ту, которая оценит мои навыки вождения и загадочное молчание.",
        "media": [
            {"file_id": "AgACAgIAAxkBAAIXn2dMFP5m6yL3WYS0yesMBTEOW2siAAJC8zEbDMVoSmSHTZ1EtwEbAQADAgADeAADNgQ", "type": MediaType.PHOTO},
            {"file_id": "AgACAgIAAxkBAAIVJ2dL21niZ-6Rvr6UEIOp7MR0MnHwAAK26TEbDMVgSvMn0H9PBQHhAQADAgADeAADNgQ", "type": MediaType.PHOTO}
        ]
    },
    {
        "telegram_id": 100003,
        "name": "Патрик Бейтман",
        "age": 27,
        "about_me": "VP в Pierce & Pierce. Хобби: уход за кожей, бизнес-карточки, Huey Lewis and the News.",
        "looking_for": "Ищу того, кто оценит мою утреннюю рутину и коллекцию костюмов от Valentino.",
        "media": [
            {"file_id": "AgACAgIAAxkBAAIVKGdL21lVAe1j5SSf7prebt0anA8NAAK36TEbDMVgSobcfEi8U1XVAQADAgADeQADNgQ", "type": MediaType.PHOTO}
        ]
    },
    {
        "telegram_id": 100002,
        "name": "Леонардо Дикаприо",
        "age": 48,
        "about_me": "Обожаю яхты и экологию. Ищу новые способы спасти мир. Возраст для меня не проблема (до 25).",
        "looking_for": "Ищу модель... для спасения окружающей среды, конечно же.",
        "media": [
            {"file_id": "AgACAgIAAxkBAAIXomdMFR0EAarBWz4Xd6tVbrO4JO-4AAJD8zEbDMVoSkFph-kQdkdpAQADAgADeQADNgQ", "type": MediaType.PHOTO},
        ]
    }
]

def create_test_profiles():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    try:
        # Clear existing test profiles
        for profile in test_profiles:
            existing = db.query(TelegramUser).filter(
                TelegramUser.telegram_id == profile["telegram_id"]
            ).first()
            if existing:
                db.delete(existing)
        
        # Create new profiles
        for profile in test_profiles:
            user = TelegramUser(
                telegram_id=profile["telegram_id"],
                name=profile["name"],
                age=profile["age"],
                about_me=profile["about_me"],
                looking_for=profile["looking_for"]
            )
            db.add(user)
            db.flush()  # Get user.id
            
            # Add media files
            for media_item in profile["media"]:
                media = UserMedia(
                    user_id=user.id,
                    file_id=media_item["file_id"],
                    media_type=media_item["type"]
                )
                db.add(media)
        
        db.commit()
        print("Test profiles created successfully!")
        
    except Exception as e:
        db.rollback()
        print(f"Error creating test profiles: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    create_test_profiles()