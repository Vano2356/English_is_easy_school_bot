
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from utils.state_machine import UserStates
from utils.keyboards import get_progress_keyboard, get_main_menu_keyboard
from modules.user_manager import UserManager
from modules.expert_system import ExpertSystem

logger = logging.getLogger(__name__)

# Создание роутера
router = Router()


@router.message(UserStates.MENU, F.text == "Мой прогресс")
async def show_progress(message: Message, state: FSMContext, user_manager: UserManager):
   
    user_id = message.from_user.id
    profile = user_manager.get_user(user_id)
    
    if not profile:
        await message.answer("Профиль не найден. Начни с команды /start")
        return
    
    # Получение статистики
    stats = profile.statistics
    
    # Расчет общей точности
    total_exercises = stats.get('total_exercises', 0)
    correct_answers = stats.get('correct_answers', 0)
    accuracy = (correct_answers / total_exercises * 100) if total_exercises > 0 else 0
    
    # Формирование прогресс-бара для модулей
    total_modules = 12  # Модулей на уровень
    completed = len(profile.completed_modules)
    progress_bar = create_progress_bar(completed, total_modules)
    
    # Формирование текста
    progress_text = (
        f"<b>Твой прогресс</b>\n\n"
        f"<b>Профиль:</b>\n"
        f"  • Имя: {profile.name}\n"
        f"  • Класс: {profile.grade}\n"
        f"  • Уровень: {profile.current_level or 'Не определен'}\n\n"
        f"<b>Обучение:</b>\n"
        f"  • Текущий модуль: {profile.current_module}\n"
        f"  • Завершено модулей: {completed}/12\n"
        f"  {progress_bar}\n\n"
        f"<b>Статистика:</b>\n"
        f"  • Всего упражнений: {total_exercises}\n"
        f"  • Правильных ответов: {correct_answers}\n"
        f"  • Точность: {accuracy:.1f}%\n"
    )
    
    # Добавление прогресс-бара точности
    accuracy_bar = create_accuracy_bar(accuracy)
    progress_text += f"  {accuracy_bar}\n"
    
    # Выученные слова
    new_words = stats.get('new_words_learned', 0)
    if new_words > 0:
        progress_text += f"\n Выучено слов: {new_words}\n"
    
    # Сильные и слабые стороны
    strengths = stats.get('strengths', [])
    weaknesses = stats.get('weaknesses', [])
    
    if strengths:
        progress_text += f"\n <b>Сильные стороны:</b>\n"
        for strength in strengths[:3]:
            progress_text += f"  • {strength}\n"
    
    if weaknesses:
        progress_text += f"\n <b>Над чем работать:</b>\n"
        for weakness in weaknesses[:3]:
            progress_text += f"  • {weakness}\n"
    
    # Последняя активность
    if profile.module_history:
        last_module = profile.module_history[-1]
        progress_text += (
            f"\n <b>Последний завершенный модуль:</b>\n"
            f"  • Модуль {last_module['module_id']}\n"
            f"  • Точность: {last_module.get('score', 0):.0%}\n"
        )
    
    await message.answer(
        progress_text,
        parse_mode="HTML",
        reply_markup=get_progress_keyboard()
    )
    
    await state.set_state(UserStates.VIEW_PROGRESS)


@router.callback_query(F.data == "detailed_stats")
async def show_detailed_stats(callback: CallbackQuery, user_manager: UserManager):
    
    user_id = callback.from_user.id
    profile = user_manager.get_user(user_id)
    
    if not profile:
        await callback.answer(" Профиль не найден")
        return
    
    # Формирование детальной статистики
    stats_text = " <b>Детальная статистика</b>\n\n"
    
    # Статистика по модулям
    if profile.module_history:
        stats_text += "<b>История модулей:</b>\n\n"
        
        for i, module in enumerate(profile.module_history[-5:], 1):  # Последние 5
            module_id = module.get('module_id', 0)
            score = module.get('score', 0)
            
            
            stats_text += f"Модуль {module_id}: {score:.0%}\n"
            
            # Сильные стороны
            strengths = module.get('strengths', [])
            if strengths:
                stats_text += f"   {', '.join(strengths[:2])}\n"
            
            # Слабые стороны
            weaknesses = module.get('weaknesses', [])
            if weaknesses:
                stats_text += f"   {', '.join(weaknesses[:2])}\n"
            
            stats_text += "\n"
    
    # Статистика ошибок
    recent_errors = profile.get_recent_errors(5)
    if recent_errors:
        stats_text += "\n<b>Последние ошибки:</b>\n"
        
        error_types = {}
        for error in recent_errors:
            error_type = error.get('error_type', 'unknown')
            error_types[error_type] = error_types.get(error_type, 0) + 1
        
        for error_type, count in error_types.items():
            stats_text += f"  • {error_type.replace('_', ' ').title()}: {count}\n"
    
    # Общая статистика
    total = profile.statistics['total_exercises']
    correct = profile.statistics['correct_answers']
    incorrect = profile.statistics['incorrect_answers']
    
    stats_text += (
        f"\n<b>Общая статистика:</b>\n"
        f"  Правильно: {correct} ({correct/total*100:.1f}%)\n"
        f"  Неправильно: {incorrect} ({incorrect/total*100:.1f}%)\n"
        f"  Всего: {total}\n"
    )
    
    await callback.answer()
    await callback.message.answer(
        stats_text,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "achievements")
