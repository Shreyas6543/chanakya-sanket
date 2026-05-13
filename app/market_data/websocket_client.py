import asyncio
import json
import ssl
import certifi
import structlog
import websockets
from datetime import datetime, timezone
from google.protobuf import json_format

from app.config import get_settings
from app.market_data.candle_processor import process_tick

logger = structlog.get_logger()
settings = get_settings()


async def _save_candle_to_db(symbol: str, candle: dict):
    """Persist a finalized live candle to the DB so restarts can recover it."""
    try:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from app.db.database import AsyncSessionLocal
        from app.db.models import Candle
        async with AsyncSessionLocal() as session:
            stmt = pg_insert(Candle).values(
                symbol=symbol,
                timeframe="5m",
                open=candle["open"],
                high=candle["high"],
                low=candle["low"],
                close=candle["close"],
                volume=candle["volume"],
                timestamp=candle["timestamp"],
            ).on_conflict_do_nothing()
            await session.execute(stmt)
            await session.commit()
    except Exception as e:
        logger.warning("Failed to persist candle to DB", symbol=symbol, error=str(e))

# Upstox v3 WebSocket URL (v2 is deprecated)
UPSTOX_WS_URL = "wss://api.upstox.com/v3/feed/market-data-feed"

# Live price store — updated on every tick, read by scheduler & evaluator
LIVE_PRICES: dict[str, float] = {}

# Instrument key → our symbol name
_INSTRUMENT_MAP = {
    "NSE_INDEX|Nifty 50": "NIFTY",
    "NSE_INDEX|Nifty Bank": "BANKNIFTY",
}


def get_live_price(symbol: str) -> float | None:
    """Return the most recent live price from WebSocket, or None if not yet received."""
    return LIVE_PRICES.get(symbol)


class UpstoxWebSocketClient:
    def __init__(self):
        self._running = False
        self._ws = None

    async def connect(self):
        token = settings.upstox_access_token
        if not token:
            logger.error("Upstox access token not set — cannot connect WebSocket")
            return

        headers = {
            "Authorization": f"Bearer {token}",
            "Api-Version": "2.0",
        }

        ssl_ctx = ssl.create_default_context(cafile=certifi.where())

        self._running = True
        while self._running:
            try:
                logger.info("Connecting to Upstox WebSocket...")
                async with websockets.connect(UPSTOX_WS_URL, additional_headers=headers, ssl=ssl_ctx) as ws:
                    self._ws = ws
                    await self._subscribe(ws)
                    logger.info("Upstox WebSocket connected", instruments=settings.instrument_list)
                    async for raw_message in ws:
                        await self._handle_message(raw_message)
            except Exception as e:
                logger.warning("WebSocket disconnected, reconnecting in 5s", error=str(e))
                await asyncio.sleep(5)

    async def _subscribe(self, ws):
        payload = {
            "guid": "chanakya-sanket",
            "method": "sub",
            "data": {
                "mode": "ltpc",
                "instrumentKeys": settings.instrument_list,
            },
        }
        # Upstox v3 expects the subscription as a binary frame
        await ws.send(json.dumps(payload).encode("utf-8"))

    async def _handle_message(self, raw: bytes | str):
        try:
            if isinstance(raw, str):
                return  # v3 only sends binary protobuf frames

            from upstox_client.feeder.proto import MarketDataFeedV3_pb2
            feed_response = MarketDataFeedV3_pb2.FeedResponse.FromString(raw)
            data_dict = json_format.MessageToDict(feed_response)

            ts = datetime.now(timezone.utc)
            for instrument_key, feed_data in data_dict.get("feeds", {}).items():
                symbol = _INSTRUMENT_MAP.get(instrument_key)
                if not symbol:
                    continue

                # LTPC mode: price is at feed_data["ltpc"]["ltp"]
                # Full mode for indices: feed_data["fullFeed"]["indexFF"]["ltpc"]["ltp"]
                ltpc = feed_data.get("ltpc") or (
                    feed_data.get("fullFeed", {}).get("indexFF", {}).get("ltpc") or
                    feed_data.get("fullFeed", {}).get("marketFF", {}).get("ltpc")
                )

                if not ltpc:
                    continue

                price = ltpc.get("ltp")
                if price:
                    LIVE_PRICES[symbol] = float(price)
                    finalized = process_tick(symbol, float(price), 0.0, ts)
                    if finalized:
                        asyncio.create_task(_save_candle_to_db(symbol, finalized))

        except Exception as e:
            logger.debug("Failed to parse WebSocket message", error=str(e))

    async def disconnect(self):
        self._running = False
        if self._ws:
            await self._ws.close()


# Singleton instance
ws_client = UpstoxWebSocketClient()
