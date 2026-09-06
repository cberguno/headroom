"""Offline evaluation of a strategy against historical daily bars. No network
calls other than fetching the bars themselves; no orders are ever submitted.
This is what self_improve.py uses to score candidate strategies quickly and
safely before anything is promoted to run_episode.py (which trades for real,
against the paper account).
"""
import importlib.util
import statistics
from datetime import datetime, timedelta

from alpaca_trading import broker, config, reward, risk


def _load_decide(source_path):
    spec = importlib.util.spec_from_file_location("candidate_task_agent", source_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "decide"):
        raise AttributeError(f"{source_path} does not define decide(context)")
    return module.decide


def _fetch_bars(symbols, lookback_days):
    end = datetime.utcnow().date()
    start = end - timedelta(days=int(lookback_days * 1.6) + 10)  # pad for weekends/holidays
    bars_by_symbol = {}
    for symbol in symbols:
        bars = broker.get_daily_bars(symbol, start.isoformat(), end.isoformat())
        bars_by_symbol[symbol] = bars[-lookback_days:] if len(bars) > lookback_days else bars
    return bars_by_symbol


def _indicators_on(closes):
    sma_5 = statistics.mean(closes[-5:]) if len(closes) >= 5 else None
    sma_20 = statistics.mean(closes[-20:]) if len(closes) >= 20 else None
    momentum_10d_pct = ((closes[-1] / closes[-11]) - 1.0) * 100 if len(closes) >= 11 else None
    return {"price": closes[-1], "sma_5": sma_5, "sma_20": sma_20, "momentum_10d_pct": momentum_10d_pct}


def run_backtest(strategy_source_path, watchlist=None, benchmark=None, starting_cash=None,
                  lookback_days=120, warmup_days=20, bars_by_symbol=None, benchmark_bars=None):
    """Simulate `decide()` from `strategy_source_path` over the last `lookback_days`
    of daily bars. Pass `bars_by_symbol`/`benchmark_bars` to reuse already-fetched
    data across multiple candidates in the same generation (saves API calls).

    Returns (fitness_dict, trade_log, equity_curve).
    """
    watchlist = watchlist or config.WATCHLIST
    benchmark = benchmark or config.BENCHMARK
    starting_cash = starting_cash if starting_cash is not None else config.STARTING_CASH

    decide = _load_decide(strategy_source_path)

    if bars_by_symbol is None:
        bars_by_symbol = _fetch_bars(watchlist, lookback_days + warmup_days)
    if benchmark_bars is None:
        benchmark_bars = _fetch_bars([benchmark], lookback_days + warmup_days)[benchmark]

    num_days = min(len(bars) for bars in bars_by_symbol.values())
    if num_days <= warmup_days:
        raise RuntimeError(
            f"Not enough historical data ({num_days} days) for warmup_days={warmup_days}. "
            "Try a shorter warmup or longer lookback."
        )

    cash = starting_cash
    positions = {symbol: 0 for symbol in watchlist}
    equity_curve = []
    trade_log = []

    for day_idx in range(warmup_days, num_days):
        prices = {}
        market_data = {}
        for symbol, bars in bars_by_symbol.items():
            closes = [b["c"] for b in bars[: day_idx + 1]]
            prices[symbol] = closes[-1]
            market_data[symbol] = _indicators_on(closes)

        equity = cash + sum(positions[s] * prices[s] for s in watchlist)

        context = {
            "date": bars_by_symbol[watchlist[0]][day_idx]["t"],
            "cash": cash,
            "equity": equity,
            "positions": dict(positions),
            "watchlist": watchlist,
            "market_data": market_data,
            "risk_limits": {
                "max_position_pct": config.MAX_POSITION_PCT,
                "max_orders_per_step": config.MAX_ORDERS_PER_STEP,
            },
        }

        try:
            result = decide(context) or {}
            proposed = result.get("orders", [])
        except Exception as exc:  # a broken candidate strategy just holds, it doesn't crash the search
            proposed = []
            trade_log.append({"date": context["date"], "error": f"decide() raised: {exc}"})

        safe_orders = risk.clamp_orders(proposed, cash, equity, positions, prices)
        for order in safe_orders:
            symbol, side, qty = order["symbol"], order["side"], order["qty"]
            price = prices[symbol]
            if side == "buy":
                cash -= qty * price
                positions[symbol] += qty
            else:
                cash += qty * price
                positions[symbol] -= qty
            trade_log.append({"date": context["date"], **order, "price": price})

        equity_curve.append(cash + sum(positions[s] * prices[s] for s in watchlist))

    benchmark_closes = [b["c"] for b in benchmark_bars[warmup_days:num_days]]
    fitness = reward.compute_fitness(equity_curve, benchmark_closes)
    return fitness, trade_log, equity_curve
