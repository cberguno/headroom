import os

from dotenv import load_dotenv

load_dotenv()

PAPER_HOST = "paper-api.alpaca.markets"


class ConfigError(RuntimeError):
    pass


def _env_float(name, default):
    val = os.environ.get(name)
    return float(val) if val else default


def _env_int(name, default):
    val = os.environ.get(name)
    return int(val) if val else default


def _env_bool(name, default):
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
ALPACA_DATA_URL = "https://data.alpaca.markets"

LLM_MODEL = os.environ.get("TRADER_LLM_MODEL", "gpt-4o-mini")

WATCHLIST = [s.strip().upper() for s in os.environ.get(
    "TRADER_WATCHLIST", "SPY,QQQ,AAPL,MSFT,NVDA"
).split(",") if s.strip()]
BENCHMARK = os.environ.get("TRADER_BENCHMARK", "SPY").strip().upper()
STARTING_CASH = _env_float("TRADER_STARTING_CASH", 100_000.0)

MAX_POSITION_PCT = _env_float("TRADER_MAX_POSITION_PCT", 0.2)
MAX_ORDERS_PER_STEP = _env_int("TRADER_MAX_ORDERS_PER_STEP", 3)
ALLOW_SHORT = _env_bool("TRADER_ALLOW_SHORT", False)  # not implemented regardless; see run_episode.py

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")


def assert_paper_endpoint():
    """Hard safety gate: refuse to do anything if pointed at a live trading endpoint."""
    if PAPER_HOST not in ALPACA_BASE_URL:
        raise ConfigError(
            f"ALPACA_BASE_URL={ALPACA_BASE_URL!r} does not look like the Alpaca paper "
            f"endpoint ({PAPER_HOST}). This project only supports paper trading — "
            "refusing to continue. Use your paper-trading API keys and base URL."
        )
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        raise ConfigError(
            "ALPACA_API_KEY / ALPACA_SECRET_KEY are not set. Copy .env.example to .env "
            "and fill in your paper-trading keys from "
            "https://app.alpaca.markets/paper/dashboard/overview"
        )
