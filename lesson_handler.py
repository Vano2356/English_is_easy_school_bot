
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from utils.state_machine import UserStates, ExerciseContext
from utils.keyboards import (
    get_start_module_keyboard,
    get_exercise_keyboard,
    get_answer_feedback_keyboard,
    get_module_complete_keyboard
)
from modules.user_manager import UserManager
from modules.expert_system import ExpertSystem
from modules.ai_integration import AIIntegration

logger = logging.getLogger(__name__)

# Создание роутера
router = Router()


@router.message(UserStates.MENU, F.text == "Продолжить обучение")
async def start_learning(message: Message, state: FSMContext, user_manager: UserManager, expert_system: ExpertSystem):
    
    user_id = message.from_user.id
    profile = user_manager.get_user(user_id)
    
    if not profile:
        await message.answer("Профиль не найден. Начни с команды /start")
        return
    
    # Проверка, пройден ли входной тест
    if not profile.current_level:
        await message.answer(
            "Сначала нужно пройти входной тест для определения уровня!\n"
            "Нажми кнопку ниже, чтобы начать."
        )
        await state.set_state(UserStates.PLACEMENT_TEST)
        return
    
    # Получение текущего модуля
    current_module = expert_system.get_module(profile.current_level, profile.current_module)
    
    if not current_module:
        # Модули закончились - переход на следующий уровень или завершение курса
        await handle_level_completion(message, profile, state, user_manager, expert_system)
        return
    
    # Отображение информации о модуле
    module_text = (
        f"<b>Модуль {profile.current_module}/12</b>\n\n"
        f"<b>{current_module['title']}</b>\n\n"
        f"Темы:\n"
    )
    
    for topic in current_module['topics'][:3]:
        module_text += f"  {topic.replace('_', ' ').title()}\n"
    
    module_text += f"\n Сложность: {current_module['difficulty']}\n"
    
    await message.answer(
        module_text,
        parse_mode="HTML",
        reply_markup=get_start_module_keyboard(profile.current_module)
    )
    
    await state.set_state(UserStates.MODULE_START)


@router.callback_query(F.data.startswith("start_module_"))
async def begin_module(callback: CallbackQuery, state: FSMContext, user_manager: UserManager, expert_system: ExpertSystem, ai_integration: AIIntegration):
    
    user_id = callback.from_user.id
    profile = user_manager.get_user(user_id)
    
    await callback.answer()
    await callback.message.edit_text(
        "Готовлю упражнения специально для тебя...\n"
        "Это может занять 10-15 секунд."
    )
    
    try:
        # Анализ предыдущего модуля (если есть)
        module_analysis = {"difficulty_adjustment": "maintain"}
        if profile.module_history:
            last_module_stats = profile.module_history[-1]
            # Простой анализ на основе последнего модуля
            if last_module_stats.get('score', 0.8) < 0.5:
                module_analysis = {"difficulty_adjustment": "decrease", "weak_topics": []}
            elif last_module_stats.get('score', 0.8) > 0.9:
                module_analysis = {"difficulty_adjustment": "increase", "weak_topics": []}
        
        # Получение конфигурации следующего модуля
        module_config = expert_system.get_next_module_config(profile, module_analysis)
        
        # Генерация промпта для AI
        ai_prompt = expert_system.generate_ai_prompt_for_module(module_config, profile)
        
        # Генерация упражнений через AI
        exercises = await ai_integration.generate_exercises(ai_prompt)
        
        if not exercises:
            await callback.message.answer(
                " Не удалось создать упражнения. Попробуй позже."
            )
            return
        
        # Создание контекста упражнений
        exercise_ctx = ExerciseContext()
        exercise_ctx.current_module_id = profile.current_module
        exercise_ctx.current_module_config = module_config
        exercise_ctx.exercises = exercises
        exercise_ctx.current_exercise_index = 0
        
        # Сохранение контекста
        await state.update_data(exercise_context=exercise_ctx)
        
        # Показ первого упражнения
        await show_exercise(callback.message, exercise_ctx, state)
        
        await state.set_state(UserStates.WAITING_ANSWER)
        logger.info(f"Пользователь {user_id} начал модуль {profile.current_module} ({len(exercises)} упражнений)")
    
    except Exception as e:
        logger.error(f"Ошибка при начале модуля для {user_id}: {e}", exc_info=True)
        await callback.message.answer(
            "Произошла ошибка при создании упражнений.\n"
            "Попробуй позже или обратись в поддержку."
        )


