"""Run the current best strategy once, for real, against your Alpaca PAPER
account. Meant to be invoked on a schedule (e.g. once per trading day) rather
than run in a tight loop — see README.md.

Usage:
    python -m alpaca_trading.run_episode              # one live decision + paper orders
    python -m alpaca_trading.run_episode --dry-run     # decide and log, but submit nothing
    python -m alpaca_trading.run_episode --report-only # just print performance so far
"""
import argparse
import importlib.util
import json
import os
import statistics
from datetime import datetime, timedelta

from alpaca_trading import broker, config, reward, risk

BEST_PATH = os.path.join(config.OUTPUT_DIR, "best", "task_agent.py")
BASELINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "task_agent.py")
EPISODES_DIR = os.path.join(config.OUTPUT_DIR, "episodes")


def _load_decide():
    path = BEST_PATH if os.path.exists(BEST_PATH) else BASELINE_PATH
    spec = importlib.util.spec_from_file_location("live_task_agent", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.decide, path


def _market_data_for(watchlist):
    end = datetime.utcnow().date()
    start = end - timedelta(days=40)
    market_data = {}
    prices = {}
    for symbol in watchlist:
        bars = broker.get_daily_bars(symbol, start.isoformat(), end.isoformat())
        closes = [b["c"] for b in bars]
        if not closes:
            continue
        prices[symbol] = closes[-1]
        market_data[symbol] = {
            "price": closes[-1],
            "sma_5": statistics.mean(closes[-5:]) if len(closes) >= 5 else None,
            "sma_20": statistics.mean(closes[-20:]) if len(closes) >= 20 else None,
            "momentum_10d_pct": ((closes[-1] / closes[-11]) - 1.0) * 100 if len(closes) >= 11 else None,
        }
    return market_data, prices


def run_episode(dry_run=False):
    config.assert_paper_endpoint()
    decide, strategy_path = _load_decide()

    account = broker.get_account()
    positions_raw = broker.get_positions()
    positions = {p["symbol"]: int(float(p["qty"])) for p in positions_raw}

    cash = float(account["cash"])
    equity = float(account["equity"])

    market_data, prices = _market_data_for(config.WATCHLIST)

    context = {
        "date": datetime.utcnow().date().isoformat(),
        "cash": cash,
        "equity": equity,
        "positions": positions,
        "watchlist": config.WATCHLIST,
        "market_data": market_data,
        "risk_limits": {
            "max_position_pct": config.MAX_POSITION_PCT,
            "max_orders_per_step": config.MAX_ORDERS_PER_STEP,
        },
    }

    result = decide(context) or {}
    proposed = result.get("orders", [])
    safe_orders = risk.clamp_orders(proposed, cash, equity, positions, prices)

    submitted = []
    for order in safe_orders:
        if dry_run:
            submitted.append({**order, "dry_run": True})
            continue
        try:
            ack = broker.submit_order(order["symbol"], order["qty"], order["side"])
            submitted.append({**order, "order_id": ack.get("id"), "status": ack.get("status")})
        except Exception as exc:
            submitted.append({**order, "error": str(exc)})

    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "strategy_path": strategy_path,
        "dry_run": dry_run,
        "account_cash": cash,
        "account_equity": equity,
        "rationale": result.get("rationale"),
        "proposed_orders": proposed,
        "submitted_orders": submitted,
    }
    os.makedirs(EPISODES_DIR, exist_ok=True)
    log_path = os.path.join(EPISODES_DIR, f"{log_entry['timestamp'].replace(':', '-')}.json")
    with open(log_path, "w") as f:
        json.dump(log_entry, f, indent=2)

    print(f"Strategy: {strategy_path}")
    print(f"Rationale: {result.get('rationale')}")
    print(f"Orders submitted: {submitted or '(none)'}")
    print(f"Logged to {log_path}")
    return log_entry


def report_only():
    config.assert_paper_endpoint()
    history = broker.get_portfolio_history(period="3M", timeframe="1D")
    equity_curve = [v for v in history.get("equity", []) if v is not None]
    if len(equity_curve) < 2:
        print("Not enough portfolio history yet — run some episodes first.")
        return

    start_ts = history["timestamp"][0]
    end_ts = history["timestamp"][-1]
    start_date = datetime.utcfromtimestamp(start_ts).date().isoformat()
    end_date = datetime.utcfromtimestamp(end_ts).date().isoformat()
    benchmark_bars = broker.get_daily_bars(config.BENCHMARK, start_date, end_date)
    benchmark_curve = [b["c"] for b in benchmark_bars]

    fitness = reward.compute_fitness(equity_curve, benchmark_curve)
    print(f"Paper account performance ({start_date} to {end_date}):")
    print(json.dumps(fitness, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the current best strategy once against the paper account.")
    parser.add_argument("--dry-run", action="store_true", help="Decide and log, but submit no orders")
    parser.add_argument("--report-only", action="store_true", help="Just print performance so far, no decision made")
    args = parser.parse_args()

    if args.report_only:
        report_only()
    else:
        run_episode(dry_run=args.dry_run)
