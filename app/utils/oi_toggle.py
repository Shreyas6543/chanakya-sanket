"""
OI strategy toggle — stored in Redis so it survives across requests and can be
flipped at runtime without a server restart.

Key: oi_strategy_enabled
Value: "1" (enabled) or "0" (disabled)
Default: "1" (enabled)
"""
import redis.asyncio as aioredis
from app.config import get_settings

settings = get_settings()
_OI_KEY = "oi_strategy_enabled"


def _client() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def is_oi_enabled() -> bool:
    async with _client() as r:
        val = await r.get(_OI_KEY)
    # Default to enabled if key not set yet
    return val != "0"


async def set_oi_enabled(enabled: bool) -> None:
    async with _client() as r:
        await r.set(_OI_KEY, "1" if enabled else "0")
