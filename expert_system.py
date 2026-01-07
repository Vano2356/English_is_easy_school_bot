
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class ExpertSystem:
    
    def __init__(self, curriculum_path: Path, error_threshold: float = 0.5, excellent_threshold: float = 0.9):
        self.curriculum_path = Path(curriculum_path)
        self.error_threshold = error_threshold  # 50% ошибок - упрощаем
        self.excellent_threshold = excellent_threshold  # 90% - усложняем
        self.curriculum = self._load_curriculum()
        logger.info(f"ExpertSystem инициализирована. Загружено уровней: {len(self.curriculum)}")
    
    def _load_curriculum(self) -> Dict[str, Any]:
        """Загрузка curriculum.json - базы знаний"""
        try:
            with open(self.curriculum_path, 'r', encoding='utf-8') as f:
                curriculum = json.load(f)
            logger.info(f"Curriculum загружен: {list(curriculum.keys())}")
            return curriculum
        except FileNotFoundError:
            logger.error(f"Файл curriculum.json не найден: {self.curriculum_path}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга curriculum.json: {e}")
            return {}
    
    def get_module(self, level: str, module_id: int) -> Optional[Dict[str, Any]]:
        """Получение модуля по уровню и ID"""
        if level not in self.curriculum:
            logger.warning(f"Уровень {level} не найден в curriculum")
            return None
        
        modules = self.curriculum[level].get("modules", [])
        
        for module in modules:
            if module["id"] == module_id:
                return module
        
        logger.warning(f"Модуль {module_id} не найден для уровня {level}")
        return None
    
    def get_all_modules(self, level: str) -> List[Dict[str, Any]]:
        """Получение всех модулей уровня"""
        if level not in self.curriculum:
            return []
        return self.curriculum[level].get("modules", [])
    
    def determine_start_level(self, test_score: float) -> str:
        """
        Определение начального уровня на основе входного теста
        test_score: от 0.0 до 1.0 (процент правильных ответов)
        """
        if test_score < 0.4:
            level = "A1"
        elif test_score < 0.7:
            level = "A2"
        else:
            level = "B1"
        
        logger.info(f"Определен начальный уровень: {level} (score: {test_score:.2f})")
        return level
    
    def analyze_module_performance(self, correct: int, total: int, errors: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Анализ прохождения модуля
        Возвращает рекомендации для следующего модуля
        """
        if total == 0:
            logger.warning("Анализ невозможен: total = 0")
            return {"status": "error", "message": "Нет данных для анализа"}
        
        accuracy = correct / total
        
        # Определение статуса
        if accuracy >= self.excellent_threshold:
            status = "excellent"
            difficulty_adjustment = "increase"  # Можно усложнить
        elif accuracy < self.error_threshold:
            status = "needs_review"
            difficulty_adjustment = "decrease"  # Нужно упростить
        else:
            status = "good"
            difficulty_adjustment = "maintain"  # Оставить как есть
        
        # Анализ типов ошибок
        error_types = {}
        weak_topics = []
        
        for error in errors:
            error_type = error.get("error_type", "unknown")
            topic = error.get("topic", "unknown")
            
            error_types[error_type] = error_types.get(error_type, 0) + 1
            
            if topic not in weak_topics and topic != "unknown":
                weak_topics.append(topic)
        
        # Определение сильных сторон (темы с минимумом ошибок)
        strengths = self._identify_strengths(errors, total)
        
        result = {
            "status": status,
            "accuracy": accuracy,
            "difficulty_adjustment": difficulty_adjustment,
            "weak_topics": weak_topics[:3],  # Топ-3 проблемных темы
            "strengths": strengths,
            "error_types": error_types,
            "recommendation": self._generate_recommendation(status, accuracy, weak_topics)
        }
        
        logger.info(f"Анализ модуля: accuracy={accuracy:.2f}, status={status}")
        return result
    
    def _identify_strengths(self, errors: List[Dict[str, Any]], total_exercises: int) -> List[str]:
        """Определение сильных сторон (темы без ошибок или с минимумом ошибок)"""
        # Упрощенная логика - в реальности нужно знать все темы модуля
        if len(errors) < total_exercises * 0.2:  # Менее 20% ошибок
            return ["Grammar", "Vocabulary"]
        elif len(errors) < total_exercises * 0.4:
            return ["Vocabulary"]
        return []
    
    def _generate_recommendation(self, status: str, accuracy: float, weak_topics: List[str]) -> str:
        """Генерация рекомендации для ученика"""
        if status == "excellent":
            return "Отличная работа! Ты готов к более сложному материалу."
        elif status == "needs_review":
            topics_str = ", ".join(weak_topics) if weak_topics else "некоторые темы"
            return f"Рекомендуется повторить: {topics_str}. Не переживай, практика поможет!"
        else:
            return "Хороший результат! Продолжай в том же духе."
    
    def get_next_module_config(self, user_profile: Any, module_analysis: Dict[str, Any]) -> Dict[str, Any]:
        
        current_level = user_profile.current_level
        next_module_id = user_profile.current_module + 1
        
        # Получение следующего модуля
        next_module = self.get_module(current_level, next_module_id)
        
        if not next_module:
            # Модули закончились - переход на следующий уровень
            return self._prepare_level_transition(user_profile)
        
        # Базовая конфигурация
        config = {
            "module_id": next_module_id,
            "level": current_level,
            "module_info": next_module,
            "difficulty": next_module.get("difficulty", "medium"),
            "exercises_count": 5,
            "include_review": False,
            "review_topics": [],
            "special_instructions": []
        }
        
        # Адаптация на основе анализа
        if module_analysis.get("difficulty_adjustment") == "decrease":
            config["difficulty"] = "easy"
            config["exercises_count"] = 4  # Меньше упражнений
            config["special_instructions"].append("Используй более простые примеры и больше подсказок")
        
        elif module_analysis.get("difficulty_adjustment") == "increase":
            config["difficulty"] = "hard"
            config["exercises_count"] = 6  # Больше упражнений
            config["special_instructions"].append("Добавь усложненные задания и меньше подсказок")
        
        # Добавление повторения проблемных тем
        weak_topics = module_analysis.get("weak_topics", [])
        if weak_topics:
            config["include_review"] = True
            config["review_topics"] = weak_topics
            config["special_instructions"].append(
                f"Включи повторение тем: {', '.join(weak_topics)}"
            )
        
        logger.info(f"Конфигурация следующего модуля: {config['module_id']}, difficulty={config['difficulty']}")
        return config
    
    def _prepare_level_transition(self, user_profile: Any) -> Dict[str, Any]:
        """Подготовка перехода на следующий уровень"""
        current_level = user_profile.current_level
        level_order = ["A1", "A2", "B1"]
        
        try:
            current_index = level_order.index(current_level)
            if current_index < len(level_order) - 1:
                next_level = level_order[current_index + 1]
                
                return {
                    "level_complete": True,
                    "current_level": current_level,
                    "next_level": next_level,
                    "message": f"Поздравляем! Уровень {current_level} завершен. Переходим на {next_level}!",
                    "module_id": 1,
                    "level": next_level
                }
            else:
                return {
                    "course_complete": True,
                    "message": "Поздравляем! Вы завершили весь курс!",
                    "achievement": "full_course_completion"
                }
        except ValueError:
            logger.error(f"Неизвестный уровень: {current_level}")
            return {"error": "Invalid level"}
    
    def select_retry_exercises(self, user_errors: List[Dict[str, Any]], count: int = 2) -> List[Dict[str, Any]]:
        """
        Выбор упражнений для повторения из буфера ошибок
        Реализация retry logic
        """
        if not user_errors:
            return []
        
        # Группировка ошибок по темам
        errors_by_topic = {}
        for error in user_errors:
            topic = error.get("topic", "unknown")
            if topic not in errors_by_topic:
                errors_by_topic[topic] = []
            errors_by_topic[topic].append(error)
        
        # Выбор тем с наибольшим количеством ошибок
        sorted_topics = sorted(
            errors_by_topic.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )
        
        selected_errors = []
        for topic, errors in sorted_topics[:count]:
            # Берем последнюю ошибку по теме (самая свежая)
            selected_errors.append(errors[-1])
        
        logger.info(f"Выбрано {len(selected_errors)} упражнений для повторения")
        return selected_errors
    
    def generate_ai_prompt_for_module(self, config: Dict[str, Any], user_profile: Any) -> str:
        """
        Генерация промпта для AI на основе конфигурации модуля
        Этот промпт будет отправлен Claude для генерации упражнений
        """
        module_info = config["module_info"]
        
        prompt = f"""Создай {config['exercises_count']} упражнений для модуля "{module_info['title']}" уровня {config['level']}.

Информация о модуле:
- Темы: {', '.join(module_info['topics'])}
- Ключевая грамматика: {', '.join(module_info['key_grammar'])}
- Ключевая лексика: {', '.join(module_info['key_vocabulary'])}
- Сложность: {config['difficulty']}

Информация об ученике:
- Класс: {user_profile.grade}
- Текущий модуль: {user_profile.current_module}
- Статистика: {user_profile.statistics['correct_answers']}/{user_profile.statistics['total_exercises']} правильных ответов
"""
        
        # Добавление специальных инструкций
        if config.get("special_instructions"):
            prompt += "\n\nСпециальные инструкции:\n"
            for instruction in config["special_instructions"]:
                prompt += f"- {instruction}\n"
        
        # Добавление повторения тем
        if config.get("include_review") and config.get("review_topics"):
            prompt += f"\n\nОБЯЗАТЕЛЬНО включи повторение следующих проблемных тем: {', '.join(config['review_topics'])}"
        
        prompt += """

Формат ответа - JSON массив упражнений:
[
  {
    "exercise_number": 1,
    "type": "fill_blank",
    "question": "Текст задания",
    "correct_answer": "правильный ответ",
    "hint": "подсказка (опционально)"
  }
]

Типы упражнений: fill_blank, translate, sentence_construction, error_correction"""
        
        return prompt