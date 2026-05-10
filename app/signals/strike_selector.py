from datetime import date, timedelta
from app.config import get_settings

settings = get_settings()


def _interval(symbol: str) -> int:
    return settings.nifty_strike_interval if symbol.upper() == "NIFTY" else settings.banknifty_strike_interval


def get_atm_strike(spot_price: float, symbol: str) -> float:
    interval = _interval(symbol)
    return round(spot_price / interval) * interval


def select_strike(spot_price: float, symbol: str, confidence: int) -> float:
    """
    Strike selection based on confidence score:
    - 65–75 → ATM
    - 75–85 → 1 strike OTM
    - >85   → 2 strikes OTM
    """
    interval = _interval(symbol)
    atm = get_atm_strike(spot_price, symbol)

    if confidence < 75:
        return atm
    elif confidence < 85:
        return atm + interval
    else:
        return atm + (2 * interval)


def select_expiry(symbol: str, reference_date: date | None = None) -> str:
    """
    Select nearest weekly expiry.
    NIFTY = Thursday, BANKNIFTY = Wednesday
    Switches to next week if expiry is within EXPIRY_MIN_DAYS days.
    """
    today = reference_date or date.today()

    # Weekday: Monday=0, Tuesday=1, Wednesday=2, Thursday=3
    expiry_weekday = 3 if symbol.upper() == "NIFTY" else 2

    days_ahead = (expiry_weekday - today.weekday()) % 7
    nearest_expiry = today + timedelta(days=days_ahead)

    if days_ahead <= settings.expiry_min_days:
        nearest_expiry = nearest_expiry + timedelta(weeks=1)

    return nearest_expiry.strftime("%Y-%m-%d")
