"""Entry points dispatched from domains/harness.py and domains/report.py,
exactly like domains/genesis/eval.py's harness_genesis/report_genesis. This
is the real integration surface -- generate_loop.py itself needs no changes
because it always calls domains.harness / domains.report generically (see
generate_loop.py:eval_produced_agent).
"""
import json
import os

from domains.alpaca_trading import config, reward, simulate

_SUBSET_TO_SPLIT = {"": "train", "_train": "train", "_val": "val", "_test": "test"}


def harness_alpaca_trading(agent_path, output_dir, run_id, num_samples=-1, subset="", resume_from=None):
    from domains.harness import load_task_agent  # lazy import avoids a harness<->domain import cycle

    split = _SUBSET_TO_SPLIT.get(subset)
    if split is None:
        raise ValueError(f"unrecognized subset {subset!r} for alpaca_trading")

    output_folder = os.path.abspath(resume_from) if resume_from else os.path.join(output_dir, run_id)
    os.makedirs(output_folder, exist_ok=True)

    TaskAgent = load_task_agent(agent_path)
    agent = TaskAgent(model=config.LLM_MODEL, chat_history_file=os.path.join(output_folder, "chat_history.md"))

    fitness_inputs, trade_log = simulate.run_simulation(agent, split, num_days=num_samples)

    with open(os.path.join(output_folder, "raw_simulation.json"), "w") as f:
        json.dump({"split": split, **fitness_inputs}, f, indent=2)
    with open(os.path.join(output_folder, "trade_log.json"), "w") as f:
        json.dump(trade_log, f, indent=2)

    return output_folder


def report_alpaca_trading(output_dir):
    raw_path = os.path.join(output_dir, "raw_simulation.json")
    with open(raw_path) as f:
        raw = json.load(f)

    fitness = reward.compute_fitness(
        raw["equity_curve"], raw.get("benchmark_curve"), raw.get("equal_weight_curve"),
    )
    report = {"split": raw["split"], **fitness}

    report_path = os.path.join(output_dir, "report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"[{raw['split']}] risk_adjusted_score={report['risk_adjusted_score']} "
          f"total_return_pct={report['total_return_pct']} "
          f"benchmark_return_pct={report['benchmark_return_pct']} "
          f"equal_weight_return_pct={report['equal_weight_return_pct']} "
          f"max_drawdown_pct={report['max_drawdown_pct']} sharpe={report['sharpe']}")

    return report, report_path
