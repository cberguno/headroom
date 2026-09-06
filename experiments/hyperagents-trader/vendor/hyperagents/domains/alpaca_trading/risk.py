"""Hard risk limits enforced on every order regardless of what the agent
proposed. This runs OUTSIDE the sandboxed decision process (see sandbox.py)
in the trusted caller, so it cannot be bypassed by anything the agent's code
does -- only by editing this file itself, which is why it lives outside the
domain's editable-strategy surface (see eval.py / sandbox.py for what is and
isn't exposed to the meta-agent).
"""
from domains.alpaca_trading import config


def clamp_orders(proposed_orders, cash, equity, positions, prices,
                  max_position_pct=None, max_orders=None):
    """
    proposed_orders: [{"symbol", "side", "qty"}, ...]
    positions: {symbol: qty currently held}
    prices: {symbol: last price}

    Returns a sanitized order list: no shorting, no order exceeding
    max_position_pct of equity, no spending beyond available cash, at most
    max_orders total.
    """
    max_position_pct = config.MAX_POSITION_PCT if max_position_pct is None else max_position_pct
    max_orders = config.MAX_ORDERS_PER_STEP if max_orders is None else max_orders

    safe_orders = []
    remaining_cash = cash
    seen = set()

    for order in proposed_orders or []:
        if len(safe_orders) >= max_orders:
            break

        symbol = order.get("symbol")
        side = order.get("side")
        qty = order.get("qty")

        if symbol is None or side not in ("buy", "sell") or symbol not in prices:
            continue
        if (symbol, side) in seen:
            continue
        try:
            qty = int(qty)
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue

        price = prices[symbol]
        held = positions.get(symbol, 0)

        if side == "sell":
            qty = min(qty, held)  # never short
            if qty <= 0:
                continue
        else:
            held_value = held * price
            max_position_value = equity * max_position_pct
            room_left = max(0.0, max_position_value - held_value)
            affordable_qty = int(min(room_left, remaining_cash) // price)
            qty = min(qty, affordable_qty)
            if qty <= 0:
                continue
            remaining_cash -= qty * price

        safe_orders.append({"symbol": symbol, "side": side, "qty": qty})
        seen.add((symbol, side))

    return safe_orders
