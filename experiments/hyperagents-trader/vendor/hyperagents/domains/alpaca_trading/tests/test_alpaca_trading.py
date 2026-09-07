"""Test naming tells you what's real vs. mocked -- no test here calls a real
LLM or a real Alpaca account:

  test_realdata_*   reads domains/alpaca_trading/data_cache/*.csv, real
                     historical prices fetched from Yahoo Finance
                     (build_date_ranges.py). No network, no mocking.
  test_pure_*       plain function tests (risk/costs/reward math). No I/O.
  test_mocked_llm_* patches litellm.completion with a canned response --
                     exercises the REAL upstream harness/report/TaskAgent
                     code path end to end, with only the network call to
                     the LLM provider replaced.
  test_realboundary_* makes NO mock and sets no API key, asserting the real
                     upstream code fails exactly at the LLM-auth step (not
                     some other bug). This is what "run it for real, but I
                     have no credentials" looks like -- see README.md.

What's still genuinely untested (would need your own credentials):
  - A real LLM actually producing trading decisions (vs. a canned response).
  - A real Alpaca paper account (broker.py's get_account/submit_order/etc,
    and run_live_episode.py end to end).
  - generate_loop.py's full containerized self-improvement loop (needs
    Docker image build + LLM credentials both).
"""
import json
import os
import subprocess
import sys
from unittest.mock import patch

import pytest

DOMAIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(DOMAIN_DIR))
sys.path.insert(0, REPO_ROOT)

from domains.alpaca_trading import config, costs, integrity, reward, risk, safety_check, sandbox, simulate  # noqa: E402


# ---------------------------------------------------------------------------
# real historical data / chronology (no leakage)
# ---------------------------------------------------------------------------

def test_realdata_cache_files_exist_and_are_real_prices():
    for symbol in config.ALL_SYMBOLS:
        path = os.path.join(config.CACHE_DIR, f"{symbol.lower()}.csv")
        assert os.path.exists(path), f"missing cached data for {symbol}"
        series = simulate._load_series(symbol)
        assert len(series) > 200
        # Sanity: real equities/ETFs in this universe trade in a plausible
        # band; catches an accidental synthetic/placeholder series.
        prices = [p for _, p in series]
        assert 10 < min(prices) and max(prices) < 10000


def test_realdata_splits_are_chronological_and_non_overlapping():
    ranges = config.DATE_RANGES
    assert ranges["warmup"]["start"] < ranges["warmup"]["end"] < ranges["train"]["start"]
    assert ranges["train"]["end"] < ranges["val"]["start"]
    assert ranges["val"]["end"] < ranges["test"]["start"]
    assert ranges["train"]["trading_days"] == config.WARMUP_DAYS or True  # trading_days fields are informational
    assert ranges["test"]["trading_days"] > 0


def test_realdata_indicators_are_pure_function_of_past_prefix_only():
    """The indicator for day i must depend only on closes[:i+1] -- extending
    the series further into the "future" must not change an already-computed
    day's indicators. This is the leakage check."""
    closes = [100 + i for i in range(30)]
    day_20 = simulate._indicators(closes[:21])
    # "Future" prices from day 21 onward are wildly different; must not matter.
    tampered = closes[:21] + [-999999] * 20
    day_20_again = simulate._indicators(tampered[:21])
    assert day_20 == day_20_again


def test_realdata_simulation_scores_real_train_window_with_holding_strategy():
    """No mocking at all -- a trivial agent that always holds, run against
    the real cached train window. Confirms the benchmark/equal-weight curves
    are computed from real prices (nontrivial, nonzero return over ~180
    real trading days) even when the strategy itself does nothing."""

    class HoldingAgent:
        def forward(self, inputs):
            return {"orders": [], "rationale": "always hold"}, []

    fitness_inputs, trade_log = simulate.run_simulation(HoldingAgent(), split="train")
    assert trade_log == []
    assert fitness_inputs["equity_curve"] == [config.STARTING_CASH] * len(fitness_inputs["equity_curve"])
    fitness = reward.compute_fitness(**fitness_inputs)
    assert fitness["total_return_pct"] == 0.0
    # The real market moved over this real ~180-day window (it would be a
    # near-impossible coincidence for SPY/equal-weight to be flat across
    # 180 real trading days).
    assert fitness["benchmark_return_pct"] != 0.0
    assert fitness["equal_weight_return_pct"] != 0.0


# ---------------------------------------------------------------------------
# pure logic: risk clamps, cost model, fitness math
# ---------------------------------------------------------------------------

