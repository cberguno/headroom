"""The meta-agent loop: propose an edited task_agent.py, validate it, backtest
it, keep it only if it beats the current best. This is the self-improving
part of "self-improving AI trader" — it never places a live order; see
run_episode.py for that.

Usage:
    python -m alpaca_trading.self_improve --generations 6
"""
import argparse
import json
import os
import shutil
from datetime import datetime

from alpaca_trading import backtest, config, llm_client, safety

BASELINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "task_agent.py")
ARCHIVE_DIR = os.path.join(config.OUTPUT_DIR, "archive")
BEST_DIR = os.path.join(config.OUTPUT_DIR, "best")
BEST_PATH = os.path.join(BEST_DIR, "task_agent.py")

META_SYSTEM_PROMPT = """You are a meta-agent improving a Python trading strategy function.

You will be shown the current strategy's full source file, its recent backtest
results, and a sample of trades it made. Propose an improved version of the
ENTIRE file that keeps the exact same interface:

    def decide(context: dict) -> dict

`context` has keys: cash, equity, positions (dict of symbol -> qty held),
watchlist (list of symbols), market_data (dict of symbol -> {price, sma_5,
sma_20, momentum_10d_pct}), risk_limits (max_position_pct, max_orders_per_step).
Return {"orders": [{"symbol", "side": "buy"|"sell", "qty": int}, ...], "rationale": str}.

Hard constraints (violating these gets your proposal rejected before it is
even tested):
- No imports beyond Python's standard math/statistics/itertools/collections
  modules — no os, sys, subprocess, socket, requests, urllib, file I/O, or
  dynamic execution (eval/exec/compile/__import__/open).
- Never propose shorting; short orders are stripped regardless.
- Pure function of `context` — no global mutable state across calls.

Respond with ONLY the full new file content in a single ```python fenced
code block, nothing else.
"""


def _build_meta_prompt(parent_source, parent_fitness, trade_log_sample):
    trades_str = "\n".join(
        f"  {t.get('date')}: {t.get('side','?')} {t.get('qty','?')} {t.get('symbol','?')}"
        + (f" @ {t['price']:.2f}" if "price" in t else f" [{t.get('error')}]")
        for t in trade_log_sample
    ) or "  (no trades)"
    return f"""Current strategy file:
```python
{parent_source}
```

Its backtest results: {json.dumps(parent_fitness)}

Sample of trades it made:
{trades_str}

Propose an improved version."""


def _extract_code(llm_response):
    import re
    match = re.search(r"```python\s*(.*?)```", llm_response, re.DOTALL)
    return match.group(1).strip() if match else llm_response.strip()


def run_self_improvement(generations=6, lookback_days=120, warmup_days=20, model=None):
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    os.makedirs(BEST_DIR, exist_ok=True)

    parent_path = BEST_PATH if os.path.exists(BEST_PATH) else BASELINE_PATH
    with open(parent_path) as f:
        parent_source = f.read()

    # Fetch bars once and reuse for every candidate this run, so comparisons are apples-to-apples.
    bars_by_symbol = backtest._fetch_bars(config.WATCHLIST, lookback_days + warmup_days)
    benchmark_bars = backtest._fetch_bars([config.BENCHMARK], lookback_days + warmup_days)[config.BENCHMARK]

    parent_fitness, parent_trades, _ = backtest.run_backtest(
        parent_path, lookback_days=lookback_days, warmup_days=warmup_days,
        bars_by_symbol=bars_by_symbol, benchmark_bars=benchmark_bars,
    )

    summary = {"started_at": datetime.utcnow().isoformat(), "generations": []}
    gen0_dir = os.path.join(ARCHIVE_DIR, "gen_0")
    os.makedirs(gen0_dir, exist_ok=True)
    shutil.copy(parent_path, os.path.join(gen0_dir, "task_agent.py"))
    with open(os.path.join(gen0_dir, "score.json"), "w") as f:
        json.dump(parent_fitness, f, indent=2)
    summary["generations"].append({"gen": 0, "status": "seed", "fitness": parent_fitness})
    print(f"[gen 0] seed score={parent_fitness['score']} ({parent_fitness})")

    for gen in range(1, generations + 1):
        gen_dir = os.path.join(ARCHIVE_DIR, f"gen_{gen}")
        os.makedirs(gen_dir, exist_ok=True)
        candidate_path = os.path.join(gen_dir, "task_agent.py")

        try:
            prompt = _build_meta_prompt(parent_source, parent_fitness, parent_trades[-15:])
            response = llm_client.complete(META_SYSTEM_PROMPT, prompt, model=model)
            candidate_source = _extract_code(response)
        except Exception as exc:
            print(f"[gen {gen}] meta-agent call failed: {exc}; keeping parent")
            summary["generations"].append({"gen": gen, "status": "meta_agent_error", "error": str(exc)})
            continue

        ok, reason = safety.validate_strategy_source(candidate_source)
        if not ok:
            print(f"[gen {gen}] rejected (safety check): {reason}")
            with open(candidate_path, "w") as f:
                f.write(candidate_source)
            summary["generations"].append({"gen": gen, "status": "rejected_unsafe", "reason": reason})
            continue

        with open(candidate_path, "w") as f:
            f.write(candidate_source)

        try:
            candidate_fitness, candidate_trades, _ = backtest.run_backtest(
                candidate_path, lookback_days=lookback_days, warmup_days=warmup_days,
                bars_by_symbol=bars_by_symbol, benchmark_bars=benchmark_bars,
            )
        except Exception as exc:
            print(f"[gen {gen}] rejected (backtest error): {exc}")
            summary["generations"].append({"gen": gen, "status": "rejected_backtest_error", "error": str(exc)})
            continue

        with open(os.path.join(gen_dir, "score.json"), "w") as f:
            json.dump(candidate_fitness, f, indent=2)

        if candidate_fitness["score"] > parent_fitness["score"]:
            print(f"[gen {gen}] PROMOTED: score {parent_fitness['score']} -> {candidate_fitness['score']}")
            parent_source, parent_fitness, parent_trades = candidate_source, candidate_fitness, candidate_trades
            shutil.copy(candidate_path, BEST_PATH)
            summary["generations"].append({"gen": gen, "status": "promoted", "fitness": candidate_fitness})
        else:
            print(f"[gen {gen}] kept parent: candidate score {candidate_fitness['score']} <= {parent_fitness['score']}")
            summary["generations"].append({"gen": gen, "status": "not_promoted", "fitness": candidate_fitness})

    if not os.path.exists(BEST_PATH):
        shutil.copy(BASELINE_PATH, BEST_PATH)

    summary["finished_at"] = datetime.utcnow().isoformat()
    summary["final_score"] = parent_fitness["score"]
    with open(os.path.join(ARCHIVE_DIR, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nDone. Best strategy so far is at {BEST_PATH} (score={parent_fitness['score']}).")
    print(f"Full lineage: {os.path.join(ARCHIVE_DIR, 'summary.json')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evolve the trading strategy offline against historical data.")
    parser.add_argument("--generations", type=int, default=6)
    parser.add_argument("--lookback-days", type=int, default=120)
    parser.add_argument("--warmup-days", type=int, default=20)
    parser.add_argument("--model", type=str, default=None, help="Override TRADER_LLM_MODEL for this run")
    args = parser.parse_args()
    run_self_improvement(
        generations=args.generations,
        lookback_days=args.lookback_days,
        warmup_days=args.warmup_days,
        model=args.model,
    )
