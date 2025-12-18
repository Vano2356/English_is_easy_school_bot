"""
Главный файл телеграм-бота для изучения английского языка
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import Config
from handlers import start_handler, test_handler, lesson_handler, progress_handler
from modules.expert_system import ExpertSystem
from modules.ai_integration import AIIntegration
from modules.user_manager import UserManager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """
    Основная функция запуска бота
    """
    # Инициализация конфигурации
    config = Config()
    
    logger.info("Запуск бота...")
    
    # Создание бота и диспетчера
    bot = Bot(token=config.BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Инициализация основных компонентов системы
    logger.info("Инициализация компонентов системы...")
    
    # Экспертная система (управляет логикой адаптации)
    expert_system = ExpertSystem(curriculum_path=config.CURRICULUM_PATH)
    
    # Интеграция с Claude AI
    ai_integration = AIIntegration(api_key=config.ANTHROPIC_API_KEY)
    
    # Менеджер пользователей
    user_manager = UserManager(users_dir=config.USERS_DIR)
    
    # Передаем компоненты в bot data для доступа из хендлеров
    dp['expert_system'] = expert_system
    dp['ai_integration'] = ai_integration
    dp['user_manager'] = user_manager
    dp['config'] = config
    
    # Регистрация handlers (роутеров)
    logger.info("Регистрация обработчиков...")
    dp.include_router(start_handler.router)
    dp.include_router(test_handler.router)
    dp.include_router(lesson_handler.router)
    dp.include_router(progress_handler.router)
    
    # Запуск бота
    try:
        logger.info("Бот успешно запущен и готов к работе!")
        logger.info(f"Загружено модулей: {len(expert_system.curriculum)}")
        
        # Удаление вебхуков (если были)
        await bot.delete_webhook(drop_pending_updates=True)
        
        # Запуск polling
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}", exc_info=True)
    finally:
        logger.info("Остановка бота...")
        await bot.session.close()


if __name__ == '__main__':
    """
    Точка входа в приложение
    """
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}", exc_info=True)
