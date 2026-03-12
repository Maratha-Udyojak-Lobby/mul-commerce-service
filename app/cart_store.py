"""Redis-backed cart storage with in-memory fallback for local dev."""

from __future__ import annotations

import json
import os
from typing import Dict

import redis


class CartStore:
    def __init__(self) -> None:
        self._redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._client: redis.Redis | None = None
        self._memory_store: dict[str, str] = {}

        try:
            self._client = redis.Redis.from_url(self._redis_url, decode_responses=True)
            self._client.ping()
        except Exception:
            self._client = None

    def _key(self, cart_id: str) -> str:
        return f"cart:{cart_id}"

    def get_quantities(self, cart_id: str) -> Dict[int, int]:
        raw: str | None = None
        key = self._key(cart_id)

        try:
            if self._client:
                raw = self._client.get(key)
            else:
                raw = self._memory_store.get(key)
        except Exception:
            raw = self._memory_store.get(key)

        if not raw:
            return {}

        try:
            data = json.loads(raw)
            return {int(k): int(v) for k, v in data.items() if int(v) > 0}
        except Exception:
            return {}

    def set_quantities(self, cart_id: str, quantities: Dict[int, int]) -> None:
        payload = json.dumps({str(k): int(v) for k, v in quantities.items() if int(v) > 0})
        key = self._key(cart_id)

        try:
            if self._client:
                self._client.set(key, payload, ex=60 * 60 * 24 * 7)
            else:
                self._memory_store[key] = payload
        except Exception:
            self._memory_store[key] = payload

    def clear(self, cart_id: str) -> None:
        key = self._key(cart_id)
        try:
            if self._client:
                self._client.delete(key)
            else:
                self._memory_store.pop(key, None)
        except Exception:
            self._memory_store.pop(key, None)


cart_store = CartStore()


def get_cart_store() -> CartStore:
    return cart_store
