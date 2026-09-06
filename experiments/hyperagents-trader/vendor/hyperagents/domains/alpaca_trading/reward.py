"""Fitness scoring: equity curve (+ baselines) -> a single comparable
number, plus the breakdown a human (or the meta-agent's next prompt) wants
to see. `score` is what utils/domain_utils.get_domain_score_key points at
for ranking generations.
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
    return 0.0 if std == 0 else (mean / std) * math.sqrt(periods_per_year)


def _max_drawdown(equity):
    peak = equity[0]
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            max_dd = max(max_dd, (peak - value) / peak)
    return max_dd


def _total_return(curve):
    return (curve[-1] / curve[0]) - 1.0 if len(curve) >= 2 and curve[0] > 0 else 0.0


def compute_fitness(equity_curve, benchmark_curve=None, equal_weight_curve=None):
    """
    equity_curve: the agent's simulated equity, chronological, net of costs.
    benchmark_curve: buy-and-hold on the benchmark symbol (e.g. SPY), same length.
    equal_weight_curve: buy-and-hold split equally across the tradeable watchlist.

    `score` = total return penalized by drawdown, so a strategy that "wins" by
    taking on a lot of risk doesn't automatically beat a steadier one. This is
    the number utils/domain_utils.get_domain_score_key("alpaca_trading") points at.
    """
    if len(equity_curve) < 2:
        return {
            "total_return_pct": 0.0, "sharpe": 0.0, "max_drawdown_pct": 0.0,
            "benchmark_return_pct": None, "alpha_vs_benchmark_pct": None,
            "equal_weight_return_pct": None, "alpha_vs_equal_weight_pct": None,
            "num_days": len(equity_curve), "risk_adjusted_score": 0.0,
        }

    total_return = _total_return(equity_curve)
    sharpe = _sharpe(_returns(equity_curve))
    max_dd = _max_drawdown(equity_curve)

    benchmark_return = _total_return(benchmark_curve) if benchmark_curve and len(benchmark_curve) >= 2 else None
    equal_weight_return = _total_return(equal_weight_curve) if equal_weight_curve and len(equal_weight_curve) >= 2 else None

    return {
        "total_return_pct": round(total_return * 100, 3),
        "sharpe": round(sharpe, 3),
        "max_drawdown_pct": round(max_dd * 100, 3),
        "benchmark_return_pct": round(benchmark_return * 100, 3) if benchmark_return is not None else None,
        "alpha_vs_benchmark_pct": round((total_return - benchmark_return) * 100, 3) if benchmark_return is not None else None,
        "equal_weight_return_pct": round(equal_weight_return * 100, 3) if equal_weight_return is not None else None,
        "alpha_vs_equal_weight_pct": round((total_return - equal_weight_return) * 100, 3) if equal_weight_return is not None else None,
        "num_days": len(equity_curve),
        "risk_adjusted_score": round(total_return - max_dd, 5),
    }
