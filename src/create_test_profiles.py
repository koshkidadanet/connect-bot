import os
from database import SessionLocal
from models import TelegramUser, UserMedia, MediaType

# Get the directory of the current script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def create_test_profiles():
    db = SessionLocal()
    
    # Тестовые данные пользователей
    test_users = [
        {
            "telegram_id": 100001,
            "name": "Райан Гослинг",
            "age": 42,
            "about_me": "Буквально я. Профессионально вожу и ношу куртку со скорпионом. Умею эффектно есть хлопья и молчать.",
            "looking_for": "Ищу ту, которая оценит мои навыки вождения и загадочное молчание.",
            "photos": ["media/unnamed.jpg", "media\загруженное.jpg"]
        },
        # {
        #     "telegram_id": 100002,
        #     "name": "Леонардо Дикаприо",
        #     "age": 48,
        #     "about_me": "Обожаю яхты и экологию. Ищу новые способы спасти мир. Возраст для меня не проблема (до 25).",
        #     "looking_for": "Ищу модель... для спасения окружающей среды, конечно же.",
        #     "photos": ["media/d95b14f8959871fc1faf99952cf8c998.jpg"]
        # },
        # {
        #     "telegram_id": 100003,
        #     "name": "Патрик Бейтман",
        #     "age": 27,
        #     "about_me": "VP в Pierce & Pierce. Хобби: уход за кожей, бизнес-карточки, Huey Lewis and the News.",
        #     "looking_for": "Ищу того, кто оценит мою утреннюю рутину и коллекцию костюмов от Valentino.",
        #     "photos": ["media/b45da3d003682c2091cf48add0419577.jpg"]
        # },
        # {
        #     "telegram_id": 100004,
        #     "name": "Брэдли Купер",
        #     "age": 48,
        #     "about_me": "Актер, режиссер, енот. Умею готовить и петь. Есть друг по имени Джексон Мейн.",
        #     "looking_for": "Ищу талантливую певицу для дуэта. Желательно умеющую говорить 'ха-ха-ха-ха'.",
        #     "photos": ["media/MV5BMjExMzc5MTEyNF5BMl5BanBnXkFtZTcwNzc0NjM2Mg@@._V1_.jpg"]
        # }
    ]
    
    for user_data in test_users:
        user = TelegramUser(
            telegram_id=user_data["telegram_id"],
            name=user_data["name"],
            age=user_data["age"],
            about_me=user_data["about_me"],
            looking_for=user_data["looking_for"]
        )
        db.add(user)
        db.flush()  # Сохраняем пользователя, чтобы получить его ID
        
        for photo in user_data["photos"]:
            media = UserMedia(
                user_id=user.id,
                file_id=None,  # No Telegram file_id for local files
                media_type=MediaType.PHOTO,
            )
            db.add(media)
        
        db.commit()
    
    db.close()

if __name__ == "__main__":
    create_test_profiles()