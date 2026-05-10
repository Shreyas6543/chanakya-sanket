import httpx
import structlog
from app.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

UPSTOX_OPTIONS_URL = "https://api.upstox.com/v2/option/chain"

_prev_oi: dict[str, dict] = {}  # Store previous OI snapshot per symbol


async def fetch_options_chain(symbol: str, expiry: str) -> dict | None:
    """
    Fetch live options chain from Upstox.
    Returns aggregated OI data for use in strategies.
    """
    if not settings.upstox_access_token:
        logger.warning("No access token — skipping options chain fetch")
        return None

    instrument_key = f"NSE_INDEX|{symbol}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                UPSTOX_OPTIONS_URL,
                headers={
                    "Authorization": f"Bearer {settings.upstox_access_token}",
                    "Api-Version": "2.0",
                },
                params={
                    "instrument_key": instrument_key,
                    "expiry_date": expiry,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

        chain = data.get("data", [])
        call_oi = sum(item.get("call_options", {}).get("market_data", {}).get("oi", 0) for item in chain)
        put_oi = sum(item.get("put_options", {}).get("market_data", {}).get("oi", 0) for item in chain)

        prev = _prev_oi.get(symbol, {})
        oi_data = {
            "call_oi": call_oi,
            "put_oi": put_oi,
            "prev_call_oi": prev.get("call_oi", call_oi),
            "prev_put_oi": prev.get("put_oi", put_oi),
        }

        # Store as new previous
        _prev_oi[symbol] = {"call_oi": call_oi, "put_oi": put_oi}

        logger.debug("Options chain fetched", symbol=symbol, call_oi=call_oi, put_oi=put_oi)
        return oi_data

    except Exception as e:
        logger.error("Failed to fetch options chain", symbol=symbol, error=str(e))
        return None