async def show_exercise(message: Message, exercise_ctx: ExerciseContext, state: FSMContext):
    
    exercise = exercise_ctx.get_current_exercise()
    
    if not exercise:
        # Модуль завершен
        await complete_module(message, exercise_ctx, state)
        return
    
    exercise_num = exercise_ctx.current_exercise_index + 1
    total_exercises = len(exercise_ctx.exercises)
    
    # Формирование текста упражнения
    exercise_text = (
        f"<b>Упражнение {exercise_num}/{total_exercises}</b>\n\n"
        f"{exercise.get('question', 'Вопрос отсутствует')}\n\n"
    )
    
    # Добавление подсказки, если есть
    if exercise.get('hint'):
        exercise_text += f" <i>Подсказка: {exercise['hint']}</i>\n\n"
    
    exercise_text += "Введи свой ответ:"
    
    await message.answer(
        exercise_text,
        parse_mode="HTML",
        reply_markup=get_exercise_keyboard()
    )


@router.message(UserStates.WAITING_ANSWER, F.text)
async def process_answer(message: Message, state: FSMContext, user_manager: UserManager, ai_integration: AIIntegration):
    
    user_id = message.from_user.id
    user_answer = message.text.strip()
    
    # Получение контекста
    data = await state.get_data()
    exercise_ctx = data.get('exercise_context')
    
    if not exercise_ctx:
        await message.answer(" Ошибка: контекст упражнения потерян")
        return
    
    exercise = exercise_ctx.get_current_exercise()
    
    if not exercise:
        await message.answer(" Упражнение не найдено")
        return
    
    # Показываем "печатает..."
    await message.bot.send_chat_action(message.chat.id, "typing")
    
    try:
        # Проверка ответа через AI
        check_result = await ai_integration.check_answer(exercise, user_answer)
        
        is_correct = check_result.get('is_correct', False)
        feedback = check_result.get('feedback', 'Ответ проверен')
        score = check_result.get('score', 3)
        
        # Сохранение ответа в контекст
        exercise_ctx.add_answer(exercise, user_answer, is_correct, check_result)
        
        # Обновление профиля пользователя
        profile = user_manager.get_user(user_id)
        profile.statistics['total_exercises'] += 1
        
        if is_correct:
            profile.statistics['correct_answers'] += 1
            
            feedback_text = "Правильно!"
        else:
            profile.statistics['incorrect_answers'] += 1
            
            feedback_text = "Неверно"
            
            # Добавление ошибки в профиль для retry logic
            profile.add_error({
                "error_type": check_result.get('error_type', 'unknown'),
                "topic": exercise.get('type', 'unknown'),
                "user_answer": user_answer,
                "correct_answer": check_result.get('correct_answer', ''),
                "explanation": feedback
            })
        
        user_manager.save_user(profile)
        
        # Формирование ответа
        response_text = (
            f"{feedback_emoji} <b>{feedback_text}</b>\n\n"
            f"{feedback}\n\n"
        )
        
        if not is_correct and check_result.get('correct_answer'):
            response_text += f"<i>Правильный ответ: {check_result['correct_answer']}</i>\n\n"
        
        response_text += f"Оценка: {'*' * score}/*****"
        
        await message.answer(
            response_text,
            parse_mode="HTML",
            reply_markup=get_answer_feedback_keyboard(is_correct)
        )
        
        # Сохранение обновленного контекста
        await state.update_data(exercise_context=exercise_ctx)
        
        logger.info(f"Пользователь {user_id} ответил: {'+' if is_correct else '-'}, score: {score}")
    
    except Exception as e:
        logger.error(f"Ошибка при проверке ответа для {user_id}: {e}", exc_info=True)
        await message.answer(
            "Произошла ошибка при проверке ответа. Попробуй еще раз."
        )


