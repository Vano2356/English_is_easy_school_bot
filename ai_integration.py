import json
import logging
from typing import Dict, Any, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


class AIIntegration:
    """
    Класс для работы с OpenRouter API (DeepSeek)
    """

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek/deepseek-r1-0528:free",
        max_tokens: int = 1000,
        site_url: Optional[str] = None,
        site_name: Optional[str] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.url = "https://openrouter.ai/api/v1/chat/completions"

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        if site_url:
            self.headers["HTTP-Referer"] = site_url
        if site_name:
            self.headers["X-Title"] = site_name

        logger.info(f"AIIntegration инициализирована. Модель: {self.model}")

    # --------------------------------------------------
    # ВНУТРЕННИЙ МЕТОД ЗАПРОСА
    # Поддерживает дополнительные параметры (temperature, top_p и т.д.)
    # --------------------------------------------------

    async def _request(self, messages: List[Dict[str, str]], max_tokens: Optional[int] = None, **kwargs) -> str:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
        }

        # Добавляем дополнительные опции запроса (temperature, top_p ...)
        for k, v in kwargs.items():
            if v is not None:
                payload[k] = v

        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.post(self.url, json=payload, timeout=90) as response:
                    response.raise_for_status()
                    data = await response.json()

                    # Пытаемся корректно извлечь текст из возможных форматов ответа
                    text = ""

                    choices = data.get("choices") or data.get("results") or []
                    if isinstance(choices, list) and choices:
                        first = choices[0]
                        if isinstance(first, dict):
                            # Чаще всего: {"message": {"role": "...", "content": "..."}}
                            msg = first.get("message")
                            if isinstance(msg, dict) and "content" in msg:
                                text = msg["content"]
                            # Альтернативы: {"text": "..."} или {"content": "..."}
                            elif "text" in first and isinstance(first["text"], str):
                                text = first["text"]
                            elif "content" in first and isinstance(first["content"], str):
                                text = first["content"]

                    # Фоллбэк на другие поля
                    if not text:
                        if isinstance(data.get("completion"), str):
                            text = data["completion"]
                        elif isinstance(data.get("output"), str):
                            text = data["output"]

                    # Если всё ещё пусто — возвращаем сериализованный ответ для отладки
                    if not text:
                        text = json.dumps(data, ensure_ascii=False)

                    return text

        except Exception as e:
            logger.error("Ошибка при запросе к OpenRouter", exc_info=True)
            raise e

    # --------------------------------------------------
    # УТИЛИТА ПАРСИНГА JSON
    # --------------------------------------------------

    def _parse_json(self, text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            if "```json" in text:
                start = text.find("```json") + 7
                end = text.find("```", start)
                return json.loads(text[start:end].strip())
            # Попытки извлечь JSON-объект/массив внутри текста
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end+1])
                except json.JSONDecodeError:
                    pass
            start = text.find('[')
            end = text.rfind(']')
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end+1])
                except json.JSONDecodeError:
                    pass
            raise

    # --------------------------------------------------
    # ГЕНЕРАЦИЯ УПРАЖНЕНИЙ
    # --------------------------------------------------

    async def generate_exercises(self, prompt: str) -> List[Dict[str, Any]]:
        system_prompt = """Ты - опытный преподаватель английского языка для школьников 5-9 классов.
Создавай интересные и эффективные упражнения.

ОБЯЗАТЕЛЬНО отвечай ТОЛЬКО в формате JSON.
"""

        try:
            text = await self._request(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ]
            )
            exercises = self._parse_json(text)
            logger.info(f"Сгенерировано упражнений: {len(exercises)}")
            return exercises

        except Exception:
            logger.error("Не удалось сгенерировать упражнения", exc_info=True)
            return []

    # --------------------------------------------------
    # ПРОВЕРКА ОТВЕТА
    # --------------------------------------------------

    async def check_answer(self, exercise: Dict[str, Any], user_answer: str) -> Dict[str, Any]:
        system_prompt = """Ты - строгий, но справедливый преподаватель английского языка.

Ответь строго в JSON:
{
  "is_correct": true/false,
  "score": 1-5,
  "feedback": "...",
  "error_type": "grammar/vocabulary/spelling/other",
  "correct_answer": "..."
}
"""

        prompt = f"""
Упражнение: {exercise.get('question')}
Правильный ответ: {exercise.get('correct_answer')}
Ответ ученика: {user_answer}
"""

        try:
            text = await self._request(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=500,
            )
            result = self._parse_json(text)
            return result

        except Exception:
            return self._simple_check(exercise, user_answer)

    # --------------------------------------------------
    # FALLBACK
    # --------------------------------------------------

    def _simple_check(self, exercise: Dict[str, Any], user_answer: str) -> Dict[str, Any]:
        correct = exercise.get("correct_answer", "").strip().lower()
        user = user_answer.strip().lower()

        is_correct = correct == user

        return {
            "is_correct": is_correct,
            "score": 5 if is_correct else 2,
            "feedback": "Правильно!" if is_correct else f"Неверно. Правильный ответ: {exercise.get('correct_answer')}",
            "error_type": None if is_correct else "unknown",
            "correct_answer": None if is_correct else exercise.get("correct_answer"),
        }

    # --------------------------------------------------
    # ОБЪЯСНЕНИЕ ОШИБКИ
    # --------------------------------------------------

    async def explain_error(self, error_data: Dict[str, Any]) -> str:
        prompt = f"""
Ученик ответил: {error_data.get('user_answer')}
Правильный ответ: {error_data.get('correct_answer')}
Тип ошибки: {error_data.get('error_type')}

Объясни ошибку простым языком (2-3 предложения).
"""

        try:
            return await self._request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
            )
        except Exception:
            return "Пока не могу объяснить ошибку, попробуй позже."

    # --------------------------------------------------
    # ДИАЛОГ
    # --------------------------------------------------

    async def conduct_dialogue(
        self,
        topic: str,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        if conversation_history is None:
            conversation_history = []

        system_prompt = f"""Ты дружелюбный собеседник для практики английского.
Тема: {topic}
Отвечай простым английским.
"""

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_message})

        try:
            return await self._request(messages, max_tokens=200)
        except Exception:
            return "Sorry, I can't reply right now."

    # --------------------------------------------------
    # ВХОДНОЙ ТЕСТ
    # --------------------------------------------------
    async def generate_placement_test(self, num_questions: int = 15) -> List[Dict[str, Any]]:
        system_prompt = """Ты — эксперт по оценке уровня английского языка (A1–B1).
            СТРОГИЕ ПРАВИЛА:
            1. Отвечай ТОЛЬКО валидным JSON-массивом.
            2. Никакого текста до или после JSON.
            3. Каждый вопрос — объект со строго заданными полями.
            4. "options" — словарь с ключами "A", "B", "C", "D".
            5. "correct_answer" — одна из букв: A, B, C, D.
            6. Убедись, что ответы разнообразны по темам и уровням.
            """

        user_prompt = f"""
            Создай ровно {num_questions} вопросов для входного теста.
            Распредели вопросы по уровням: 5 A1, 5 A2, 5 B1.
            Включи различные темы: grammar, vocabulary, reading.

            ФОРМАТ ОДНОГО ВОПРОСА:
            {{
              "question": "What is the correct sentence?",
              "options": {{
                "A": "She go to school.",
                "B": "She goes to school.",
                "C": "She going to school.",
                "D": "She gone to school."
              }},
              "correct_answer": "B",
              "full_answer": "She goes to school.",
              "topic": "present_simple",
              "level": "A1"
            }}

            Верни ТОЛЬКО JSON-массив. НИЧЕГО БОЛЬШЕ.
            """

        try:

            text = await self._request(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=4000,  # Увеличьте для большего количества вопросов
                temperature=0.7,
            )

            # Очистка текста от возможных markdown
            text = text.strip()
            if text.startswith('```json'):
                text = text[7:]
            if text.endswith('```'):
                text = text[:-3]
            text = text.strip()

            questions = self._parse_json(text)

            if isinstance(questions, list) and len(questions) >= num_questions:
                logger.info(f"Сгенерирован входной тест: {len(questions)} вопросов")

                # Валидация структуры
                valid_questions = []
                for q in questions[:num_questions]:  # Берем только нужное количество
                    if all(key in q for key in ['question', 'options', 'correct_answer']):
                        # Проверяем, что options - словарь
                        if isinstance(q['options'], dict) and all(k in q['options'] for k in ['A', 'B', 'C', 'D']):
                            valid_questions.append(q)

                logger.info(f"Валидных вопросов: {len(valid_questions)}")
                return valid_questions
            else:
                logger.error(f"Некорректный формат ответа или недостаточно вопросов: {len(questions) if isinstance(questions, list) else 'не список'}")
                return []

        except Exception as e:
            logger.error(f"Не удалось сгенерировать входной тест: {e}", exc_info=True)
            return []


    # --------------------------------------------------
    # ОТЧЕТ ПО МОДУЛЮ
    # --------------------------------------------------

    async def generate_module_summary(self, user_profile: Any, module_info: Dict[str, Any], analysis: Dict[str, Any]) -> str:
        prompt = f"""
Создай мотивирующий отчет для ученика {user_profile.grade} класса.

Модуль: {module_info['title']}
Точность: {analysis['accuracy']:.0%}
Сильные стороны: {', '.join(analysis.get('strengths', []))}
Слабые темы: {', '.join(analysis.get('weak_topics', []))}
"""

        try:
            return await self._request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
            )
        except Exception:
            return "Модуль завершён! Отличная работа!"