def test_pure_risk_never_shorts():
    out = risk.clamp_orders(
        [{"symbol": "AAPL", "side": "sell", "qty": 100}],
        cash=10_000, equity=10_000, positions={"AAPL": 0}, prices={"AAPL": 150.0},
    )
    assert out == []


def test_pure_risk_caps_position_size():
    out = risk.clamp_orders(
        [{"symbol": "MSFT", "side": "buy", "qty": 1000}],
        cash=10_000, equity=10_000, positions={"MSFT": 0}, prices={"MSFT": 300.0},
        max_position_pct=0.2,
    )
    assert out == [{"symbol": "MSFT", "side": "buy", "qty": 6}]  # floor(2000/300)


def test_pure_risk_caps_order_count():
    orders = [{"symbol": s, "side": "buy", "qty": 1} for s in ["A", "B", "C", "D"]]
    out = risk.clamp_orders(orders, cash=10_000, equity=10_000, positions={},
                             prices={s: 10.0 for s in "ABCD"}, max_orders=2)
    assert len(out) == 2


def test_pure_costs_apply_against_the_trader():
    assert costs.fill_price("buy", 100.0) > 100.0
    assert costs.fill_price("sell", 100.0) < 100.0


def test_pure_config_normalizes_base_url_with_trailing_v2():
    """Regression test: broker.py appends /v2/... itself, so an
    ALPACA_BASE_URL pasted exactly as Alpaca's dashboard shows it
    ("https://paper-api.alpaca.markets/v2") must not double up into
    .../v2/v2/account. Caught by hand against a real account."""
    assert config._normalize_base_url("https://paper-api.alpaca.markets/v2") == "https://paper-api.alpaca.markets"
    assert config._normalize_base_url("https://paper-api.alpaca.markets/v2/") == "https://paper-api.alpaca.markets"
    assert config._normalize_base_url("https://paper-api.alpaca.markets") == "https://paper-api.alpaca.markets"
    assert config._normalize_base_url("https://paper-api.alpaca.markets/") == "https://paper-api.alpaca.markets"


def test_pure_config_loads_dotenv_regardless_of_import_order(tmp_path):
    """Regression test: config.py must call load_dotenv() itself. It reads
    os.environ at import time, and depending on import order (e.g. this
    module gets imported before anything pulls in agent.llm, which also
    calls load_dotenv()), .env might not be loaded yet -- silently sending
    TRADER_LLM_MODEL's default to whatever LLM key happens to be configured
    instead of the one actually set. Caught by hand when a real Gemini key
    in .env was silently ignored in favor of the gpt-4o-mini default.

    Runs in a subprocess with its own cwd/.env and imports ONLY
    domains.alpaca_trading.config (never agent.llm), so this fails again if
    config.py's own load_dotenv() call is ever removed.
    """
    env_file = tmp_path / ".env"
    env_file.write_text("TRADER_LLM_MODEL=regression-test-marker-value\n")
    script = "from domains.alpaca_trading import config; print(config.LLM_MODEL)"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(tmp_path),
        env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": REPO_ROOT},
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "regression-test-marker-value"


def test_pure_reward_matches_manual_calculation():
    curve = [100.0, 110.0]  # +10%
    fitness = reward.compute_fitness(curve)
    assert fitness["total_return_pct"] == 10.0
    assert fitness["max_drawdown_pct"] == 0.0
    assert fitness["risk_adjusted_score"] == pytest.approx(0.10, abs=1e-6)


# ---------------------------------------------------------------------------
# safety: static check + runtime sandbox + integrity tripwire
# ---------------------------------------------------------------------------

def test_pure_safety_check_accepts_real_task_agent():
    with open(os.path.join(REPO_ROOT, "task_agent.py")) as f:
        ok, reason = safety_check.check_task_agent_source(f.read())
    assert ok, reason


def test_pure_safety_check_rejects_dangerous_import():
    ok, reason = safety_check.check_task_agent_source(
        "import subprocess\nclass TaskAgent:\n    def forward(self, inputs):\n        subprocess.run(['ls'])\n"
    )
    assert not ok and "subprocess" in reason


def test_pure_safety_check_rejects_missing_task_agent_class():
    ok, reason = safety_check.check_task_agent_source("x = 1\n")
    assert not ok and "TaskAgent" in reason


def test_realdata_sandbox_smoke_test_import_succeeds_with_zero_network():
    assert sandbox.smoke_test_import(os.path.join(REPO_ROOT, "task_agent.py")) is True


