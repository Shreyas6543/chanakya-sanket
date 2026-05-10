import asyncio
import json
import structlog
import websockets
from datetime import datetime

from app.config import get_settings
from app.market_data.candle_processor import process_tick

logger = structlog.get_logger()
settings = get_settings()

UPSTOX_WS_URL = "wss://api.upstox.com/v2/feed/market-data-feed"


class UpstoxWebSocketClient:
    def __init__(self, on_tick_callbacks: list = None):
        self._callbacks = on_tick_callbacks or []
        self._running = False
        self._ws = None

    def add_callback(self, cb):
        self._callbacks.append(cb)

    async def connect(self):
        if not settings.upstox_access_token:
            logger.error("Upstox access token not set — cannot connect WebSocket")
            return

        headers = {
            "Authorization": f"Bearer {settings.upstox_access_token}",
            "Api-Version": "2.0",
        }

        self._running = True
        while self._running:
            try:
                logger.info("Connecting to Upstox WebSocket...")
                async with websockets.connect(UPSTOX_WS_URL, extra_headers=headers) as ws:
                    self._ws = ws
                    await self._subscribe(ws)
                    logger.info("Upstox WebSocket connected")
                    async for raw_message in ws:
                        await self._handle_message(raw_message)
            except Exception as e:
                logger.warning("WebSocket disconnected, reconnecting in 5s", error=str(e))
                await asyncio.sleep(5)

    async def _subscribe(self, ws):
        instruments = settings.instrument_list
        payload = {
            "guid": "trading-engine",
            "method": "sub",
            "data": {
                "mode": "full",
                "instrumentKeys": instruments,
            },
        }
        await ws.send(json.dumps(payload))

    async def _handle_message(self, raw: bytes | str):
        try:
            # Upstox v2 sends protobuf — for now handle as JSON fallback
            # TODO: Integrate upstox-python-sdk proto decoder
            data = json.loads(raw) if isinstance(raw, str) else {}
            feeds = data.get("feeds", {})

            for instrument_key, feed_data in feeds.items():
                symbol = instrument_key.split("|")[-1].replace(" ", "").upper()
                ltpc = feed_data.get("ff", {}).get("marketFF", {}).get("ltpc", {})
                price = ltpc.get("ltp")
                volume = feed_data.get("ff", {}).get("marketFF", {}).get("vtt", 0)

                if price:
                    ts = datetime.utcnow()
                    process_tick(symbol, float(price), float(volume), ts)

                    for cb in self._callbacks:
                        await cb(symbol, float(price), ts)

        except Exception as e:
            logger.debug("Failed to parse WebSocket message", error=str(e))

    async def disconnect(self):
        self._running = False
        if self._ws:
            await self._ws.close()


# Singleton instance
ws_client = UpstoxWebSocketClient()
