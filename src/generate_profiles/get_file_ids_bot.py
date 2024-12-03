from aiogram import Bot, Dispatcher, types, F
import os
import asyncio
import json
from datetime import datetime

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    print("Please set BOT_TOKEN environment variable")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

file_ids = {
    'photos': [],
    'videos': []
}

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    file_id = message.photo[-1].file_id
    file_ids['photos'].append(file_id)
    print(f"Received photo file_id: {file_id}")
    await save_file_ids()

@dp.message(F.video)
async def handle_video(message: types.Message):
    file_id = message.video.file_id
    file_ids['videos'].append(file_id)
    print(f"Received video file_id: {file_id}")
    await save_file_ids()

async def save_file_ids():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f'file_ids_{timestamp}.json'
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(file_ids, f, indent=2, ensure_ascii=False)
    print(f"File IDs saved to {filename}")

async def main():
    print("Bot started. Send photos and videos to get their file_ids...")
    print("Press Ctrl+C to stop")
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        print("\nBot stopped")

if __name__ == "__main__":
    asyncio.run(main())