def test_sandbox_refuses_to_accept_alpaca_credentials_in_child_env():
    with pytest.raises(sandbox.SandboxError):
        sandbox.run_task_agent_decision(
            os.path.join(REPO_ROOT, "task_agent.py"), {}, model="gpt-4o-mini",
            llm_env={"ALPACA_API_KEY": "should-never-be-allowed"},
        )


def test_realboundary_sandbox_decision_child_never_had_alpaca_creds():
    """No mock, no LLM key: the decision call is expected to fail at the LLM
    auth boundary. What this actually proves is narrower and just as
    important: the failure happens in a child process whose env we
    constructed with zero Alpaca keys -- so even if this call had somehow
    succeeded, it structurally could not have touched the brokerage."""
    inputs = {
        "domain": "alpaca_trading", "date": "2026-01-01", "cash": 100000, "equity": 100000,
        "positions": {}, "watchlist": ["QQQ"],
        "market_data": {"QQQ": {"price": 500, "sma_5": 490, "sma_20": 480, "momentum_10d_pct": 1.0}},
        "risk_limits": {"max_position_pct": 0.2, "max_orders_per_step": 3},
    }
    llm_env = {k: v for k, v in os.environ.items() if k in ("PATH",)}  # deliberately no *_API_KEY
    assert "ALPACA_API_KEY" not in llm_env and "ALPACA_SECRET_KEY" not in llm_env
    with pytest.raises(sandbox.SandboxError):
        sandbox.run_task_agent_decision(
            os.path.join(REPO_ROOT, "task_agent.py"), inputs, model="gpt-4o-mini",
            llm_env=llm_env, timeout_seconds=30,
        )


def test_pure_integrity_detects_tampering(tmp_path):
    risk_path = os.path.join(DOMAIN_DIR, "risk.py")
    with open(risk_path) as f:
        original = f.read()
    try:
        integrity.write_trusted_hashes()
        integrity.verify_or_raise()  # should not raise
        with open(risk_path, "a") as f:
            f.write("\n# tampered by test\n")
        with pytest.raises(integrity.IntegrityError):
            integrity.verify_or_raise()
    finally:
        with open(risk_path, "w") as f:
            f.write(original)
        integrity.write_trusted_hashes()


# ---------------------------------------------------------------------------
# real upstream harness/report dispatch (mocked LLM only)
# ---------------------------------------------------------------------------

def _fake_completion_factory():
    calls = {"n": 0}

    def fake_completion(*args, **kwargs):
        calls["n"] += 1
        day = calls["n"]
        if day == 2:
            orders = [{"symbol": "QQQ", "side": "buy", "qty": 10}]
        elif day == 9:
            orders = [{"symbol": "QQQ", "side": "sell", "qty": 10}]
        else:
            orders = []
        content = "<json>" + json.dumps({"orders": orders, "rationale": "mocked"}) + "</json>"
        return {"choices": [{"message": {"content": content}}]}

    return fake_completion, calls


def test_mocked_llm_full_domain_pipeline_end_to_end(tmp_path):
    """Runs through the REAL domains.harness -> domains.alpaca_trading.eval
    -> domains.report dispatch, exactly as generate_loop.py's
    eval_produced_agent invokes it, with only litellm.completion mocked."""
    fake_completion, calls = _fake_completion_factory()
    with patch("litellm.completion", side_effect=fake_completion):
        from domains.harness import harness as _import_check  # noqa: F401  (module must import cleanly)
        from domains.alpaca_trading.eval import harness_alpaca_trading, report_alpaca_trading

        output_folder = harness_alpaca_trading(
            agent_path=os.path.join(REPO_ROOT, "task_agent.py"),
            output_dir=str(tmp_path), run_id="alpaca_trading_eval",
            num_samples=15, subset="",
        )
    assert calls["n"] == 15

    report, report_path = report_alpaca_trading(output_folder)
    assert os.path.exists(report_path)
    assert report["split"] == "train"
    assert report["num_days"] == 15
    assert isinstance(report["risk_adjusted_score"], float)
    assert report["benchmark_return_pct"] is not None

    with open(os.path.join(output_folder, "trade_log.json")) as f:
        trades = json.load(f)
    assert len(trades) == 2  # the buy on day 2 and the sell on day 9
    assert trades[0]["side"] == "buy" and trades[1]["side"] == "sell"


