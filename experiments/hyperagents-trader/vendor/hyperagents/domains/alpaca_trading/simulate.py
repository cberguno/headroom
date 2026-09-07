"""Chronological backtest engine for the alpaca_trading domain. Reads only
the committed data_cache/*.csv (real historical daily bars) -- no network
access, no Alpaca credentials needed. Calls the given TaskAgent's
.forward(inputs) once per trading day, in date order, carrying portfolio
state (cash/positions) forward, exactly like a real trading session would --
never using a day's own future close to make that day's decision, and never
looking past the split boundary being evaluated.
"""
import csv
import os
import statistics

from domains.alpaca_trading import config, costs, risk


def _load_series(symbol):
    path = os.path.join(config.CACHE_DIR, f"{symbol.lower()}.csv")
    with open(path) as f:
        reader = csv.DictReader(f)
        return [(row["date"], float(row["close"])) for row in reader]


def _load_all_series():
    return {symbol: _load_series(symbol) for symbol in config.ALL_SYMBOLS}


def _indicators(closes):
    sma_5 = statistics.mean(closes[-5:]) if len(closes) >= 5 else None
    sma_20 = statistics.mean(closes[-20:]) if len(closes) >= 20 else None
    momentum_10d_pct = ((closes[-1] / closes[-11]) - 1.0) * 100 if len(closes) >= 11 else None
    return {"price": closes[-1], "sma_5": sma_5, "sma_20": sma_20, "momentum_10d_pct": momentum_10d_pct}


def _dates_in_range(dates, start, end):
    return [i for i, d in enumerate(dates) if start <= d <= end]


def run_simulation(agent, split, num_days=-1, log_fn=None):
    """
    agent: an instantiated TaskAgent (has .forward(inputs) -> (prediction, msg_history))
    split: "train", "val", or "test" -- looked up in date_ranges.json
    num_days: cap on scored days evaluated (for staged/quick eval); -1 = all

    Returns (fitness_inputs, trade_log) where fitness_inputs is
    {"equity_curve", "benchmark_curve", "equal_weight_curve"} ready for
    reward.compute_fitness, and trade_log is a list of per-day records
    (including any error, e.g. an unparseable LLM response -- which counts
    as a hold, not a crash).
    """
    log_fn = log_fn or (lambda msg: None)
    ranges = config.DATE_RANGES
    period = ranges[split]
    all_series = _load_all_series()

    dates = [d for d, _ in all_series[config.BENCHMARK]]
    closes_by_symbol = {sym: [c for _, c in series] for sym, series in all_series.items()}

    scored_idx = _dates_in_range(dates, period["start"], period["end"])
    if num_days is not None and num_days > 0:
        scored_idx = scored_idx[:num_days]
    if not scored_idx:
        raise RuntimeError(f"No scored days found for split={split} in range {period}")

    cash = config.STARTING_CASH
    positions = {symbol: 0 for symbol in config.WATCHLIST}
    equity_curve, benchmark_curve, equal_weight_curve = [], [], []
    trade_log = []

    # Equal-weight buy-and-hold baseline: buy each watchlist symbol equally on day 0.
    ew_cash = config.STARTING_CASH
    first_prices = {sym: closes_by_symbol[sym][scored_idx[0]] for sym in config.WATCHLIST}
    ew_shares = {sym: (ew_cash / len(config.WATCHLIST)) / first_prices[sym] for sym in config.WATCHLIST}
    ew_cash = 0.0

    benchmark_shares = config.STARTING_CASH / closes_by_symbol[config.BENCHMARK][scored_idx[0]]

    for day_num, i in enumerate(scored_idx):
        prices = {sym: closes_by_symbol[sym][i] for sym in config.WATCHLIST}
        market_data = {sym: _indicators(closes_by_symbol[sym][: i + 1]) for sym in config.WATCHLIST}
        equity = cash + sum(positions[s] * prices[s] for s in config.WATCHLIST)

        inputs = {
            "domain": "alpaca_trading",
            "date": dates[i],
            "cash": round(cash, 2),
            "equity": round(equity, 2),
            "positions": dict(positions),
            "watchlist": config.WATCHLIST,
            "market_data": market_data,
            "risk_limits": {
                "max_position_pct": config.MAX_POSITION_PCT,
                "max_orders_per_step": config.MAX_ORDERS_PER_STEP,
            },
        }

        try:
            prediction, _ = agent.forward(inputs)
            proposed = prediction.get("orders", []) if isinstance(prediction, dict) else []
        except Exception as exc:
            proposed = []
            trade_log.append({"date": dates[i], "error": f"agent.forward raised: {exc}"})
            log_fn(f"[{dates[i]}] agent.forward raised: {exc}")

        safe_orders = risk.clamp_orders(proposed, cash, equity, positions, prices)
        for order in safe_orders:
            symbol, side, qty = order["symbol"], order["side"], order["qty"]
            quote = prices[symbol]
            fill = costs.fill_price(side, quote)
            notional = qty * fill
            fee = costs.commission(notional)
            if side == "buy":
                cash -= (notional + fee)
                positions[symbol] += qty
            else:
                cash += (notional - fee)
                positions[symbol] -= qty
            trade_log.append({"date": dates[i], **order, "quote_price": quote, "fill_price": fill, "fee": fee})

        equity_curve.append(cash + sum(positions[s] * prices[s] for s in config.WATCHLIST))
        equal_weight_curve.append(sum(ew_shares[s] * prices[s] for s in config.WATCHLIST) + ew_cash)
        benchmark_curve.append(benchmark_shares * closes_by_symbol[config.BENCHMARK][i])

    return (
        {"equity_curve": equity_curve, "benchmark_curve": benchmark_curve, "equal_weight_curve": equal_weight_curve},
        trade_log,
    )
