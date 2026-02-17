import os
from dataclasses import dataclass
from typing import Any, Optional

import redis


@dataclass(frozen=True)
class RedisCache:
    client: redis.Redis

    @staticmethod
    def from_env() -> "RedisCache":
        url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        client = redis.Redis.from_url(url, decode_responses=True)
        return RedisCache(client=client)

    def get_json(self, key: str) -> Optional[Any]:
        raw = self.client.get(key)
        if raw is None:
            return None
        try:
            import json

            return json.loads(raw)
        except Exception:
            return None

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        import json

        self.client.setex(key, ttl_seconds, json.dumps(value, ensure_ascii=False))

