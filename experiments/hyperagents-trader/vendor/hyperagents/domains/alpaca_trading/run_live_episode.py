"""Runs the current best task_agent.py once against a REAL Alpaca PAPER
account. This is the only script in this domain that holds Alpaca
credentials, and the only one that can place an order -- self-improvement
(self_improve or generate_loop) never calls this; it only ever backtests
against data_cache/*.csv.

Safety layers, in order:
1. safety_check.check_task_agent_source -- static AST pre-filter (cheap,
   not sufficient alone).
2. sandbox.smoke_test_import -- zero-network, zero-credential import check.
3. sandbox.run_task_agent_decision -- the actual decision call runs in a
   resource-limited child process whose environment holds the LLM key(s)
   but NEVER the Alpaca credentials. This process's return value is treated
   as inert data (parsed JSON), never executed.
4. risk.clamp_orders -- hard position/cash/order-count limits applied in
   THIS (trusted) process, regardless of what the child proposed.
5. broker.submit_order -- only this trusted process ever holds
   ALPACA_API_KEY/ALPACA_SECRET_KEY, and only after steps 1-4 pass.

Usage:
    python -m domains.alpaca_trading.run_live_episode [--dry-run] [--task-agent-path PATH]
"""
import argparse
import json
import os
import statistics
from datetime import datetime, timedelta

from domains.alpaca_trading import broker, config, integrity, risk, safety_check, sandbox

DEFAULT_TASK_AGENT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "task_agent.py")
EPISODES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_episodes")


def _llm_env():
    """Only the LLM credentials the child needs -- never Alpaca's."""
    keys = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "PATH")
    return {k: os.environ[k] for k in keys if k in os.environ}


def _market_data_for(watchlist):
    end = datetime.utcnow().date()
    start = end - timedelta(days=40)
    market_data, prices = {}, {}
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


def run_live_episode(task_agent_path=DEFAULT_TASK_AGENT, dry_run=False):
    broker.assert_paper_endpoint()
    integrity.verify_or_raise()  # refuses to run if risk.py/broker.py/sandbox.py/safety_check.py were altered

    with open(task_agent_path) as f:
        source = f.read()
    ok, reason = safety_check.check_task_agent_source(source)
    if not ok:
        raise RuntimeError(f"refusing to run: static safety check failed: {reason}")
    sandbox.smoke_test_import(task_agent_path)

    account = broker.get_account()
    positions_raw = broker.get_positions()
    positions = {p["symbol"]: int(float(p["qty"])) for p in positions_raw}
    cash = float(account["cash"])
    equity = float(account["equity"])

    market_data, prices = _market_data_for(config.WATCHLIST)

    inputs = {
        "domain": "alpaca_trading",
        "date": datetime.utcnow().date().isoformat(),
        "cash": cash,
        "equity": equity,
        "positions": positions,
        "watchlist": config.WATCHLIST,
        "market_data": market_data,
        "risk_limits": {"max_position_pct": config.MAX_POSITION_PCT, "max_orders_per_step": config.MAX_ORDERS_PER_STEP},
    }

    prediction = sandbox.run_task_agent_decision(task_agent_path, inputs, config.LLM_MODEL, _llm_env())
    proposed = prediction.get("orders", []) if isinstance(prediction, dict) else []
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
        "task_agent_path": task_agent_path,
        "dry_run": dry_run,
        "account_cash": cash,
        "account_equity": equity,
        "rationale": prediction.get("rationale") if isinstance(prediction, dict) else None,
        "proposed_orders": proposed,
        "submitted_orders": submitted,
    }
    os.makedirs(EPISODES_DIR, exist_ok=True)
    log_path = os.path.join(EPISODES_DIR, f"{log_entry['timestamp'].replace(':', '-')}.json")
    with open(log_path, "w") as f:
        json.dump(log_entry, f, indent=2)

    print(f"Rationale: {log_entry['rationale']}")
    print(f"Orders submitted: {submitted or '(none)'}")
    print(f"Logged to {log_path}")
    return log_entry


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-agent-path", default=DEFAULT_TASK_AGENT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_live_episode(task_agent_path=args.task_agent_path, dry_run=args.dry_run)
