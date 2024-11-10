from aiogram import Bot, Dispatcher, types
import os
import asyncio

# Initialize bot and dispatcher
bot = Bot(token=os.environ['BOT_TOKEN'])
dp = Dispatcher()

@dp.message()
async def echo_message(message: types.Message):
    await message.reply(message.text)

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
        asyncio.run(main())
    except KeyboardInterrupt:
        pass