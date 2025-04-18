import asyncio
import logging
import os
import sys
import msvcrt
import atexit
from bot import main as bot_main
from admin_panel.app import app
from hypercorn.asyncio import serve
from hypercorn.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
async def run_web():
    config = Config()
    config.bind = ["0.0.0.0:8000"]
    config.use_reloader = False
    await serve(app, config)


async def main():
    lock_file = obtain_lock()
    atexit.register(lambda: release_lock(lock_file))
    bot_task = asyncio.create_task(bot_main())  # bot_main должен запускать polling!
    web_task = asyncio.create_task(run_web())
    logger.info("Starting bot and web server...")
    await asyncio.gather(bot_task, web_task)
    
def obtain_lock():
    try:
        lock_file = open("bot.lock", "w")
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    except IOError:
        print("Другой экземпляр бота уже запущен")
        sys.exit(1)
    return lock_file

def release_lock(lock_file):
    try:
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        lock_file.close()
        os.unlink("bot.lock")
    except:
        pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user.")

