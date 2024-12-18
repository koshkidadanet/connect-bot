from fastapi import FastAPI
from database import engine, Base
from models import TelegramUser
from sqlalchemy import text

app = FastAPI()

def manage_tables(drop_existing=False):
    """
    Управление таблицами базы данных.
    drop_existing: если True, удаляет существующие таблицы перед созданием новых
    """
    try:
        if drop_existing:
            with engine.connect() as connection:
                # Удаляем старые таблицы
                connection.execute(text("DROP TABLE IF EXISTS ranked_profiles CASCADE"))
                connection.execute(text("DROP TABLE IF EXISTS user_media CASCADE"))
                connection.execute(text("DROP TABLE IF EXISTS telegram_users CASCADE"))
                connection.commit()
                print("Old tables dropped successfully")
        
        # Создаем таблицы из моделей
        Base.metadata.create_all(bind=engine)
        print("Tables created successfully")
    except Exception as e:
        print(f"Error during table operations: {e}")

# Раскомментируйте следующую строку для пересоздания таблиц
manage_tables(drop_existing=True)

@app.get("/")
def read_root():
    return {"message": "Welcome to my FastAPI application!"}

@app.get("/items/")
def read_items():
    return [{"item_id": "Foo"}, {"item_id": "Bar"}]

@app.post("/items/")
def create_item(item: dict):
    return {"message": "Item created", "item": item}