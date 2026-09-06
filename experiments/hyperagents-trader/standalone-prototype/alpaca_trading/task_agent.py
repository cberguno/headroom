"""The strategy the self-improvement loop evolves.

Contract (do not change the signature — self_improve.py and run_episode.py
both call this exact function):

    decide(context: dict) -> dict

`context` contains everything the strategy is allowed to see (see
backtest.py / run_episode.py for the exact fields: cash, equity, current
positions, per-symbol price + moving averages, and the risk limits that will
be enforced on whatever this returns regardless). It must return
{"orders": [{"symbol": str, "side": "buy"|"sell", "qty": int}, ...], "rationale": str}.

This file must not do network I/O, file I/O, or subprocess calls — the
self-improvement loop's safety check (self_improve.py:validate_strategy_source)
statically rejects any candidate that imports or calls into those. Keep the
logic here pure: read `context`, return an orders list.

Baseline strategy: a simple SMA(5)/SMA(20) crossover, one unit of the
narrowest affordable size per signal, capped by the risk limits below.
"""


def decide(context):
    cash = context["cash"]
    equity = context["equity"]
    positions = context["positions"]
    market_data = context["market_data"]
    max_position_pct = context["risk_limits"]["max_position_pct"]
    max_orders = context["risk_limits"]["max_orders_per_step"]

    orders = []
    reasons = []

    for symbol, data in market_data.items():
        if len(orders) >= max_orders:
            break

        price = data.get("price")
        sma_5 = data.get("sma_5")
        sma_20 = data.get("sma_20")
        if not price or not sma_5 or not sma_20:
            continue

        held_qty = positions.get(symbol, 0)
        max_position_value = equity * max_position_pct

        # Golden cross: short-term average above long-term average -> buy signal.
        if sma_5 > sma_20 and held_qty == 0:
            budget = min(cash, max_position_value)
            qty = int(budget // price)
            if qty > 0:
                orders.append({"symbol": symbol, "side": "buy", "qty": qty})
                reasons.append(f"{symbol}: SMA5>{'SMA20'} golden cross, buying {qty}")

        # Death cross while holding -> exit.
        elif sma_5 < sma_20 and held_qty > 0:
            orders.append({"symbol": symbol, "side": "sell", "qty": held_qty})
            reasons.append(f"{symbol}: SMA5<SMA20 death cross, selling {held_qty}")

    return {
        "orders": orders,
        "rationale": "; ".join(reasons) if reasons else "no crossover signals",
    }
