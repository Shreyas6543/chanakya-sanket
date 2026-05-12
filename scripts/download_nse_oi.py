"""
Download NSE F&O Bhavcopy OI data for NIFTY & BANKNIFTY options.

Handles two NSE archive formats automatically:
  - Pre-April 2022  : old bhavcopy  (archives/fo/bhav/fo{DDMMMYYYY}bhav.csv.zip)
  - April 2022+     : UDiFF format  (content/fo/BhavCopy_NSE_FO_0_0_0_{YYYYMMDD}_F_0000.csv.zip)

Usage:
    python scripts/download_nse_oi.py                         # 2020-01-01 → today
    python scripts/download_nse_oi.py --start 2022-01-01      # custom start
    python scripts/download_nse_oi.py --start 2020-01-01 --end 2026-05-12

Output:
    data/nse_oi/YYYY-MM-DD.csv  — one file per trading day
    Columns: date, symbol, expiry, option_type, strike, oi, spot
             (spot is null for pre-2022 data — not available in old format)
"""

import io
import time
import zipfile
import argparse
import requests
import pandas as pd
from datetime import date, timedelta
from pathlib import Path

OUTPUT_DIR = Path("data/nse_oi")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# NSE switched to UDiFF format around this date
UDIFF_START = date(2022, 4, 1)

SYMBOLS = {"NIFTY", "BANKNIFTY"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.nseindia.com/",
}

session = requests.Session()
session.headers.update(HEADERS)


def warm_up():
    try:
        session.get("https://www.nseindia.com", timeout=10)
        time.sleep(1)
    except Exception:
        pass


def trading_days(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


# ── Old format (pre-April 2022) ───────────────────────────────────────────────

def _url_old(d: date) -> str:
    mon = d.strftime("%b").upper()   # JAN, FEB, ...
    return (
        f"https://nsearchives.nseindia.com/archives/fo/bhav/"
        f"fo{d.day:02d}{mon}{d.year}bhav.csv.zip"
    )


def _extract_old(df: pd.DataFrame, d: date) -> pd.DataFrame | None:
    """
    Old bhavcopy columns:
      SYMBOL, EXPIRY_DT, OPTION_TYP (CE/PE/XX), STRIKE_PR, OPEN_INT
    Futures have OPTION_TYP='XX' — skip them.
    No spot price available.
    """
    opts = df[
        df["SYMBOL"].isin(SYMBOLS) &
        df["OPTION_TYP"].isin(["CE", "PE"])
    ].copy()

    if opts.empty:
        return None

    opts["date"]        = d.isoformat()
    opts["spot"]        = None
    opts["oi"]          = pd.to_numeric(opts["OPEN_INT"], errors="coerce").fillna(0).astype(int)
    opts["strike"]      = pd.to_numeric(opts["STRIKE_PR"], errors="coerce")
    opts["expiry"]      = opts["EXPIRY_DT"]
    opts["symbol"]      = opts["SYMBOL"]
    opts["option_type"] = opts["OPTION_TYP"]

    return opts[["date", "symbol", "expiry", "option_type", "strike", "oi", "spot"]]


# ── UDiFF format (April 2022+) ────────────────────────────────────────────────

def _url_udiff(d: date) -> str:
    return (
        f"https://nsearchives.nseindia.com/content/fo/"
        f"BhavCopy_NSE_FO_0_0_0_{d.strftime('%Y%m%d')}_F_0000.csv.zip"
    )


def _extract_udiff(df: pd.DataFrame, d: date) -> pd.DataFrame | None:
    """
    UDiFF columns:
      FinInstrmTp (IDO = index options), TckrSymb, XpryDt,
      OptnTp (CE/PE), StrkPric, OpnIntrst, UndrlygPric
    """
    opts = df[
        (df["FinInstrmTp"] == "IDO") &
        (df["TckrSymb"].isin(SYMBOLS)) &
        (df["OptnTp"].isin(["CE", "PE"]))
    ].copy()

    if opts.empty:
        return None

    opts["date"]        = d.isoformat()
    opts["symbol"]      = opts["TckrSymb"]
    opts["expiry"]      = opts["XpryDt"]
    opts["option_type"] = opts["OptnTp"]
    opts["strike"]      = pd.to_numeric(opts["StrkPric"], errors="coerce")
    opts["oi"]          = pd.to_numeric(opts["OpnIntrst"], errors="coerce").fillna(0).astype(int)
    opts["spot"]        = pd.to_numeric(opts["UndrlygPric"], errors="coerce")

    return opts[["date", "symbol", "expiry", "option_type", "strike", "oi", "spot"]]


# ── Unified downloader ────────────────────────────────────────────────────────

def download_day(d: date) -> pd.DataFrame | None:
    use_udiff = d >= UDIFF_START
    url       = _url_udiff(d) if use_udiff else _url_old(d)

    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200 or len(resp.content) < 5_000:
            return None
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            with z.open(z.namelist()[0]) as f:
                raw = pd.read_csv(f)
        return _extract_udiff(raw, d) if use_udiff else _extract_old(raw, d)
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="Download NSE F&O OI bhavcopy")
    parser.add_argument("--start", default="2020-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end",   default=date.today().isoformat(), help="End date YYYY-MM-DD")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end   = date.fromisoformat(args.end)

    print(f"Downloading NSE F&O OI: {start} → {end}")
    print(f"Output: {OUTPUT_DIR.resolve()}\n")

    days = list(trading_days(start, end))
    success, skipped, missed = 0, 0, 0

    for i, d in enumerate(days):
        out_path = OUTPUT_DIR / f"{d.isoformat()}.csv"
        if out_path.exists():
            skipped += 1
            continue

        fmt = "UDiFF" if d >= UDIFF_START else "old"
        oi  = download_day(d)

        if oi is None or oi.empty:
            print(f"  MISS  {d}  [{fmt}]  (holiday or not in archive)")
            missed += 1
            time.sleep(0.3)
            continue

        oi.to_csv(out_path, index=False)
        nifty = len(oi[oi["symbol"] == "NIFTY"])
        bn    = len(oi[oi["symbol"] == "BANKNIFTY"])
        print(f"  OK    {d}  [{fmt}]  NIFTY={nifty} BN={bn} rows")
        success += 1
        time.sleep(0.5)

        if (i + 1) % 50 == 0:
            warm_up()

    print(f"\nDone. Success={success}  Skipped={skipped}  Missed/Holiday={missed}")
    print(f"Total files in {OUTPUT_DIR}: {len(list(OUTPUT_DIR.glob('*.csv')))}")


if __name__ == "__main__":
    main()
