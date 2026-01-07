
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class UserProfile:
    
    
    def __init__(self, user_id: int, name: str = "", grade: int = 5):
        self.user_id = user_id
        self.name = name
        self.grade = grade
        self.start_level = None
        self.current_level = None
        self.current_module = 0
        self.current_exercise = 0
        self.completed_modules = []
        self.errors = []  # Список ошибок для retry logic
        self.statistics = {
            "total_exercises": 0,
            "correct_answers": 0,
            "incorrect_answers": 0,
            "modules_completed": 0,
            "new_words_learned": 0,
            "strengths": [],
            "weaknesses": []
        }
        self.module_history = []  # История прохождения модулей
        self.created_at = datetime.now().isoformat()
        self.last_activity = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "grade": self.grade,
            "start_level": self.start_level,
            "current_level": self.current_level,
            "current_module": self.current_module,
            "current_exercise": self.current_exercise,
            "completed_modules": self.completed_modules,
            "errors": self.errors,
            "statistics": self.statistics,
            "module_history": self.module_history,
            "created_at": self.created_at,
            "last_activity": self.last_activity
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserProfile':
        profile = cls(
            user_id=data["user_id"],
            name=data.get("name", ""),
            grade=data.get("grade", 5)
        )
        profile.start_level = data.get("start_level")
        profile.current_level = data.get("current_level")
        profile.current_module = data.get("current_module", 0)
        profile.current_exercise = data.get("current_exercise", 0)
        profile.completed_modules = data.get("completed_modules", [])
        profile.errors = data.get("errors", [])
        profile.statistics = data.get("statistics", profile.statistics)
        profile.module_history = data.get("module_history", [])
        profile.created_at = data.get("created_at", datetime.now().isoformat())
        profile.last_activity = data.get("last_activity", datetime.now().isoformat())
        return profile
    
    def add_error(self, error_data: Dict[str, Any]):
        error_entry = {
            "timestamp": datetime.now().isoformat(),
            "module": self.current_module,
            "exercise": self.current_exercise,
            "error_type": error_data.get("error_type", "unknown"),
            "topic": error_data.get("topic", ""),
            "user_answer": error_data.get("user_answer", ""),
            "correct_answer": error_data.get("correct_answer", ""),
            "explanation": error_data.get("explanation", "")
        }
        self.errors.append(error_entry)
        
        # Ограничение размера буфера
        if len(self.errors) > 50:
            self.errors = self.errors[-50:]
    
    def get_recent_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.errors[-limit:] if self.errors else []
    
    def complete_module(self, module_id: int, score: float, strengths: List[str], weaknesses: List[str]):
        self.completed_modules.append(module_id)
        self.statistics["modules_completed"] += 1
        
        # Добавление в историю
        self.module_history.append({
            "module_id": module_id,
            "completed_at": datetime.now().isoformat(),
            "score": score,
            "strengths": strengths,
            "weaknesses": weaknesses
        })
        
        # Обновление сильных и слабых сторон
        self.statistics["strengths"] = list(set(self.statistics["strengths"] + strengths))
        self.statistics["weaknesses"] = list(set(self.statistics["weaknesses"] + weaknesses))
    
    def update_activity(self):
        self.last_activity = datetime.now().isoformat()


class UserManager:
    
    def __init__(self, users_dir: Path):
        self.users_dir = Path(users_dir)
        self.users_dir.mkdir(exist_ok=True, parents=True)
        logger.info(f"UserManager. {self.users_dir}")
    
    def _get_user_path(self, user_id: int) -> Path:
        return self.users_dir / f"user_{user_id}.json"
    
    def user_exists(self, user_id: int) -> bool:
        return self._get_user_path(user_id).exists()
    
    def create_user(self, user_id: int, name: str = "", grade: int = 5) -> UserProfile:
        if self.user_exists(user_id):
            logger.warning(f"Пользователь {user_id} уже существует")
            return self.get_user(user_id)
        
        profile = UserProfile(user_id=user_id, name=name, grade=grade)
        self.save_user(profile)
        logger.info(f"Создан новый пользователь: {user_id} ({name})")
        return profile
    
    def get_user(self, user_id: int) -> Optional[UserProfile]:
        user_path = self._get_user_path(user_id)
        
        if not user_path.exists():
            logger.warning(f"Пользователь {user_id} не найден")
            return None
        
        try:
            with open(user_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            profile = UserProfile.from_dict(data)
            logger.debug(f"Загружен профиль пользователя {user_id}")
            return profile
        
        except Exception as e:
            logger.error(f"Ошибка при загрузке пользователя {user_id}: {e}")
            return None
    
    def save_user(self, profile: UserProfile) -> bool:
        user_path = self._get_user_path(profile.user_id)
        
        try:
            profile.update_activity()
            
            with open(user_path, 'w', encoding='utf-8') as f:
                json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)
            
            logger.debug(f"Профиль пользователя {profile.user_id} сохранен")
            return True
        
        except Exception as e:
            logger.error(f"Ошибка при сохранении пользователя {profile.user_id}: {e}")
            return False
    
    def update_user(self, user_id: int, **kwargs) -> bool:
        profile = self.get_user(user_id)
        
        if not profile:
            logger.error(f"Невозможно обновить несуществующего пользователя {user_id}")
            return False
        
        # Обновление полей
        for key, value in kwargs.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
                logger.debug(f"Обновлено поле {key} для пользователя {user_id}")
        
        return self.save_user(profile)
    
    def delete_user(self, user_id: int) -> bool:
        user_path = self._get_user_path(user_id)
        
        if not user_path.exists():
            logger.warning(f"Пользователь {user_id} не найден для удаления")
            return False
        
        try:
            user_path.unlink()
            logger.info(f"Пользователь {user_id} удален")
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении пользователя {user_id}: {e}")
            return False
    
    def get_all_users(self) -> List[UserProfile]:
        users = []
        
        for user_file in self.users_dir.glob("user_*.json"):
            try:
                with open(user_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                users.append(UserProfile.from_dict(data))
            except Exception as e:
                logger.error(f"Ошибка при загрузке файла {user_file}: {e}")
        
        logger.info(f"Загружено {len(users)} пользователей")
        return users
    
    def get_user_statistics(self, user_id: int) -> Optional[Dict[str, Any]]:
        profile = self.get_user(user_id)
        
        if not profile:
            return None
        
        stats = profile.statistics.copy()
        stats["accuracy"] = (
            stats["correct_answers"] / stats["total_exercises"] 
            if stats["total_exercises"] > 0 else 0
        )
        stats["current_level"] = profile.current_level
        stats["current_module"] = profile.current_module
        stats["total_modules"] = len(profile.completed_modules)
        
        return stats