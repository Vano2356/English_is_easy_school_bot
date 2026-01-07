"""
Handler для входного адаптивного теста (Placement Test)
Определяет начальный уровень ученика
ИСПРАВЛЕННАЯ ВЕРСИЯ - без ошибок с зависимостями
"""
import logging
import sys
from pathlib import Path
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from utils.state_machine import UserStates, TestContext
from utils.keyboards import get_test_options_keyboard, get_main_menu_keyboard
from utils import keyboards
from config import Config
from modules.user_manager import UserManager
from modules.expert_system import ExpertSystem

# Добавляем корневую папку в путь для импорта static_placement_test
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Импорт статического теста
try:
    from static_placement_test import get_placement_test, calculate_level, get_level_description
    logger = logging.getLogger(__name__)
    logger.info("✅ static_placement_test успешно импортирован")
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.error(f"❌ Ошибка импорта static_placement_test: {e}")
    logger.error(f"Путь к проекту: {project_root}")
    logger.error(f"Содержимое папки: {list(project_root.glob('*.py'))}")
    raise

# Создание роутера
router = Router()


@router.message(UserStates.PLACEMENT_TEST, F.text == "📚 Продолжить обучение")
@router.message(UserStates.PLACEMENT_TEST, F.text.lower().in_(["да", "начать", "готов", "го", "yes"]))
async def start_placement_test(message: Message, state: FSMContext):
    """
    Начало входного теста - используем статический тест
    """
    user_id = message.from_user.id
    
    await message.answer("⏳ Готовлю тест для тебя...")
    
    try:
        # Получаем статический тест (без AI!)
        questions = get_placement_test()
        
        if not questions:
            await message.answer(
                "❌ Ошибка при создании теста. Попробуй позже или напиши /start"
            )
            return
        
        # Создание контекста теста
        test_ctx = TestContext()
        test_ctx.questions = questions
        test_ctx.current_question_index = 0
        
        # Сохранение контекста в state
        await state.update_data(test_context=test_ctx)
        
        # Показ первого вопроса
        await show_question(message, test_ctx, state)
        
        await state.set_state(UserStates.PLACEMENT_TEST_QUESTION)
        logger.info(f"Пользователь {user_id} начал входной тест ({len(questions)} вопросов)")
    
    except Exception as e:
        logger.error(f"Ошибка при запуске теста для {user_id}: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при создании теста.\n"
            "Попробуй позже командой /start"
        )


async def show_question(message: Message, test_ctx: TestContext, state: FSMContext):
    """
    Отображение текущего вопроса теста
    """
    question = test_ctx.get_current_question()
    
    if not question:
        # Тест завершен
        await complete_test_final(message, test_ctx, state)
        return
    
    question_num = test_ctx.current_question_index + 1
    total_questions = len(test_ctx.questions)
    
    # Формирование текста вопроса с прогресс-баром
    progress_percent = (question_num / total_questions) * 100
    progress_bar = "█" * int(progress_percent / 10) + "░" * (10 - int(progress_percent / 10))
    
    question_text = (
        f"📝 <b>Вопрос {question_num}/{total_questions}</b>\n"
        f"[{progress_bar}] {progress_percent:.0f}%\n\n"
        f"<b>{question['question']}</b>\n\n"
        f"Выбери правильный ответ:"
    )
    
    # Создание клавиатуры с вариантами (A, B, C, D)
    keyboard = get_test_options_keyboard(question['options'])
    
    await message.answer(
        question_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )


@router.callback_query(UserStates.PLACEMENT_TEST_QUESTION, F.data.startswith("test_answer_"))
async def process_test_answer(callback: CallbackQuery, state: FSMContext):
    """
    Обработка ответа на вопрос теста
    """
    user_id = callback.from_user.id
    
    # Получение контекста теста
    data = await state.get_data()
    test_ctx = data.get('test_context')
    
    if not test_ctx:
        await callback.answer("❌ Ошибка: контекст теста потерян")
        return
    
    # Извлечение ответа пользователя (A, B, C, D)
    user_answer = callback.data.split("_")[-1]
    
    # Получение текущего вопроса
    question = test_ctx.get_current_question()
    correct_answer = question['correct_answer']
    
    # Проверка ответа (сравниваем буквы!)
    is_correct = user_answer.upper() == correct_answer.upper()
    
    # Сохранение ответа
    test_ctx.add_answer(question, user_answer, is_correct)
    
    # Уведомление пользователя
    if is_correct:
        await callback.answer("✅ Правильно!", show_alert=False)
    else:
        correct_text = question.get('correct_text', correct_answer)
        await callback.answer(
            f"❌ Неверно. Правильно: {correct_answer}) {correct_text}",
            show_alert=False
        )
    
    # Переход к следующему вопросу
    test_ctx.next_question()
    await state.update_data(test_context=test_ctx)
    
    # Показ следующего вопроса или завершение
    await show_question(callback.message, test_ctx, state)
    
    logger.debug(f"Пользователь {user_id} ответил: {user_answer} ({'✓' if is_correct else '✗'})")


