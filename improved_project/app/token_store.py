from typing import Optional, Dict, Set
from .config import settings


class TokenStore:
    """Very simple in-memory token storage. Replace with DB/Redis later."""

    def __init__(self) -> None:
        raw = (settings.INVITE_TOKENS or "").strip()
        self._active: Set[str] = set([t.strip() for t in raw.split(",") if t.strip()])
        self._consumed: Set[str] = set()
        self._by_user: Dict[int, str] = {}

    def is_authorized(self, user_id: int) -> bool:
        return user_id in self._by_user

    def consume(self, token: str, user_id: int) -> bool:
        token = (token or "").strip()
        if not token:
            return False
        if token in self._consumed:
            return False
        if token not in self._active:
            return False
        # mark as used (single-use). For multi-use, remove the next line.
        self._active.remove(token)
        self._consumed.add(token)
        self._by_user[user_id] = token
        return True

    def grant_for_dev(self, user_id: int) -> None:
        """Helper to grant access manually during development."""
        self._by_user[user_id] = "dev"


tokens = TokenStore()