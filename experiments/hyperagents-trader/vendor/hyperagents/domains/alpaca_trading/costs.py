"""Transaction cost model applied to every simulated fill. Alpaca charges
zero commission on US equities, so COMMISSION_BPS defaults to 0; SLIPPAGE_BPS
models bid-ask spread / market impact against the trader on every fill.
Real paper-account fills (run_live_episode.py) get Alpaca's actual fill
price instead -- this model is for the offline backtest only.
"""
from domains.alpaca_trading import config


def fill_price(side, quote_price, commission_bps=None, slippage_bps=None):
    """Returns the effective per-share price after slippage (commission is
    applied separately as a flat amount in apply_costs, since Alpaca's is 0
    but a nonzero rate is typically a flat fee or per-share, not a price
    adjustment)."""
    slippage_bps = config.SLIPPAGE_BPS if slippage_bps is None else slippage_bps
    slip = slippage_bps / 10_000.0
    if side == "buy":
        return quote_price * (1 + slip)  # you pay slightly more
    return quote_price * (1 - slip)  # you receive slightly less


def commission(notional, commission_bps=None):
    commission_bps = config.COMMISSION_BPS if commission_bps is None else commission_bps
    return abs(notional) * (commission_bps / 10_000.0)