async def show_achievements(callback: CallbackQuery, user_manager: UserManager):
    
    user_id = callback.from_user.id
    profile = user_manager.get_user(user_id)
    
    if not profile:
        await callback.answer("Профиль не найден")
        return
    
    # Определение достижений
    achievements = []
    
    # Достижение: Первый модуль
    if len(profile.completed_modules) >= 1:
        achievements.append(" <b>Первые шаги</b> - Завершил первый модуль")
    
    # Достижение: 5 модулей
    if len(profile.completed_modules) >= 5:
        achievements.append(" <b>Упорный ученик</b> - Завершил 5 модулей")
    
    # Достижение: Завершил уровень
    if len(profile.completed_modules) >= 12:
        achievements.append(" <b>Мастер уровня</b> - Завершил целый уровень")
    
    # Достижение: Высокая точность
    if profile.statistics['total_exercises'] >= 20:
        accuracy = profile.statistics['correct_answers'] / profile.statistics['total_exercises']
        if accuracy >= 0.9:
            achievements.append(" <b>Отличник</b> - Точность выше 90%")
        elif accuracy >= 0.8:
            achievements.append(" <b>Хорошист</b> - Точность выше 80%")
    
    # Достижение: 100 упражнений
    if profile.statistics['total_exercises'] >= 100:
        achievements.append(" <b>Практик</b> - Выполнил 100 упражнений")
    
    # Достижение: 50 выученных слов
    if profile.statistics.get('new_words_learned', 0) >= 50:
        achievements.append(" <b>Словарный запас</b> - Выучил 50+ слов")
    
    # Достижение: Работа над ошибками
    if len(profile.errors) > 0:
        achievements.append(" <b>Работа над собой</b> - Исправляет свои ошибки")
    
    # Формирование текста
    if achievements:
        achievements_text = " <b>Твои достижения:</b>\n\n"
        achievements_text += "\n".join(achievements)
        
        # Прогресс до следующего достижения
        achievements_text += "\n\n<b>Скоро разблокируешь:</b>\n"
        
        if len(profile.completed_modules) < 5:
            remaining = 5 - len(profile.completed_modules)
            achievements_text += f"Упорный ученик ({remaining} модулей до цели)\n"
        
        if profile.statistics['total_exercises'] < 100:
            remaining = 100 - profile.statistics['total_exercises']
            achievements_text += f" Практик ({remaining} упражнений до цели)\n"
    else:
        achievements_text = (
            " <b>Достижения</b>\n\n"
            "Пока у тебя нет достижений, но это только начало!\n\n"
            "Продолжай учиться и открывай новые награды! "
        )
    
    await callback.answer()
    await callback.message.answer(
        achievements_text,
        parse_mode="HTML"
    )


@router.message(UserStates.MENU, F.text == "Работа над ошибками")
async def show_retry_mode(message: Message, state: FSMContext, user_manager: UserManager, expert_system: ExpertSystem):
    
    user_id = message.from_user.id
    profile = user_manager.get_user(user_id)
    
    if not profile:
        await message.answer("Профиль не найден")
        return
    
    # Получение недавних ошибок
    recent_errors = profile.get_recent_errors(10)
    
    if not recent_errors:
        await message.answer(
            "<b>Отлично!</b>\n\n"
            "У тебя пока нет ошибок для повторения.\n"
            "Продолжай в том же духе!",
            parse_mode="HTML"
        )
        return
    
    # Выбор ошибок для повторения
    selected_errors = expert_system.select_retry_exercises(recent_errors, count=3)
    
    # Формирование текста
    retry_text = (
        f"<b>Работа над ошибками</b>\n\n"
        f"Найдено ошибок: {len(recent_errors)}\n"
        f"Выбрано для повторения: {len(selected_errors)}\n\n"
        f"<b>Проблемные темы:</b>\n"
    )
    
    # Группировка ошибок по темам
    topics = {}
    for error in recent_errors:
        topic = error.get('topic', 'unknown')
        topics[topic] = topics.get(topic, 0) + 1
    
    for topic, count in sorted(topics.items(), key=lambda x: x[1], reverse=True)[:3]:
        retry_text += f"  • {topic}: {count} ошибок\n"
    
    retry_text += "\nХочешь повторить эти темы?"
    
    from utils.keyboards import get_retry_keyboard
    
    await message.answer(
        retry_text,
        parse_mode="HTML",
        reply_markup=get_retry_keyboard()
    )
    
    await state.set_state(UserStates.RETRY_MODE)


@router.callback_query(F.data == "view_errors")
async def view_errors_list(callback: CallbackQuery, user_manager: UserManager):
    
    user_id = callback.from_user.id
    profile = user_manager.get_user(user_id)
    
    if not profile:
        await callback.answer(" Профиль не найден")
        return
    
    recent_errors = profile.get_recent_errors(5)
    
    if not recent_errors:
        await callback.answer("Нет ошибок", show_alert=True)
        return
    
    errors_text = "<b>Последние ошибки:</b>\n\n"
    
    for i, error in enumerate(recent_errors, 1):
        errors_text += (
            f"<b>{i}. Модуль {error.get('module', '?')}</b>\n"
            f"Тема: {error.get('topic', 'unknown')}\n"
            f"Твой ответ: <i>{error.get('user_answer', '')}</i>\n"
            f"Правильно: <i>{error.get('correct_answer', '')}</i>\n\n"
        )
    
    await callback.answer()
    await callback.message.answer(
        errors_text,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "start_retry")
async def start_retry_exercises(callback: CallbackQuery, state: FSMContext):
    
    await callback.answer(" Начинаем работу над ошибками!")
    
    # TODO: Реализовать генерацию упражнений на основе ошибок
    await callback.message.answer(
        " Функция в разработке.\n"
        "Скоро ты сможешь повторять ошибки в интерактивном режиме!"
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message, state: FSMContext, user_manager: UserManager):
    
    await state.set_state(UserStates.MENU)
    await show_progress(message, state, user_manager)