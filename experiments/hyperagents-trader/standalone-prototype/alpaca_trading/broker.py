"""Thin wrapper around Alpaca's paper-trading REST API.

Every call goes through `_headers()`/`_trading_url()`/`_data_url()`, and every
public entry point calls `config.assert_paper_endpoint()` first, so this
module cannot silently be pointed at a live account.
"""
import time

import requests

from alpaca_trading import config


def _headers():
    return {
        "APCA-API-KEY-ID": config.ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": config.ALPACA_SECRET_KEY,
    }


def _trading_url(path):
    return f"{config.ALPACA_BASE_URL}/v2{path}"


def _data_url(path):
    return f"{config.ALPACA_DATA_URL}/v2{path}"


def _request(method, url, **kwargs):
    config.assert_paper_endpoint()
    resp = requests.request(method, url, headers=_headers(), timeout=30, **kwargs)
    if resp.status_code >= 400:
        raise RuntimeError(f"Alpaca API error {resp.status_code} for {method} {url}: {resp.text}")
    return resp.json() if resp.text else {}


def get_account():
    return _request("GET", _trading_url("/account"))


def get_positions():
    return _request("GET", _trading_url("/positions"))


def get_clock():
    return _request("GET", _trading_url("/clock"))


def submit_order(symbol, qty, side, order_type="market", time_in_force="day"):
    """Submit a paper order. `side` is 'buy' or 'sell'. `qty` must be > 0."""
    assert side in ("buy", "sell"), f"invalid side: {side}"
    assert qty > 0, f"qty must be positive, got {qty}"
    payload = {
        "symbol": symbol,
        "qty": str(qty),
        "side": side,
        "type": order_type,
        "time_in_force": time_in_force,
    }
    return _request("POST", _trading_url("/orders"), json=payload)


def get_portfolio_history(period="1M", timeframe="1D"):
    """Equity curve for the paper account: {"timestamp": [...], "equity": [...]}."""
    return _request(
        "GET",
        _trading_url("/account/portfolio/history"),
        params={"period": period, "timeframe": timeframe},
    )


def get_daily_bars(symbol, start, end, retries=3):
    """Historical daily bars for `symbol` between ISO dates `start` and `end`.

    Returns a list of {"t": iso_timestamp, "o", "h", "l", "c", "v"} dicts, oldest first.
    Uses the free IEX feed, which paper-trading keys have access to.
    """
    config.assert_paper_endpoint()
    all_bars = []
    page_token = None
    for attempt in range(retries):
        try:
            while True:
                params = {
                    "timeframe": "1Day",
                    "start": start,
                    "end": end,
                    "limit": 1000,
                    "feed": "iex",
                    "adjustment": "split",
                }
                if page_token:
                    params["page_token"] = page_token
                resp = requests.get(
                    _data_url(f"/stocks/{symbol}/bars"),
                    headers=_headers(),
                    params=params,
                    timeout=30,
                )
                if resp.status_code >= 400:
                    raise RuntimeError(f"Alpaca data API error {resp.status_code}: {resp.text}")
                data = resp.json()
                all_bars.extend(data.get("bars", []))
                page_token = data.get("next_page_token")
                if not page_token:
                    break
            return all_bars
        except (requests.RequestException, RuntimeError):
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    return all_bars
