import json
from pathlib import Path
from datetime import datetime

USERS_DIR = Path("data/users")

class UserProfile:
    def __init__(self, user_id, name="", grade=5):
        self.user_id = user_id
        self.name = name
        self.grade = grade
        self.current_level = None
        self.current_module = 1
        self.completed_modules = []
        self.errors = []
        self.total_exercises = 0
        self.correct_answers = 0
        self.last_activity = datetime.now().isoformat()

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "name": self.name,
            "grade": self.grade,
            "current_level": self.current_level,
            "current_module": self.current_module,
            "completed_modules": self.completed_modules,
            "errors": self.errors,
            "total_exercises": self.total_exercises,
            "correct_answers": self.correct_answers,
            "last_activity": self.last_activity,
        }

def load_profile(data: dict) -> UserProfile:
    p = UserProfile(user_id=data["user_id"])
    p.name = data.get("name", "")
    p.grade = data.get("grade", 5)
    p.current_level = data.get("current_level")
    p.current_module = data.get("current_module", 1)
    p.completed_modules = data.get("completed_modules", [])
    p.errors = data.get("errors", [])
    p.total_exercises = data.get("total_exercises", 0)
    p.correct_answers = data.get("correct_answers", 0)
    p.last_activity = data.get("last_activity", "")
    return p

class UserManager:
    def __init__(self):
        USERS_DIR.mkdir(exist_ok=True)

    def path(self, uid):
        return USERS_DIR / f"user_{uid}.json"

    def get(self, uid):
        p = self.path(uid)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            return load_profile(data)
        return None

    def save(self, profile):
        p = self.path(profile.user_id)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)

    def create(self, uid, name, grade):
        profile = UserProfile(uid, name, grade)
        self.save(profile)
        return profile

def load_curriculum():
    return json.loads(Path("data/curriculum.json").read_text(encoding="utf-8"))

def determine_level_by_score(correct, total):
    score = correct / total if total else 0
    if score < 0.4: return "A1"
    if score < 0.7: return "A2"
    return "B1"