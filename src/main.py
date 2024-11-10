from fastapi import FastAPI
from database import engine, Base
from models import User, Item

app = FastAPI()

def create_tables():
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"Error creating tables: {e}")

create_tables()

@app.get("/")
def read_root():
    return {"message": "Welcome to my FastAPI application!"}

@app.get("/items/")
def read_items():
    return [{"item_id": "Foo"}, {"item_id": "Bar"}]

@app.post("/items/")
def create_item(item: dict):
    return {"message": "Item created", "item": item}