@router.callback_query(F.data == "next_exercise")
async def next_exercise(callback: CallbackQuery, state: FSMContext):
    
    await callback.answer()
    
    # Получение контекста
    data = await state.get_data()
    exercise_ctx = data.get('exercise_context')
    
    if not exercise_ctx:
        await callback.message.answer(" Ошибка: контекст потерян")
        return
    
    # Переход к следующему
    exercise_ctx.next_exercise()
    await state.update_data(exercise_context=exercise_ctx)
    
    # Показ следующего упражнения или завершение
    await show_exercise(callback.message, exercise_ctx, state)


@router.callback_query(F.data == "hint")
async def show_hint(callback: CallbackQuery, state: FSMContext):
    
    data = await state.get_data()
    exercise_ctx = data.get('exercise_context')
    
    if not exercise_ctx:
        await callback.answer("Ошибка")
        return
    
    exercise = exercise_ctx.get_current_exercise()
    hint = exercise.get('hint', 'Подсказка недоступна')
    
    await callback.answer(f"{hint}", show_alert=True)


@router.callback_query(F.data == "skip")
async def skip_exercise(callback: CallbackQuery, state: FSMContext):
    
    await callback.answer("Упражнение пропущено")
    
    # Переход к следующему
    data = await state.get_data()
    exercise_ctx = data.get('exercise_context')
    
    if exercise_ctx:
        exercise_ctx.next_exercise()
        await state.update_data(exercise_context=exercise_ctx)
        await show_exercise(callback.message, exercise_ctx, state)


@router.callback_query(F.data == "explain_error")
async def explain_error(callback: CallbackQuery, state: FSMContext, ai_integration: AIIntegration):
    
    await callback.answer()
    await callback.message.bot.send_chat_action(callback.message.chat.id, "typing")
    
    # Получение последней ошибки
    data = await state.get_data()
    exercise_ctx = data.get('exercise_context')
    
    if not exercise_ctx or not exercise_ctx.errors:
        await callback.message.answer("Нет ошибок для объяснения")
        return
    
    last_error = exercise_ctx.errors[-1]
    error_data = last_error['feedback']
    
    # Генерация объяснения через AI
    explanation = await ai_integration.explain_error(error_data)
    
    await callback.message.answer(
        f"<b>Объяснение:</b>\n\n{explanation}",
        parse_mode="HTML"
    )


async def complete_module(message: Message, exercise_ctx: ExerciseContext, state: FSMContext, user_manager: UserManager = None, expert_system: ExpertSystem = None, ai_integration: AIIntegration = None):
    
    # user_manager, expert_system и ai_integration будут автоматически переданы middleware
    
    user_id = message.chat.id
    profile = user_manager.get_user(user_id)
    
    # Получение статистики модуля
    stats = exercise_ctx.get_module_statistics()
    
    # Анализ результатов через экспертную систему
    analysis = expert_system.analyze_module_performance(
        stats['correct'],
        stats['total'],
        [error['feedback'] for error in exercise_ctx.errors]
    )
    
    # Получение информации о модуле
    module_info = expert_system.get_module(profile.current_level, exercise_ctx.current_module_id)
    
    # Обновление профиля
    profile.complete_module(
        exercise_ctx.current_module_id,
        stats['accuracy'],
        analysis.get('strengths', []),
        analysis.get('weak_topics', [])
    )
    
    # Переход к следующему модулю
    profile.current_module += 1
    user_manager.save_user(profile)
    
    # Генерация персонального отчета через AI
    summary = await ai_integration.generate_module_summary(profile, module_info, analysis)
    
    # Формирование сообщения
    completion_text = (
        f"<b>Модуль {exercise_ctx.current_module_id} завершен!</b>\n\n"
        f"<b>Статистика:</b>\n"
        f"Правильных ответов: {stats['correct']}/{stats['total']}\n"
        f"Точность: {stats['accuracy']:.0%}\n"
        f"Статус: {analysis['status']}\n\n"
        f"<b>Сильные стороны:</b> {', '.join(analysis.get('strengths', ['Все хорошо!']))}\n"
    )
    
    if analysis.get('weak_topics'):
        completion_text += f"<b>Над чем поработать:</b> {', '.join(analysis['weak_topics'])}\n"
    
    completion_text += f"\n {summary}"
    
    await message.answer(
        completion_text,
        parse_mode="HTML",
        reply_markup=get_module_complete_keyboard()
    )
    
    await state.set_state(UserStates.MODULE_SUMMARY)
    logger.info(f"Пользователь {user_id} завершил модуль {exercise_ctx.current_module_id} ({stats['accuracy']:.0%})")


