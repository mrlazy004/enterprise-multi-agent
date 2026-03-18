"""
Per-agent, per-session conversation memory backed by Redis.
Falls back to in-process dict if Redis is unavailable.
"""
import json
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

import redis.asyncio as aioredis
from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import AIMessage, HumanMessage, SystemMessage

from backend.core.config import settings
from backend.core.logging_config import get_logger

logger = get_logger("memory")


class AgentMemory:
    """
    Wraps LangChain's ConversationBufferWindowMemory and persists it
    to Redis so memory survives pod restarts.
    """

    KEY_PREFIX = "agent_memory"

    def __init__(self, session_id: str, agent_type: str):
        self.session_id = session_id
        self.agent_type = agent_type
        self.key = f"{self.KEY_PREFIX}:{agent_type}:{session_id}"
        self._redis: Optional[aioredis.Redis] = None
        self._local: List[Dict] = []         # fallback
        self.lc_memory = ConversationBufferWindowMemory(
            memory_key="chat_history",
            return_messages=True,
            k=settings.MEMORY_WINDOW_SIZE,
            human_prefix="User",
            ai_prefix=f"{agent_type.upper()} Agent",
        )

    # ── Redis ─────────────────────────────────────────────────────────────────
    async def _get_redis(self) -> Optional[aioredis.Redis]:
        if self._redis is None:
            try:
                self._redis = await aioredis.from_url(
                    settings.REDIS_URL, encoding="utf-8", decode_responses=True
                )
                await self._redis.ping()
            except Exception as exc:
                logger.warning(f"Redis unavailable, using in-process memory: {exc}")
                self._redis = None
        return self._redis

    async def _load_from_redis(self) -> List[Dict]:
        r = await self._get_redis()
        if r:
            raw = await r.get(self.key)
            if raw:
                return json.loads(raw)
        return []

    async def _save_to_redis(self, messages: List[Dict]):
        r = await self._get_redis()
        if r:
            await r.setex(
                self.key,
                86400,  # TTL: 24 hours
                json.dumps(messages),
            )

    # ── Public API ────────────────────────────────────────────────────────────
    async def load(self):
        """Populate LangChain memory from persistent store."""
        messages = await self._load_from_redis() or self._local
        self.lc_memory.clear()
        for msg in messages[-(settings.MEMORY_WINDOW_SIZE * 2):]:
            if msg["role"] == "human":
                self.lc_memory.chat_memory.add_user_message(msg["content"])
            elif msg["role"] == "ai":
                self.lc_memory.chat_memory.add_ai_message(msg["content"])

    async def add_turn(self, human_msg: str, ai_msg: str):
        """Persist a conversation turn."""
        now = datetime.now(timezone.utc).isoformat()
        messages = await self._load_from_redis() or self._local
        messages.extend([
            {"role": "human", "content": human_msg, "ts": now},
            {"role": "ai", "content": ai_msg, "ts": now},
        ])
        # Keep only the last N * 2 messages
        messages = messages[-(settings.MEMORY_WINDOW_SIZE * 2):]
        await self._save_to_redis(messages)
        self._local = messages
        self.lc_memory.chat_memory.add_user_message(human_msg)
        self.lc_memory.chat_memory.add_ai_message(ai_msg)

    async def get_history(self) -> List[Dict]:
        return await self._load_from_redis() or self._local

    async def clear(self):
        r = await self._get_redis()
        if r:
            await r.delete(self.key)
        self._local = []
        self.lc_memory.clear()

    def get_lc_memory(self) -> ConversationBufferWindowMemory:
        return self.lc_memory


# ── Memory registry (one instance per session×agent) ─────────────────────────
_registry: Dict[str, AgentMemory] = {}


def get_agent_memory(session_id: str, agent_type: str) -> AgentMemory:
    key = f"{session_id}:{agent_type}"
    if key not in _registry:
        _registry[key] = AgentMemory(session_id, agent_type)
    return _registry[key]
