import json
import os

from dotenv import load_dotenv

# Load .env ourselves rather than relying on agent/llm.py to have done it
# first: this module reads os.environ at import time, and depending on
# import order (e.g. domains.alpaca_trading.eval imports this before
# task_agent.py ever pulls in agent.llm), .env might not be loaded yet --
# which silently sends TRADER_LLM_MODEL's default (gpt-4o-mini) to whatever
# LLM key happens to be missing instead of the one actually configured.
load_dotenv()

_HERE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(_HERE, "date_ranges.json")) as _f:
    DATE_RANGES = json.load(_f)

WATCHLIST = ["QQQ", "AAPL", "MSFT", "NVDA", "AMZN"]  # tradeable universe
BENCHMARK = "SPY"  # buy-and-hold comparison only; not traded by the agent
ALL_SYMBOLS = DATE_RANGES["symbols"]

STARTING_CASH = 100_000.0

# Cheaper default than the "gpt-4o" other domains use, since a full train+val
# pass makes ~220 LLM calls per generation (one per trading day) -- see README
# for the cost math. Override with TRADER_LLM_MODEL (any litellm model id).
LLM_MODEL = os.environ.get("TRADER_LLM_MODEL", "gpt-4o-mini")

# Hard risk limits -- enforced in risk.py regardless of what the strategy proposes.
MAX_POSITION_PCT = 0.2       # max fraction of equity in any one symbol
MAX_ORDERS_PER_STEP = 3      # max orders per decision
ALLOW_SHORT = False          # shorting is never implemented, regardless of this flag

# Cost model. Alpaca charges no commission on US equity trades; slippage models
# bid-ask spread / market impact, applied against the agent on every fill.
COMMISSION_BPS = 0.0
SLIPPAGE_BPS = 5.0

WARMUP_DAYS = DATE_RANGES["warmup"]["trading_days"]  # trailing days needed before the first scored decision

CACHE_DIR = os.path.join(_HERE, "data_cache")

# Alpaca paper trading only -- see broker.py for the hard runtime guard.
PAPER_HOST = "paper-api.alpaca.markets"
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")
def _normalize_base_url(url):
    # broker.py appends /v2/... itself; strip a trailing /v2 so pasting the
    # endpoint exactly as Alpaca's dashboard shows it ("https://paper-api.
    # alpaca.markets/v2") doesn't silently double up into .../v2/v2/account.
    url = url.rstrip("/")
    if url.endswith("/v2"):
        url = url[: -len("/v2")]
    return url


ALPACA_BASE_URL = _normalize_base_url(os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
ALPACA_DATA_URL = "https://data.alpaca.markets"