@router.callback_query(F.data == "next_module")
async def start_next_module(callback: CallbackQuery, state: FSMContext, user_manager: UserManager, expert_system: ExpertSystem):
    
    await callback.answer()
    await callback.message.answer("Отлично! Переходим к следующему модулю...")
    await state.set_state(UserStates.MENU)
    
    # Эмуляция нажатия кнопки "Продолжить обучение"
    fake_message = callback.message
    fake_message.text = " Продолжить обучение"
    await start_learning(fake_message, state, user_manager, expert_system)


async def handle_level_completion(message: Message, profile, state: FSMContext, user_manager: UserManager, expert_system: ExpertSystem):
    
    level_order = ["A1", "A2", "B1"]
    
    try:
        current_index = level_order.index(profile.current_level)
        if current_index < len(level_order) - 1:
            next_level = level_order[current_index + 1]
            
            profile.current_level = next_level
            profile.current_module = 1
            user_manager.save_user(profile)
            
            await message.answer(
                f"<b>Поздравляем!</b>\n\n"
                f"Ты завершил уровень <b>{profile.current_level}</b>!\n\n"
                f"Переходим на уровень <b>{next_level}</b>!\n\n"
                f"Готов к новым вызовам?",
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"<b>НЕВЕРОЯТНО!</b>\n\n"
                f"Ты завершил весь курс английского языка!\n\n"
                f" Пройдено уровней: A1, A2, B1\n"
                f" Завершено модулей: {len(profile.completed_modules)}\n"
                f" Правильных ответов: {profile.statistics['correct_answers']}\n\n"
                f"Ты молодец!",
                parse_mode="HTML"
            )
    except ValueError:
        logger.error(f"Неизвестный уровень: {profile.current_level}")


@router.callback_query(F.data == "module_info")
async def show_module_info(callback: CallbackQuery, user_manager: UserManager, expert_system: ExpertSystem):
    """
    Показ детальной информации о модуле
    """
    user_id = callback.from_user.id
    profile = user_manager.get_user(user_id)
    
    module = expert_system.get_module(profile.current_level, profile.current_module)
    
    if not module:
        await callback.answer("Информация недоступна")
        return
    
    info_text = (
        f"<b>{module['title']}</b>\n\n"
        f"<b>Темы:</b>\n"
    )
    
    for topic in module['topics']:
        info_text += f"  {topic.replace('_', ' ').title()}\n"
    
    info_text += f"\n<b>Ключевая грамматика:</b>\n"
    for grammar in module['key_grammar'][:5]:
        info_text += f"  {grammar.replace('_', ' ').title()}\n"
    
    info_text += f"\n<b>Ключевая лексика:</b>\n"
    for word in module['key_vocabulary'][:5]:
        info_text += f"  {word.replace('_', ' ')}\n"
    
    await callback.answer()
    await callback.message.answer(
        info_text,
        parse_mode="HTML"
    )