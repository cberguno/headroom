"""Fitness scoring: turn an equity curve (+ a benchmark curve) into a single
comparable number, plus the breakdown a human (or the meta-agent's next
prompt) would want to see.
"""
import math


def _returns(equity):
    return [(equity[i] / equity[i - 1]) - 1.0 for i in range(1, len(equity)) if equity[i - 1] > 0]


def _sharpe(daily_returns, periods_per_year=252):
    if len(daily_returns) < 2:
        return 0.0
    mean = sum(daily_returns) / len(daily_returns)
    variance = sum((r - mean) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return (mean / std) * math.sqrt(periods_per_year)


def _max_drawdown(equity):
    peak = equity[0]
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            max_dd = max(max_dd, (peak - value) / peak)
    return max_dd


def compute_fitness(equity_curve, benchmark_curve=None):
    """
    equity_curve / benchmark_curve: list of floats, chronological, same length
    (benchmark_curve is optional).

    Returns a dict; `score` is what self_improve.py uses to rank candidates:
    total return penalized by drawdown, so a strategy that "wins" by taking
    on a lot of risk doesn't automatically beat a steadier one.
    """
    if len(equity_curve) < 2:
        return {
            "total_return_pct": 0.0, "sharpe": 0.0, "max_drawdown_pct": 0.0,
            "benchmark_return_pct": None, "alpha_pct": None, "score": 0.0,
        }

    total_return = (equity_curve[-1] / equity_curve[0]) - 1.0
    daily_returns = _returns(equity_curve)
    sharpe = _sharpe(daily_returns)
    max_dd = _max_drawdown(equity_curve)

    benchmark_return = None
    alpha = None
    if benchmark_curve and len(benchmark_curve) >= 2:
        benchmark_return = (benchmark_curve[-1] / benchmark_curve[0]) - 1.0
        alpha = total_return - benchmark_return

    score = total_return - max_dd  # drawdown-penalized return; simple and legible

    return {
        "total_return_pct": round(total_return * 100, 3),
        "sharpe": round(sharpe, 3),
        "max_drawdown_pct": round(max_dd * 100, 3),
        "benchmark_return_pct": round(benchmark_return * 100, 3) if benchmark_return is not None else None,
        "alpha_pct": round(alpha * 100, 3) if alpha is not None else None,
        "score": round(score, 5),
    }
