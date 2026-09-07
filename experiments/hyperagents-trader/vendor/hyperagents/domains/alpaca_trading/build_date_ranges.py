"""Regenerates date_ranges.json and data_cache/*.csv from real daily bars.

This is what actually produced the committed date_ranges.json — run it again
only if you deliberately want to roll the train/val/test window forward
(e.g. months from now). Re-running it changes what "test" means, so don't
run it to escape a bad test-set result.

Prefers Alpaca's data API (if ALPACA_API_KEY/ALPACA_SECRET_KEY are set and
ALPACA_BASE_URL is the paper endpoint); falls back to Yahoo Finance's
public chart API (no key required) otherwise. Both return real market data,
never synthetic prices.
"""
import argparse
import csv
import json
import os
import subprocess
from datetime import datetime, timezone

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_cache")
RANGES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "date_ranges.json")
SYMBOLS = ["QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "SPY"]


def _fetch_yahoo(symbol, start_date, end_date):
    period1 = int(datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    period2 = int(datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={period1}&period2={period2}&interval=1d"
    )
    result = subprocess.run(
        ["curl", "-s", "-A", "Mozilla/5.0", "--max-time", "20", url],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)["chart"]["result"][0]
    timestamps = data["timestamp"]
    closes = data["indicators"]["quote"][0]["close"]
    adjclose = data.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", closes)
    rows = []
    for ts, c, ac in zip(timestamps, closes, adjclose):
        price = ac if ac is not None else c
        if price is None:
            continue
        date = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        rows.append((date, price))
    return rows


def _fetch_alpaca(symbol, start_date, end_date):
    from domains.alpaca_trading import broker  # only imported if Alpaca creds are configured
    bars = broker.get_daily_bars(symbol, start_date, end_date)
    return [(b["t"][:10], b["c"]) for b in bars]


def fetch_and_cache(symbol, start_date, end_date):
    use_alpaca = bool(os.environ.get("ALPACA_API_KEY")) and bool(os.environ.get("ALPACA_SECRET_KEY"))
    rows = _fetch_alpaca(symbol, start_date, end_date) if use_alpaca else _fetch_yahoo(symbol, start_date, end_date)
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{symbol.lower()}.csv")
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "close"])
        writer.writerows(rows)
    return rows, ("alpaca" if use_alpaca else "yahoo_finance_chart_api")


def build(as_of, warmup_days=20, train_days=180, val_days=40, test_days=36,
          lookback_start="2025-08-01"):
    all_rows = {}
    source_used = None
    for symbol in SYMBOLS:
        rows, source_used = fetch_and_cache(symbol, lookback_start, as_of)
        all_rows[symbol] = rows

    dates = [d for d, _ in all_rows["SPY"]]  # SPY trades every session; use it as the calendar
    total_needed = warmup_days + train_days + val_days + test_days
    if len(dates) < total_needed:
        raise RuntimeError(
            f"Only {len(dates)} trading days available between {lookback_start} and {as_of}, "
            f"need {total_needed}. Pick an earlier lookback_start."
        )
    dates = dates[-total_needed:]  # anchor the split to end at as_of

    def bounds(start_idx, end_idx):
        return {"start": dates[start_idx], "end": dates[end_idx], "trading_days": end_idx - start_idx + 1}

    ranges = {
        "_comment": (
            "Fixed chronological splits derived from real daily bars cached in data_cache/ "
            "(source: see 'source' field, fetched at 'fetched_at'). Regenerate with "
            "build_date_ranges.py only if you deliberately want to roll the window forward "
            "-- do not edit by hand."
        ),
        "source": source_used,
        "fetched_at": as_of,
        "symbols": SYMBOLS,
        "warmup": bounds(0, warmup_days - 1),
        "train": bounds(warmup_days, warmup_days + train_days - 1),
        "val": bounds(warmup_days + train_days, warmup_days + train_days + val_days - 1),
        "test": bounds(warmup_days + train_days + val_days, total_needed - 1),
    }
    with open(RANGES_PATH, "w") as f:
        json.dump(ranges, f, indent=2)
        f.write("\n")
    print(json.dumps(ranges, indent=2))
    return ranges


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=datetime.utcnow().date().isoformat(),
                         help="Last date of the test window (default: today, UTC)")
    parser.add_argument("--lookback-start", default="2025-08-01")
    args = parser.parse_args()
    build(as_of=args.as_of, lookback_start=args.lookback_start)
