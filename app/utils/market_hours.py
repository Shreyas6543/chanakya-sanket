from datetime import datetime, date, time
import pytz

IST = pytz.timezone("Asia/Kolkata")

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
SIGNAL_CUTOFF = time(15, 15)  # Stop new signals 15 min before close

# NSE holidays 2025 — update annually
# Source: NSE India official holiday calendar
NSE_HOLIDAYS_2025: set[date] = {
    date(2025, 1, 26),   # Republic Day
    date(2025, 3, 14),   # Holi
    date(2025, 4, 14),   # Dr. Ambedkar Jayanti
    date(2025, 4, 18),   # Good Friday
    date(2025, 5, 1),    # Maharashtra Day
    date(2025, 8, 15),   # Independence Day
    date(2025, 10, 2),   # Gandhi Jayanti
    date(2025, 10, 24),  # Dussehra
    date(2025, 11, 5),   # Diwali Laxmi Pujan
    date(2025, 11, 15),  # Gurunanak Jayanti (placeholder)
    date(2025, 12, 25),  # Christmas
}

NSE_HOLIDAYS_2026: set[date] = {
    date(2026, 1, 26),   # Republic Day
    # TODO: Add full 2026 NSE holiday list from official NSE calendar
}

NSE_HOLIDAYS = NSE_HOLIDAYS_2025 | NSE_HOLIDAYS_2026


def now_ist() -> datetime:
    return datetime.now(IST)


def is_market_open() -> bool:
    now = now_ist()
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    if now.date() in NSE_HOLIDAYS:
        return False
    current_time = now.time()
    return MARKET_OPEN <= current_time <= MARKET_CLOSE


def can_generate_signals() -> bool:
    """Don't generate new signals in last 15 minutes to avoid EOD noise."""
    now = now_ist()
    if not is_market_open():
        return False
    return now.time() <= SIGNAL_CUTOFF


def is_eod() -> bool:
    """True at or after market close — used to expire open signals."""
    now = now_ist()
    return now.time() >= MARKET_CLOSE and now.weekday() < 5
