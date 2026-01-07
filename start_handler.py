
import logging
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from utils.state_machine import UserStates
from utils.keyboards import get_grade_keyboard, get_main_menu_keyboard
from config import Config
from modules.user_manager import UserManager

logger = logging.getLogger(__name__)

# Создание роутера
router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, user_manager: UserManager, config: Config):
    
    user_id = message.from_user.id
    
    # Проверка существования пользователя
    if user_manager.user_exists(user_id):
        # Возвращающийся пользователь
        profile = user_manager.get_user(user_id)
        
        await message.answer(
            f"С возвращением, {profile.name}! \n\n"
            f"Твой прогресс:\n"
            f"Уровень: {profile.current_level}\n"
            f"Модуль: {profile.current_module}\n"
            f"Завершено модулей: {len(profile.completed_modules)}\n\n"
            f"Что будем делать?",
            reply_markup=get_main_menu_keyboard()
        )
        await state.set_state(UserStates.MENU)
        logger.info(f"Возвращающийся пользователь: {user_id} ({profile.name})")
    else:
        # Новый пользователь
        await message.answer(
            config.WELCOME_MESSAGE,
            reply_markup=None
        )
        await state.set_state(UserStates.WAITING_NAME)
        logger.info(f"Новый пользователь начал регистрацию: {user_id}")


@router.message(UserStates.WAITING_NAME, F.text)
async def process_name(message: Message, state: FSMContext):
    
    name = message.text.strip()
    
    # Валидация имени
    if len(name) < 2 or len(name) > 50:
        await message.answer(
            "Пожалуйста, введи корректное имя (от 2 до 50 символов):"
        )
        return
    
    # Сохранение имени в состояние
    await state.update_data(name=name)
    
    await message.answer(
        f"Приятно познакомиться, {name}! \n\n"
        f"В каком ты классе?",
        reply_markup=get_grade_keyboard()
    )
    await state.set_state(UserStates.WAITING_GRADE)
    logger.info(f"Пользователь {message.from_user.id} указал имя: {name}")


@router.message(UserStates.WAITING_GRADE, F.text)
async def process_grade(message: Message, state: FSMContext, user_manager: UserManager, config: Config):
    
    text = message.text.strip()
    
    # Извлечение номера класса
    try:
        # Поддержка формата "7 класс" или просто "7"
        grade = int(text.split()[0])
        
        if grade not in config.GRADES:
            await message.answer(
                f"Пожалуйста, выбери класс от 5 до 9:",
                reply_markup=get_grade_keyboard()
            )
            return
    except (ValueError, IndexError):
        await message.answer(
            "Некорректный формат. Выбери класс из меню:",
            reply_markup=get_grade_keyboard()
        )
        return
    
    # Получение данных из состояния
    data = await state.get_data()
    name = data.get('name', '')
    user_id = message.from_user.id
    
    # Создание профиля пользователя
    profile = user_manager.create_user(user_id=user_id, name=name, grade=grade)
    
    if profile:
        await message.answer(
            f"Отлично, {name}!\n\n"
            f"Теперь давай определим твой уровень английского.\n"
            f"Тебе нужно пройти короткий входной тест из {config.PLACEMENT_TEST_QUESTIONS} вопросов.\n\n"
            f"Не волнуйся, это не экзамен! \n"
            f"Просто отвечай честно, и мы подберем оптимальную программу.\n\n"
            f"Готов начать?",
            reply_markup=get_main_menu_keyboard()
        )
        
        # Переход к тесту
        await state.set_state(UserStates.PLACEMENT_TEST)
        logger.info(f"Профиль создан: {user_id} ({name}, {grade} класс)")
    else:
        await message.answer(
            "❌ Произошла ошибка при создании профиля. Попробуй снова командой /start"
        )
        await state.clear()


@router.message(Command("menu"))
@router.message(F.text == "Главное меню")
@router.callback_query(F.data == "main_menu")
async def show_main_menu(event: Message | CallbackQuery, state: FSMContext, user_manager: UserManager):
    
    # Определяем тип события
    if isinstance(event, CallbackQuery):
        message = event.message
        user_id = event.from_user.id
        await event.answer()
    else:
        message = event
        user_id = event.from_user.id
    
    # Получение профиля
    profile = user_manager.get_user(user_id)
    
    if not profile:
        await message.answer(
            "Профиль не найден. Начни с команды /start"
        )
        return
    
    # Формирование сообщения
    menu_text = (
        f"<b>Главное меню</b>\n\n"
        f" Имя: {profile.name}\n"
        f" Класс: {profile.grade}\n"
        f" Уровень: {profile.current_level or 'Не определен'}\n"
        f" Текущий модуль: {profile.current_module}\n"
        f" Завершено: {len(profile.completed_modules)} модулей\n\n"
        f"Выбери действие:"
    )
    
    if isinstance(event, CallbackQuery):
        await message.edit_text(
            menu_text,
            parse_mode="HTML",
            reply_markup=None
        )
    
    await message.answer(
        "Что будем делать?",
        reply_markup=get_main_menu_keyboard()
    )
    
    await state.set_state(UserStates.MENU)


@router.message(Command("help"))
@router.message(F.text == "Помощь")
async def show_help(message: Message):
    
    help_text = """
    <b>Справка</b>

<b>Основные команды:</b>
/start - Начать работу с ботом
/menu - Главное меню
/help - Эта справка

<b>Как пользоваться:</b>

1️ <b>Обучение</b>
Выбери "Продолжить обучение" в меню.
Проходи модули по порядку, выполняя упражнения.

2️ <b>Диалог с AI</b>
Практикуй английский в диалоге на интересные темы.
Выбери тему и начни общаться!

3️ <b>Работа над ошибками</b>
Система автоматически собирает твои ошибки.
Периодически повторяй проблемные темы.

4️ <b>Прогресс</b>
Смотри свою статистику: точность ответов,
завершенные модули, выученные слова.

<b>Особенности:</b>
 Адаптивная сложность - система подстраивается под тебя
 Персональный подход - учет твоих ошибок
 Детальная статистика - отслеживай свой рост
 AI-собеседник - практика в естественном диалоге

Если возникли вопросы - пиши в поддержку!
"""
    
    await message.answer(
        help_text,
        parse_mode="HTML"
    )


@router.message(Command("reset"))
async def cmd_reset(message: Message, state: FSMContext, user_manager: UserManager):
    
    user_id = message.from_user.id
    
    if user_manager.user_exists(user_id):
        user_manager.delete_user(user_id)
        await state.clear()
        
        await message.answer(
            "Твой прогресс сброшен.\n"
            "Начни заново командой /start"
        )
        logger.info(f"Пользователь {user_id} сбросил прогресс")
    else:
        await message.answer(
            "Профиль не найден. Начни с команды /start"
        )