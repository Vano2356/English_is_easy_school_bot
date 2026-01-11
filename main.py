from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from config import BOT_TOKEN, OPENROUTER_API_KEY
from core import UserManager, load_curriculum, determine_level_by_score
from ai import AIIntegration

user_manager = UserManager()
curriculum = load_curriculum()
ai = AIIntegration(OPENROUTER_API_KEY)

user_states = {}


def get_main_menu_kb():
    return ReplyKeyboardMarkup([["Продолжить обучение", "Прогресс"]], resize_keyboard=True)

def get_test_kb(options):
    buttons = [[f"{k}) {v}"] for k, v in options.items()]
    return ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    profile = user_manager.get(user_id)
    if profile:
        await update.message.reply_text(
            f"С возвращением, {profile.name}! Твой уровень: {profile.current_level or 'не определён'}",
            reply_markup=get_main_menu_kb()
        )
        user_states[user_id] = {"state": "menu"}
        return

    await update.message.reply_text("Привет! Как тебя зовут?")
    user_states[user_id] = {"state": "waiting_name"}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    state = user_states.get(user_id, {}).get("state", "menu")
    data = user_states.get(user_id, {}).get("data", {})

    if state == "waiting_name":
        if len(text) < 2:
            await update.message.reply_text("Имя слишком короткое. Попробуй ещё раз:")
            return
        user_states[user_id] = {"state": "waiting_grade", "data": {"name": text}}
        await update.message.reply_text("В каком ты классе? Напиши число от 5 до 9:")
        return

    if state == "waiting_grade":
        try:
            grade = int(text)
            if grade not in range(5, 10):
                raise ValueError
        except:
            await update.message.reply_text("Напиши число от 5 до 9:")
            return
        name = data["name"]
        user_manager.create(user_id, name, grade)
        await update.message.reply_text(
            "Отлично! Теперь пройди короткий тест (5 вопросов), чтобы определить твой уровень.",
            reply_markup=ReplyKeyboardRemove()
        )
        test_questions = [
            {"q": "What ___ you do?", "opts": {"A": "do", "B": "does", "C": "is", "D": "are"}, "ans": "A"},
            {"q": "She ___ to school yesterday.", "opts": {"A": "go", "B": "went", "C": "goes", "D": "going"}, "ans": "B"},
            {"q": "I have ___ apple.", "opts": {"A": "a", "B": "an", "C": "the", "D": "-"}, "ans": "B"},
            {"q": "They ___ playing football now.", "opts": {"A": "is", "B": "am", "C": "are", "D": "be"}, "ans": "C"},
            {"q": "He ___ speak English.", "opts": {"A": "can", "B": "can to", "C": "to can", "D": "cans"}, "ans": "A"},
        ]
        user_states[user_id] = {
            "state": "placement_test",
            "data": {"test": test_questions, "index": 0, "correct": 0}
        }
        await ask_test_question(update, user_id)
        return

    if state == "placement_test":
        test_data = data["test"]
        i = data["index"]
        if i >= len(test_data):
            return  # уже завершён
        correct_ans = test_data[i]["ans"]
        if text.upper().startswith(correct_ans):
            correct = data["correct"] + 1
            await update.message.reply_text("Правильно!")
        else:
            correct = data["correct"]
            await update.message.reply_text(f"Неверно. Правильно: {correct_ans}) {test_data[i]['opts'][correct_ans]}")
        i += 1
        if i >= len(test_data):
            # Завершение теста
            level = determine_level_by_score(correct, len(test_data))
            profile = user_manager.get(user_id)
            profile.current_level = level
            user_manager.save(profile)
            await update.message.reply_text(
                f"Тест завершён! Твой уровень: {level}. Воспользуйся меню, чтобы продолжить.",
                reply_markup=get_main_menu_kb()
            )
            user_states[user_id] = {"state": "menu"}
        else:
            user_states[user_id] = {
                "state": "placement_test",
                "data": {"test": test_data, "index": i, "correct": correct}
            }
            await ask_test_question(update, user_id)
        return

    if state == "menu":
        if text == "Продолжить обучение":
            profile = user_manager.get(user_id)
            if not profile or not profile.current_level:
                await update.message.reply_text("Сначала пройди тест! Напиши /start")
                return
            level = profile.current_level
            module_id = profile.current_module
            module = None
            for m in curriculum.get(level, {}).get("modules", []):
                if m["id"] == module_id:
                    module = m
                    break
            if not module:
                await update.message.reply_text("Модули закончились! Молодец!")
                return
            await update.message.reply_text(f"Начинаем модуль: {module['title']}")
            exercises = await ai.generate_exercises(module['title'], profile.grade, 3)
            if not exercises:
                exercises = [{"question": "I ___ to school.", "correct_answer": "go", "hint": "Present Simple"}]
            user_states[user_id] = {
                "state": "learning",
                "data": {"exercises": exercises, "index": 0, "module_id": module_id}
            }
            await send_exercise(update, user_id)
        elif text == "Прогресс":
            profile = user_manager.get(user_id)
            if profile:
                acc = profile.correct_answers / max(profile.total_exercises, 1)
                await update.message.reply_text(
                    f"Уровень: {profile.current_level}\n"
                    f"Модуль: {profile.current_module}\n"
                    f"Точность: {acc:.0%}\n"
                    f"Ошибок: {len(profile.errors)}"
                )
        return

    if state == "learning":
        exercises = data["exercises"]
        i = data["index"]
        ex = exercises[i]
        result = await ai.check_answer(ex, text)
        profile = user_manager.get(user_id)
        profile.total_exercises += 1
        if result["is_correct"]:
            profile.correct_answers += 1
        else:
            profile.errors.append({"question": ex["question"], "user": text, "correct": ex["correct_answer"]})
        user_manager.save(profile)
        await update.message.reply_text(result["feedback"])
        i += 1
        if i >= len(exercises):
            profile = user_manager.get(user_id)
            profile.completed_modules.append(data["module_id"])
            profile.current_module += 1
            user_manager.save(profile)
            await update.message.reply_text("Модуль завершён! Отличная работа! Используй меню для продолжения обучения.", reply_markup=get_main_menu_kb())
            user_states[user_id] = {"state": "menu"}
        else:
            user_states[user_id] = {
                "state": "learning",
                "data": {"exercises": exercises, "index": i, "module_id": data["module_id"]}
            }
            await send_exercise(update, user_id)
        return

    await update.message.reply_text("Выбери действие:", reply_markup=get_main_menu_kb())
    user_states[user_id] = {"state": "menu"}

async def ask_test_question(update, user_id):
    data = user_states[user_id]["data"]
    test = data["test"]
    i = data["index"]
    q = test[i]
    opts = "\n".join([f"{k}) {v}" for k, v in q["opts"].items()])
    await update.message.reply_text(f"Вопрос {i+1}/5:\n{q['q']}\n\n{opts}", reply_markup=get_test_kb(q["opts"]))

async def send_exercise(update, user_id):
    data = user_states[user_id]["data"]
    ex = data["exercises"][data["index"]]
    msg = ex["question"]
    if "hint" in ex:
        msg += f"\n\nПодсказка: {ex['hint']}"
    msg += "\n\nВведи свой ответ:"
    await update.message.reply_text(msg)


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
