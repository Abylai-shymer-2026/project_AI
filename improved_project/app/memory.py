from collections import deque
from typing import Deque, Dict, List

from .config import settings


class Memory:
    def __init__(self, max_turns: int = 6):
        self.max_turns = max_turns
        self._data: Dict[int, Deque[dict]] = {}

    def get(self, user_id: int) -> List[dict]:
        return list(self._data.get(user_id, deque(maxlen=self.max_turns * 2)))

    def append(self, user_id: int, role: str, content: str) -> None:
        dq = self._data.setdefault(user_id, deque(maxlen=self.max_turns * 2))
        dq.append({"role": role, "content": content})

    def clear(self, user_id: int) -> None:
        self._data.pop(user_id, None)


memory = Memory(max_turns=getattr(settings, "MAX_HISTORY_TURNS", 6))
