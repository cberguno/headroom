"""Thin wrapper around Alpaca's paper-trading REST API. Used only by
run_live_episode.py (real paper orders) and, optionally, build_date_ranges.py
(historical bars). The offline backtest/self-improvement path
(simulate.py, eval.py) never imports this module and never needs Alpaca
credentials or network access -- it reads only the committed data_cache/ CSVs.

Every public entry point calls assert_paper_endpoint() first, so this module
cannot silently be pointed at a live account.
"""
import time

import requests

from domains.alpaca_trading import config


class ConfigError(RuntimeError):
    pass


def assert_paper_endpoint():
    if config.PAPER_HOST not in config.ALPACA_BASE_URL:
        raise ConfigError(
            f"ALPACA_BASE_URL={config.ALPACA_BASE_URL!r} does not look like the Alpaca "
            f"paper endpoint ({config.PAPER_HOST}). This domain only supports paper "
            "trading -- refusing to continue."
        )
    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        raise ConfigError(
            "ALPACA_API_KEY / ALPACA_SECRET_KEY are not set. Get paper-trading keys from "
            "https://app.alpaca.markets/paper/dashboard/overview and export them -- "
            "never commit them to the repo."
        )


def _headers():
    return {
        "APCA-API-KEY-ID": config.ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": config.ALPACA_SECRET_KEY,
    }


def _request(method, url, **kwargs):
    assert_paper_endpoint()
    resp = requests.request(method, url, headers=_headers(), timeout=30, **kwargs)
    if resp.status_code >= 400:
        raise RuntimeError(f"Alpaca API error {resp.status_code} for {method} {url}: {resp.text}")
    return resp.json() if resp.text else {}


def get_account():
    return _request("GET", f"{config.ALPACA_BASE_URL}/v2/account")


def get_positions():
    return _request("GET", f"{config.ALPACA_BASE_URL}/v2/positions")


def submit_order(symbol, qty, side, order_type="market", time_in_force="day"):
    assert side in ("buy", "sell"), f"invalid side: {side}"
    assert qty > 0, f"qty must be positive, got {qty}"
    payload = {"symbol": symbol, "qty": str(qty), "side": side, "type": order_type, "time_in_force": time_in_force}
    return _request("POST", f"{config.ALPACA_BASE_URL}/v2/orders", json=payload)


def get_portfolio_history(period="3M", timeframe="1D"):
    return _request(
        "GET", f"{config.ALPACA_BASE_URL}/v2/account/portfolio/history",
        params={"period": period, "timeframe": timeframe},
    )


def get_daily_bars(symbol, start, end, retries=3):
    """Historical daily bars from Alpaca's data API (paper keys have IEX-feed access)."""
    assert_paper_endpoint()
    all_bars, page_token = [], None
    for attempt in range(retries):
        try:
            while True:
                params = {"timeframe": "1Day", "start": start, "end": end, "limit": 1000,
                          "feed": "iex", "adjustment": "split"}
                if page_token:
                    params["page_token"] = page_token
                resp = requests.get(
                    f"{config.ALPACA_DATA_URL}/v2/stocks/{symbol}/bars",
                    headers=_headers(), params=params, timeout=30,
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
