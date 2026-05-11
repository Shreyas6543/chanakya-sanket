"""
Download NSE F&O UDiFF Bhavcopy data for NIFTY & BANKNIFTY options.
Covers May 2025 - May 2026 (our backtest window).

Usage:
    python scripts/download_nse_oi.py

Output:
    data/nse_oi/YYYY-MM-DD.csv  — one file per trading day
    Columns: date, symbol, expiry, option_type, strike, oi, spot
"""

import io
import time
import zipfile
import requests
import pandas as pd
from datetime import date, timedelta
from pathlib import Path

OUTPUT_DIR = Path("data/nse_oi")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

START_DATE = date(2025, 5, 1)
END_DATE   = date(2026, 5, 12)

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


def download_day(d: date) -> pd.DataFrame | None:
    url = (
        f"https://nsearchives.nseindia.com/content/fo/"
        f"BhavCopy_NSE_FO_0_0_0_{d.strftime('%Y%m%d')}_F_0000.csv.zip"
    )
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code == 200 and len(resp.content) > 10_000:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                with z.open(z.namelist()[0]) as f:
                    return pd.read_csv(f)
    except Exception:
        pass
    return None


def extract_oi(df: pd.DataFrame, d: date) -> pd.DataFrame | None:
    """
    UDiFF format columns we need:
      FinInstrmTp  — 'IDO' = index derivatives options (NIFTY, BANKNIFTY)
      TckrSymb     — 'NIFTY' / 'BANKNIFTY'
      StrkPric     — strike price
      OptnTp       — 'CE' / 'PE'
      OpnIntrst    — open interest (contracts)
      XpryDt       — expiry date
      UndrlygPric  — underlying spot price
    """
    idx_opts = df[
        (df["FinInstrmTp"] == "IDO") &
        (df["TckrSymb"].isin(SYMBOLS)) &
        (df["OptnTp"].isin(["CE", "PE"]))
    ].copy()

    if idx_opts.empty:
        return None

    idx_opts["date"] = d.isoformat()
    result = idx_opts[[
        "date", "TckrSymb", "XpryDt", "OptnTp", "StrkPric", "OpnIntrst", "UndrlygPric"
    ]].copy()
    result.columns = ["date", "symbol", "expiry", "option_type", "strike", "oi", "spot"]
    result["oi"] = pd.to_numeric(result["oi"], errors="coerce").fillna(0).astype(int)
    return result


def main():
    warm_up()
    print(f"Downloading NSE F&O OI: {START_DATE} → {END_DATE}")
    print(f"Output: {OUTPUT_DIR.resolve()}\n")

    days = list(trading_days(START_DATE, END_DATE))
    success, skipped, missed = 0, 0, 0

    for i, d in enumerate(days):
        out_path = OUTPUT_DIR / f"{d.isoformat()}.csv"
        if out_path.exists():
            skipped += 1
            continue

        raw = download_day(d)
        if raw is None:
            print(f"  MISS  {d}  (holiday or not in archive)")
            missed += 1
            time.sleep(0.3)
            continue

        oi = extract_oi(raw, d)
        if oi is None or oi.empty:
            print(f"  WARN  {d}  (no NIFTY/BN IDO rows found)")
            missed += 1
            time.sleep(0.3)
            continue

        oi.to_csv(out_path, index=False)
        nifty_rows = len(oi[oi["symbol"] == "NIFTY"])
        bn_rows    = len(oi[oi["symbol"] == "BANKNIFTY"])
        print(f"  OK    {d}  NIFTY={nifty_rows} BN={bn_rows} rows")
        success += 1

        time.sleep(0.5)

        if (i + 1) % 50 == 0:
            warm_up()

    print(f"\nDone. Success={success}  Skipped={skipped}  Missed/Holiday={missed}")
    print(f"Files: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
