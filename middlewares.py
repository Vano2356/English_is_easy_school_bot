
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject



class DependenciesMiddleware(BaseMiddleware):
    
    
    def __init__(self, **dependencies):
        super().__init__()
        self.dependencies = dependencies
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Добавляем зависимости в data
        data.update(self.dependencies)
        
        # Вызываем handler с обогащенными данными
        return await handler(event, data)