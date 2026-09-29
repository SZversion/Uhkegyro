"""PostgreSQL-backed persistence for anonymous sessions."""
from __future__ import annotations

import uuid
from typing import Any

from backend.shared.auth import hash_session_token


class SessionRepository:
    """Persist session identifiers and token hashes using an asyncpg pool."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def create_session(self, token: str) -> str:
        """Create a session and return its UUID; only the token hash is stored."""
        if not token:
            raise ValueError("token must not be empty")
        row = await self._pool.fetchrow(
            """
            INSERT INTO sessions (session_id, session_token_hash)
            VALUES ($1::uuid, $2)
            RETURNING session_id
            """,
            str(uuid.uuid4()),
            hash_session_token(token),
        )
        return str(row["session_id"])

    async def resolve_session(self, token: str) -> str | None:
        """Resolve a token hash and update activity in the same statement."""
        if not token:
            raise ValueError("token must not be empty")
        row = await self._pool.fetchrow(
            """
            UPDATE sessions
            SET last_activity_at = now()
            WHERE session_token_hash = $1
            RETURNING session_id
            """,
            hash_session_token(token),
        )
        return str(row["session_id"]) if row is not None else None

    async def delete_expired_sessions(self) -> int:
        """Delete sessions inactive for more than three calendar months."""
        result = await self._pool.execute(
            """
            DELETE FROM sessions
            WHERE last_activity_at < now() - interval '3 months'
            """
        )
        return int(result.rsplit(" ", 1)[-1])
