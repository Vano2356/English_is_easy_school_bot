import json
import aiohttp


class AIIntegration:
    def __init__(self, api_key: str, model: str = "deepseek/deepseek-r1-0528:free"):
        self.api_key = api_key
        self.model = model
        self.url = "https://openrouter.ai/api/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def request(self, messages, max_tokens=1000, temperature=0.3):
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.post(self.url, json=payload, timeout=90) as resp:
                    data = await resp.json()
                    choices = data.get("choices", [])
                    if choices and isinstance(choices[0], dict):
                        msg = choices[0].get("message")
                        if msg and "content" in msg:
                            return msg["content"]
                    return json.dumps(data)
        except Exception as e:
            print("AI error:", e)
            raise

    def parse_json(self, text: str):
        """Безопасное извлечение JSON из текста"""
        try:
            return json.loads(text)
        except:
            print(text)
            if "```json" in text:
                start = text.find("```json") + 7
                end = text.find("```", start)
                if end != -1:
                    return json.loads(text[start:end].strip())
            s = text.find('{')
            e = text.rfind('}')
            if s != -1 and e > s:
                return json.loads(text[s:e + 1])
            raise ValueError(f"No valid JSON found {text}")

    def validate_exercises(self, exercises):
        """Проверяет, что упражнения соответствуют ожидаемому формату"""
        if not isinstance(exercises, list):
            return False
        for ex in exercises:
            if not isinstance(ex, dict):
                return False
            if "question" not in ex or "correct_answer" not in ex:
                return False
            if not isinstance(ex["correct_answer"], str):
                ex["correct_answer"] = str(ex["correct_answer"])
        return True

    async def generate_exercises(self, topic: str, grade: int, count: int = 3):
        prompt = f"""Ты — учитель английского для школьников {grade} класса.
Создай ровно {count} упражнений по теме "{topic}".

Каждое упражнение должно быть в виде объекта со следующими полями:
- "exercise_number": номер (1, 2, ...)
- "type": тип упражнения (один из: "fill_blank", "translate", "sentence_construction", "error_correction")
- "question": вопрос или задание на русском или английском
- "correct_answer": правильный ответ (строка)
- "hint": краткая подсказка на русском (опционально)

Пример одного упражнения:
{{
  "exercise_number": 1,
  "type": "fill_blank",
  "question": "I ___ to school every day.",
  "correct_answer": "go",
  "hint": "Present Simple, глагол 'to go'"
}}

Верни ТОЛЬКО JSON-массив таких объектов. Никакого другого текста до или после."""

        try:
            text = await self.request([
                {"role": "user", "content": prompt}
            ], max_tokens=1500, temperature=0.4)
            exercises = self.parse_json(text)
            if self.validate_exercises(exercises):
                return exercises[:count]
            else:
                print("AI returned invalid exercise format")
                return []
        except Exception as e:
            print("Error generating exercises:", e)
            return []

    async def check_answer(self, exercise, user_answer: str):
        prompt = f"""Упражнение: {exercise.get('question')}
Правильный ответ: {exercise.get('correct_answer')}
Ответ ученика: {user_answer}

Проанализируй ответ. Верни ТОЛЬКО JSON со следующими полями:
- "is_correct": true или false
- "score": целое число от 1 до 5 (5 = идеально)
- "feedback": краткое объяснение на русском (1–2 предложения)
- "error_type": одна из: "grammar", "vocabulary", "spelling", "word_order", "other", null
- "correct_answer": строка с правильным ответом, только если is_correct=false, иначе null

Пример:
{{"is_correct":false,"score":3,"feedback":"Нужен Present Simple, а не Past.","error_type":"grammar","correct_answer":"go"}}"""

        try:
            text = await self.request([
                {"role": "user", "content": prompt}
            ], max_tokens=5000, temperature=0.1)
            print(text)
            result = self.parse_json(text)
            result["is_correct"] = bool(result.get("is_correct"))
            result["score"] = int(result.get("score", 3))
            if result["score"] < 1:
                result["score"] = 1
            if result["score"] > 5:
                result["score"] = 5
            return result
        except Exception as e:
            print("Fallback to simple check due to AI error:", e)
            correct = exercise.get("correct_answer", "").strip().lower()
            user = user_answer.strip().lower()
            is_correct = correct == user
            return {
                "is_correct": is_correct,
                "score": 5 if is_correct else 2,
                "feedback": "Правильно!" if is_correct else f"Неверно. Правильно: {exercise.get('correct_answer')}",
                "error_type": None if is_correct else "unknown",
                "correct_answer": None if is_correct else exercise.get("correct_answer"),
            }