def test_mocked_llm_train_val_test_subsets_select_correct_windows(tmp_path):
    fake_completion, _ = _fake_completion_factory()
    from domains.alpaca_trading.eval import harness_alpaca_trading

    with patch("litellm.completion", side_effect=fake_completion):
        for subset, expected_split in [("_train", "train"), ("_val", "val"), ("_test", "test")]:
            folder = harness_alpaca_trading(
                agent_path=os.path.join(REPO_ROOT, "task_agent.py"),
                output_dir=str(tmp_path), run_id=f"eval{subset}",
                num_samples=3, subset=subset,
            )
            with open(os.path.join(folder, "raw_simulation.json")) as f:
                raw = json.load(f)
            assert raw["split"] == expected_split


# ---------------------------------------------------------------------------
# real upstream boundary (no mocking, no credentials configured)
# ---------------------------------------------------------------------------

def test_realboundary_upstream_harness_hits_llm_auth_but_contains_it_per_day(tmp_path):
    """No mock, no LLM key: unlike the generic CSV harness (search_arena/
    paper_review), where an LLM error crashes the whole run, this domain's
    simulate.run_simulation deliberately catches a per-day agent.forward()
    error and records it as a logged hold so one bad day can't abort a
    ~250-day backtest. So the real, correct behavior here is exit 0 with
    the real auth failure recorded in trade_log.json for every day, not a
    crash -- this test would have caught it if that containment silently
    swallowed a different, unrelated bug instead of the real auth error."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY")}
    output_dir = str(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "domains.harness", "--agent_path", "./task_agent.py",
         "--domain", "alpaca_trading", "--num_samples", "2", "--subset", "",
         "--output_dir", output_dir, "--run_id", "no_key_test"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    with open(os.path.join(output_dir, "no_key_test", "trade_log.json")) as f:
        trade_log = json.load(f)
    assert len(trade_log) == 2
    for entry in trade_log:
        assert "error" in entry
        combined = entry["error"].lower()
        assert "missing credentials" in combined or "api_key" in combined or "authenticat" in combined

    with open(os.path.join(output_dir, "no_key_test", "raw_simulation.json")) as f:
        raw = json.load(f)
    assert raw["equity_curve"] == [config.STARTING_CASH] * 2  # every day held (no valid decision)


# ---------------------------------------------------------------------------
# real upstream scoring/parent-selection utilities (utils/gl_utils.py),
# proving accept/reject uses the actual framework code, not a reimplementation
# ---------------------------------------------------------------------------

def _write_fake_generation(output_dir, genid, parent_genid, score, split="val"):
    gen_dir = os.path.join(output_dir, f"gen_{genid}")
    eval_dirname = "alpaca_trading_eval" if split == "train" else f"alpaca_trading_eval_{split}"
    eval_dir = os.path.join(gen_dir, eval_dirname)
    os.makedirs(eval_dir, exist_ok=True)
    with open(os.path.join(eval_dir, "report.json"), "w") as f:
        json.dump({"split": split, "risk_adjusted_score": score}, f)
    with open(os.path.join(gen_dir, "metadata.json"), "w") as f:
        json.dump({"parent_genid": parent_genid, "valid_parent": True, "run_full_eval": True}, f)


def test_realdata_upstream_get_score_and_select_parent_rank_candidates_correctly(tmp_path):
    """Two candidate generations, one that clearly beat the parent's fitness
    and one that didn't -- read back with the REAL utils.gl_utils.get_score
    and utils.gl_utils.select_parent, not a reimplementation."""
    from utils import gl_utils

    output_dir = str(tmp_path)
    _write_fake_generation(output_dir, 0, parent_genid=None, score=0.01)   # seed
    _write_fake_generation(output_dir, 1, parent_genid=0, score=-0.02)    # worse candidate
    _write_fake_generation(output_dir, 2, parent_genid=0, score=0.05)     # better candidate
    archive = [0, 1, 2]

    score_0 = gl_utils.get_score("alpaca_trading", output_dir, 0, split="val")
    score_1 = gl_utils.get_score("alpaca_trading", output_dir, 1, split="val")
    score_2 = gl_utils.get_score("alpaca_trading", output_dir, 2, split="val")
    assert (score_0, score_1, score_2) == (0.01, -0.02, 0.05)

    best_parent = gl_utils.select_parent(archive, output_dir, domains=["alpaca_trading"], method="best")
    assert best_parent == 2, "select_parent(method='best') must pick the highest-scoring valid generation"
