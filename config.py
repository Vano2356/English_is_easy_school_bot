
import os
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()


class Config:
    

    # Токены и ключи
    BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN')
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', 'YOUR_OPENROUTER_API_KEY')
    
    # Пути к файлам и директориям
    BASE_DIR = Path(__file__).parent
    DATA_DIR = BASE_DIR / 'data'
    USERS_DIR = DATA_DIR / 'users'
    CURRICULUM_PATH = DATA_DIR / 'curriculum.json'
    
    # Создание необходимых директорий
    DATA_DIR.mkdir(exist_ok=True)
    USERS_DIR.mkdir(exist_ok=True)
    
    # Настройки уровней
    LEVELS = ['A1', 'A2', 'B1']
    GRADES = list(range(5, 10))  # 5-9 классы
    
    # Количество модулей на уровень
    MODULES_PER_LEVEL = 12
    EXERCISES_PER_MODULE = 5
    
    # Пороги для адаптации
    ERROR_THRESHOLD = 0.5  # 50% ошибок
    EXCELLENT_THRESHOLD = 0.9  # 90% правильных ответов
    
    # Настройки входного теста
    PLACEMENT_TEST_QUESTIONS = 15
    
    # Настройки retry logic (работа над ошибками)
    RETRY_BUFFER_SIZE = 10  # Максимум ошибок в буфере
    RETRY_EXERCISES_PER_SESSION = 2  # Сколько упражнений на ошибки за сессию
    
    # Настройки AI
    AI_MODEL = 'tngtech/deepseek-r1t2-chimera:free'
    AI_MAX_TOKENS = 1000
    AI_TEMPERATURE = 0.7
    
    # Тексты для пользователя
    WELCOME_MESSAGE = """
Привет! Я твой персональный помощник по английскому языку.

Я помогу тебе:
• Определить твой текущий уровень
• Пройти персонализированный курс
• Практиковаться в диалогах с AI
• Отслеживать прогресс

Давай начнем! Введи свое имя:
"""
    
    MODULE_COMPLETE_MESSAGE = """
Итоги модуля {module_number}/12:
━━━━━━━━━━━━━━━━━━━━
Правильных ответов: {correct}/{total}
Новых слов выучено: {new_words}
Твоя сильная сторона: {strength}
Над чем поработать: {weakness}

Продолжаем?
"""
    
    @classmethod
    def validate(cls):
        """Проверка наличия необходимых настроек"""
        if cls.BOT_TOKEN == 'YOUR_TELEGRAM_BOT_TOKEN':
            raise ValueError("Не установлен BOT_TOKEN в .env файле")
        
        if cls.OPENROUTER_API_KEY == 'YOUR_OPENROUTER_API_KEY':
            raise ValueError("Не установлен OPENROUTER_API_KEY в .env файле")
        
        if not cls.CURRICULUM_PATH.exists():
            raise FileNotFoundError(f"Не найден файл curriculum.json по пути {cls.CURRICULUM_PATH}")
        
        return True
