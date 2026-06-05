"""Valkey client for Phase 3 transient data (reminders, session flags)."""
import json
import logging
from datetime import datetime
from typing import Optional

import valkey

from app.config import settings

logger = logging.getLogger(__name__)


class ValkeyClient:
    """Singleton Valkey client — charging reminders (sorted set), session flags (hash)."""

    _instance: Optional['ValkeyClient'] = None

    def __init__(self):
        # Parse VALKEY_URL or build from separate settings
        valkey_url = settings.valkey_url
        if valkey_url:
            # valkey://:password@host:port/db
            parsed = valkey_url.replace("valkey://:", "").replace("valkey://", "")
            if "@" in parsed:
                password_part, rest = parsed.split("@", 1)
                host_port = rest.split("/")[0]
                if ":" in host_port:
                    host, port = host_port.split(":")
                else:
                    host, port = host_port, "6379"
                password = password_part
            else:
                host, port, password = "localhost", "6379", None
        else:
            host = getattr(settings, 'VALKEY_HOST', 'localhost')
            port = 6379
            password = getattr(settings, 'VALKEY_PASSWORD', None)

        self._client: valkey.Valkey = valkey.Valkey(
            host=host,
            port=int(port),
            password=password,
            db=0,
            decode_responses=True,
        )

    @classmethod
    def get_instance(cls) -> 'ValkeyClient':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Charging reminders (sorted set) ───────────────────────────────────────

    def add_charging_reminder(
        self,
        user_id: str,
        vehicle_id: Optional[str],
        remind_at: datetime,
        message: str,
    ) -> str:
        """Add a charging reminder. Returns reminder key."""
        reminder_key = f"reminder:{user_id}"
        score = remind_at.timestamp()
        member = json.dumps({
            "vehicle_id": vehicle_id,
            "remind_at": remind_at.isoformat(),
            "message": message,
            "added_at": datetime.utcnow().isoformat(),
        })
        self._client.zadd(reminder_key, {member: score})
        # Set TTL of 7 days after remind_at
        self._client.expire(reminder_key, int((7 * 86400)))
        return reminder_key

    def get_due_reminders(self, user_id: str, before_dt: Optional[datetime] = None) -> list[dict]:
        """Get reminders that are due (score <= now or <= before_dt)."""
        if before_dt is None:
            before_dt = datetime.utcnow()
        reminder_key = f"reminder:{user_id}"
        max_score = before_dt.timestamp()
        members = self._client.zrangebyscore(reminder_key, '-inf', max_score)
        results = []
        for m in members:
            try:
                data = json.loads(m)
                results.append(data)
            except json.JSONDecodeError:
                continue
        return results

    def remove_reminder(self, user_id: str, remind_at_iso: str) -> bool:
        """Remove a specific reminder by its remind_at timestamp match."""
        reminder_key = f"reminder:{user_id}"
        all_members = self._client.zrange(reminder_key, 0, -1)
        for m in all_members:
            try:
                data = json.loads(m)
                if data.get("remind_at") == remind_at_iso:
                    self._client.zrem(reminder_key, m)
                    return True
            except json.JSONDecodeError:
                continue
        return False

    def list_reminders(self, user_id: str) -> list[dict]:
        """List all upcoming reminders for a user."""
        reminder_key = f"reminder:{user_id}"
        members = self._client.zrange(reminder_key, 0, -1)
        results = []
        for m in members:
            try:
                results.append(json.loads(m))
            except json.JSONDecodeError:
                continue
        return results

    # ── Session flags (hash with TTL) ──────────────────────────────────────────

    def set_session_flag(self, session_id: str, key: str, value: str, ttl_seconds: int = 86400) -> None:
        """Set a flag on a chat session (e.g., 'vehicle_detected', 'last_vehicle')."""
        flag_key = f"session:flags:{session_id}"
        self._client.hset(flag_key, key, value)
        self._client.expire(flag_key, ttl_seconds)

    def get_session_flag(self, session_id: str, key: str) -> Optional[str]:
        """Get a flag value from a chat session."""
        flag_key = f"session:flags:{session_id}"
        return self._client.hget(flag_key, key)

    def clear_session_flags(self, session_id: str) -> None:
        """Delete all flags for a session."""
        flag_key = f"session:flags:{session_id}"
        self._client.delete(flag_key)


# Lazy singleton accessor
def get_valkey() -> ValkeyClient:
    return ValkeyClient.get_instance()