async def complete_test_final(message: Message, test_ctx: TestContext, state: FSMContext):
    """
    Завершение теста - создаем зависимости внутри функции
    """
    user_id = message.chat.id
    
    try:
        # Расчет результата
        result = test_ctx.calculate_score()
        
        # Определение уровня через нашу функцию
        level = calculate_level(result['correct'], result['total'])
        
        # Получаем описание уровня
        level_info = get_level_description(level)
        
        # Создаем зависимости ЗДЕСЬ
        config = Config()
        user_manager = UserManager(config.USERS_DIR)
        expert_system = ExpertSystem(config.CURRICULUM_PATH)
        
        # Обновление профиля пользователя
        user_manager.update_user(
            user_id,
            start_level=level,
            current_level=level,
            current_module=1
        )
        
        # Получение информации о модулях
        first_module = expert_system.get_module(level, 1)
        all_modules = expert_system.get_all_modules(level)
        
        # ЗАЩИТА: Проверяем что all_modules не пустой
        if not all_modules:
            all_modules = []
            logger.warning(f"Модули для уровня {level} не найдены!")
        
        # Формирование красивого сообщения
        result_text = (
            f"🎊 <b>Поздравляем! Тест завершен!</b>\n\n"
            f"📊 <b>Твои результаты:</b>\n"
            f"{'━' * 25}\n"
            f"✅ Правильных ответов: <b>{result['correct']}</b> из {result['total']}\n"
            f"📈 Точность: <b>{result['score']:.0%}</b>\n"
            f"{'━' * 25}\n\n"
            f"{level_info['emoji']} <b>Твой уровень: {level}</b>\n"
            f"<i>{level_info['title']}</i>\n\n"
            f"{level_info['description']}\n\n"
            f"🎯 <b>Что тебя ждет:</b>\n"
        )
        
        for i, goal in enumerate(level_info['goals'], 1):
            result_text += f"  {i}. {goal}\n"
        
        # План обучения (только если есть модули)
        if all_modules:
            result_text += f"\n\n📚 <b>План обучения ({level}):</b>\n"
            result_text += f"{'━' * 25}\n"
            
            # Показываем первые 5 модулей
            for i, module in enumerate(all_modules[:5], 1):
                difficulty_emoji = {
                    "easy": "🟢",
                    "medium": "🟡",
                    "hard": "🔴"
                }.get(module.get('difficulty', 'medium'), "🟡")
                
                result_text += f"{i}. {difficulty_emoji} {module['title']}\n"
            
            if len(all_modules) > 5:
                result_text += f"... и еще {len(all_modules) - 5} модулей!\n"
            
            result_text += f"\n<b>Всего модулей:</b> {len(all_modules)}\n"
        else:
            result_text += f"\n\n📚 <b>План обучения готовится...</b>\n"
        
        # Информация о первом модуле
        if first_module:
            result_text += (
                f"\n🚀 <b>Начнем с первого модуля:</b>\n"
                f"📖 <i>{first_module['title']}</i>\n\n"
                f"<b>Основные темы:</b>\n"
            )
            
            for topic in first_module.get('topics', [])[:3]:
                result_text += f"  • {topic.replace('_', ' ').title()}\n"
            
            result_text += f"\n💪 Готов начать обучение?"
        else:
            result_text += f"\n\n💪 Готов начать обучение?"
        
        await message.answer(
            result_text,
            parse_mode="HTML",
            reply_markup=keyboards.get_test_complete_keyboard()
        )
        
        # Переход в главное меню
        await state.set_state(UserStates.MENU)
        
        logger.info(
            f"Пользователь {user_id} завершил тест: "
            f"{result['correct']}/{result['total']} ({result['score']:.0%}), "
            f"уровень: {level}"
        )
    
    except Exception as e:
        logger.error(f"Ошибка при завершении теста для {user_id}: {e}", exc_info=True)
        
        # Минимальный вывод в случае ошибки
        await message.answer(
            f"🎊 <b>Тест завершен!</b>\n\n"
            f"✅ Правильных ответов: <b>{result.get('correct', 0)}</b> из {result.get('total', 15)}\n"
            f"📊 Твой уровень определен!\n\n"
            f"Нажми 'Продолжить обучение' чтобы начать! 💪",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )
        
        await state.set_state(UserStates.MENU)


# Обработчики кнопок после теста
@router.callback_query(F.data == "start_first_module")
async def start_first_module_from_test(callback: CallbackQuery, state: FSMContext):
    """Начать обучение сразу после теста"""
    await callback.answer()
    
    # Отправляем главное меню
    await callback.message.answer(
        "Отлично! Переходим к обучению 🚀",
        reply_markup=get_main_menu_keyboard()
    )
    
    await state.set_state(UserStates.MENU)
    
    # Эмулируем нажатие "Продолжить обучение"
    fake_message = callback.message
    fake_message.text = "📚 Продолжить обучение"
    fake_message.from_user = callback.from_user
    
    # Импортируем handler обучения
    from handlers.lesson_handler import start_learning
    
    # Создаем зависимости
    config = Config()
    user_manager = UserManager(config.USERS_DIR)
    expert_system = ExpertSystem(config.CURRICULUM_PATH)
    
    await start_learning(fake_message, state, user_manager, expert_system)


@router.callback_query(F.data == "view_all_modules")
async def view_all_modules_from_test(callback: CallbackQuery):
    """Показать все модули уровня"""
    user_id = callback.from_user.id
    
    try:
        # Создаем зависимости
        config = Config()
        user_manager = UserManager(config.USERS_DIR)
        expert_system = ExpertSystem(config.CURRICULUM_PATH)
        
        profile = user_manager.get_user(user_id)
        
        if not profile:
            await callback.answer("Ошибка: профиль не найден")
            return
        
        level = profile.current_level
        all_modules = expert_system.get_all_modules(level)
        
        # Проверка что модули есть
        if not all_modules:
            await callback.answer("Модули для этого уровня пока не загружены", show_alert=True)
            return
        
        modules_text = (
            f"📚 <b>Все модули уровня {level}</b>\n"
            f"{'━' * 30}\n\n"
        )
        
        for i, module in enumerate(all_modules, 1):
            difficulty_emoji = {
                "easy": "🟢",
                "medium": "🟡",
                "hard": "🔴"
            }.get(module.get('difficulty', 'medium'), "🟡")
            
            modules_text += f"<b>{i}. {difficulty_emoji} {module['title']}</b>\n"
            
            if i <= 3:
                topics = ', '.join(module.get('topics', [])[:2])
                if topics:
                    modules_text += f"   <i>{topics}</i>\n"
            
            modules_text += "\n"
        
        modules_text += (
            f"💡 <i>Модули проходятся последовательно.</i>\n"
            f"<i>Система автоматически подстраивает сложность!</i>"
        )
        
        await callback.answer()
        await callback.message.answer(
            modules_text,
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(f"Ошибка при показе модулей: {e}", exc_info=True)
        await callback.answer("Произошла ошибка при загрузке модулей", show_alert=True)


@router.callback_query(F.data == "view_profile")
async def view_profile_from_test(callback: CallbackQuery):
    """Показать профиль пользователя"""
    user_id = callback.from_user.id
    
    # Создаем зависимости
    config = Config()
    user_manager = UserManager(config.USERS_DIR)
    
    profile = user_manager.get_user(user_id)
    
    if not profile:
        await callback.answer("Ошибка: профиль не найден")
        return
    
    profile_text = (
        f"👤 <b>Твой профиль</b>\n"
        f"{'━' * 25}\n\n"
        f"📝 <b>Имя:</b> {profile.name}\n"
        f"🎓 <b>Класс:</b> {profile.grade}\n"
        f"📊 <b>Уровень:</b> {profile.current_level}\n"
        f"📖 <b>Текущий модуль:</b> {profile.current_module}\n"
        f"✅ <b>Завершено модулей:</b> {len(profile.completed_modules)}\n\n"
        f"📈 <b>Статистика теста:</b>\n"
        f"  • Правильных ответов: {profile.statistics['correct_answers']}\n"
        f"  • Точность: {profile.statistics['correct_answers']/max(profile.statistics['total_exercises'], 1):.0%}\n\n"
        f"🎯 <b>Готов к обучению!</b>"
    )
    
    await callback.answer()
    await callback.message.answer(
        profile_text,
        parse_mode="HTML"
    )