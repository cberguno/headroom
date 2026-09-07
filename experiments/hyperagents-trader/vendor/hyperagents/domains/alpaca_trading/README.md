# alpaca_trading domain

A real domain added to the actual [facebookresearch/hyperagents](https://github.com/facebookresearch/hyperagents)
framework (vendored at commit `59a68f672dfb92c74aeb7e61535d776fb36e172d` --
see `../../../UPSTREAM_COMMIT.md`), following its real extension contract:
`domains/harness.py` / `domains/report.py` dispatch and `utils/domain_utils.py`
scoring metadata, exactly like the existing `genesis`/`balrog` domains. No
change was needed in `generate_loop.py` itself -- it always calls
`domains.harness` / `domains.report` generically
(`generate_loop.py:eval_produced_agent`), so any domain implementing the
contract works with the real self-improvement loop.

The one shared file modified is the root `task_agent.py`: it now has an
`if domain == "alpaca_trading":` branch teaching the framework's existing
baseline agent this domain's response schema (`{"orders": [...], "rationale": ...}`
instead of the generic `{"response": ...}`). Every other domain's behavior
in that file is byte-for-byte unchanged.

## What's real here, and what's mocked in the tests

- **Real**: `data_cache/*.csv` are real daily bars (QQQ, AAPL, MSFT, NVDA,
  AMZN, SPY; 2025-08-01 through 2026-09-04), fetched from Yahoo Finance's
  public chart API (no key needed) since this sandbox has no Alpaca
  credentials -- see `build_date_ranges.py`. `train`/`val`/`test` are real,
  fixed, non-overlapping chronological windows over that data
  (`date_ranges.json`). Backtesting reads only these files; it makes no
  network calls and needs no credentials at all.
- **Mocked in tests**: `litellm.completion`, since no LLM API key is
  configured in this environment. Tests that do this are named
  `test_mocked_llm_*` and run the real `domains.harness` →
  `domains.alpaca_trading.eval` → `domains.report` dispatch with only that
  one call replaced.
- **Never mocked in the committed test suite** (it needs no credentials to
  run in CI), but since first written this domain HAS been run for real,
  by hand, against: Gemini (`gemini/gemini-3-flash-preview`, hit its
  20-req/day free-tier cap fast), Nous Portal's OpenAI-compatible endpoint
  (`openai/inclusionai/ling-3.0-flash-sante:free` via `OPENAI_API_BASE` --
  see `.env.example` for the exact pattern for any OpenAI-compatible
  provider), and a real Alpaca paper account (`get_account`/`get_positions`/
  `get_daily_bars`, read-only). A 3-day real run with Nous's model produced
  a real trade log (bought AAPL, partially sold it, bought more AAPL + QQQ)
  and a real `report.json` with nonzero return/drawdown/Sharpe. None of this
  is in the automated suite since it needs credentials CI doesn't have --
  see git history for the exact commands run.

Run `python -m pytest domains/alpaca_trading/tests/ -v` (from `vendor/hyperagents/`,
after `pip install -r domains/alpaca_trading/requirements-minimal.txt`) --
22 tests, all passing as of this commit, none requiring credentials.

## Cost math before you run this with real LLM keys

Backtesting calls `TaskAgent.forward()` once per simulated trading day (this
domain evaluates chronologically, so days can't be parallelized like
independent question rows can). Per generation:

- Staged/quick eval: 10 calls (`get_domain_stagedeval_samples`)
- Full eval: 180 (train) + 40 (val) = 220 calls; +36 more if you also
  evaluate `test` (only do this once, at the very end -- see "Held-out test"
  below)

Default model is `gpt-4o-mini` (`TRADER_LLM_MODEL` env var to change), each
call's prompt is small (positions + 5 symbols' prices/moving averages), so
per-generation cost should be small, but check current pricing for whatever
model you pick before running many generations -- 10 generations of full
eval is ~2,200 calls. Use `--num_samples` to cap days evaluated while
developing.

`generate_loop.py`'s meta-agent (separate from the task agent) makes its own
LLM calls per generation to propose the code diff -- typically fewer but
larger (it sees the relevant parts of the repo). Check `run_meta_agent.py`
if you want that cost in isolation.

## Running it

```bash
cd experiments/hyperagents-trader/vendor/hyperagents
python3 -m venv venv && source venv/bin/activate
pip install -r domains/alpaca_trading/requirements-minimal.txt   # harness-only path, no Docker/genesis/balrog deps
cp .env.example .env   # create this yourself -- see variables below; never commit it
```

Variables (put in `.env`, or export them):
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` -- for the task
  agent's own decisions (backtesting) and, if you go this far, the
  meta-agent's patch proposals.
- `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` -- **only** needed for
  `run_live_episode.py`. Get paper-trading keys (not live) from
  https://app.alpaca.markets/paper/dashboard/overview. Backtesting/
  self-improvement never read these.
- `ALPACA_BASE_URL` -- leave as `https://paper-api.alpaca.markets`.
  `broker.py` refuses to run against anything else.

**A single evaluation** (what `eval_produced_agent` does per generation):
```bash
python -m domains.harness --agent_path ./task_agent.py --domain alpaca_trading \
  --num_samples 20 --subset "" --output_dir outputs --run_id my_eval   # subset "" / "_val" / "_test" -> train/val/test
python -m domains.report --domain alpaca_trading --dname outputs/my_eval
cat outputs/my_eval/report.json
```

**Full self-improvement** (the real `generate_loop.py`, Docker-containerized
per upstream's design -- see "What wasn't run" below for why this session
didn't execute it end to end):
```bash
python generate_loop.py --domains alpaca_trading --max_generation 10 --selection_method best
```
`--selection_method` matters: `best` is strict hill-climbing (only the
highest-scoring valid generation becomes the next parent). `random` /
`score_prop` / `score_child_prop` are open-ended/quality-diversity search,
where a lower-scoring generation can still be selected as a future parent --
this is upstream's actual default framing ("open-ended self-improvement"),
not simple hill-climbing. See `utils/gl_utils.py:select_parent`.

**Held-out test** -- run this once, after you're done iterating, not as
part of the loop:
```bash
python -m domains.harness --agent_path outputs/<best_gen>/task_agent.py --domain alpaca_trading --subset "_test" --output_dir outputs --run_id final_test
python -m domains.report --domain alpaca_trading --dname outputs/final_test
```

**Live paper trading**, once you trust a specific `task_agent.py`:
```bash
python -c "from domains.alpaca_trading.integrity import write_trusted_hashes; write_trusted_hashes()"  # after reviewing risk.py/broker.py/sandbox.py/safety_check.py yourself
python -m domains.alpaca_trading.run_live_episode --dry-run   # decides and logs, submits nothing
python -m domains.alpaca_trading.run_live_episode             # submits real paper orders
```
Run on a schedule (e.g. once per trading day) rather than in a loop.

## Safety architecture

1. **Paper-only, structurally.** `broker.py` refuses to run unless
   `ALPACA_BASE_URL` contains `paper-api.alpaca.markets`. Alpaca issues
   separate keys for paper vs. live -- that's the real boundary; the code
   check is a second layer.
2. **Backtesting/self-improvement never holds Alpaca credentials, because it
   never needs them.** It reads only `data_cache/*.csv`. Whatever the
   meta-agent's Docker container can do to `task_agent.py`, it cannot reach
   your brokerage from inside a backtest.
3. **`run_live_episode.py` isolates the decision call, not just the
   strategy file's imports.** `sandbox.py` runs `TaskAgent.forward()` in a
   resource-limited (CPU/memory/process-count) child process whose
   environment contains the LLM key(s) it needs and **never**
   `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`. The child's output is parsed as
   inert JSON, never executed. `risk.py`'s hard clamps (no shorting,
   position-size cap, cash cap, order-count cap) run in the trusted parent
   afterward, regardless of what the child proposed. Only the trusted
   parent ever calls `broker.submit_order`.
4. **Static checks are a pre-filter, not the guarantee** (`safety_check.py`
   rejects obviously dangerous imports/calls) -- layer 3 is what actually
   backs it up, per your instruction not to rely on static checks alone.
5. **The gap this can't close on its own**: upstream's meta-agent has
   unrestricted write access to the whole repo
   (`meta_agent.py`: `"Modify any part of the codebase at {repo_path}"`) --
   there is no upstream flag that scopes it to `task_agent.py` only (the
   existing `reset_task_agent` flag *discards* task_agent.py diffs; it does
   not *restrict* edits to that file --
   see `utils/gl_utils.py:filter_patch_by_files`). So a self-improvement run
   could, in principle, rewrite `risk.py`, `broker.py`, `sandbox.py`, or
   `safety_check.py` themselves. Those files are never read by
   self-improvement (it only calls `domains.harness`/`domains.report`), so
   this has no effect *unless* a human later runs `run_live_episode.py`
   against that same mutated checkout without reviewing it first.
   `integrity.py` is the mitigation: `run_live_episode.py` hashes those four
   files and refuses to run if they differ from the hashes you last
   accepted by hand (`write_trusted_hashes()`, meant to be run only after
   you've read `git diff` on them yourself). This is a tripwire an operator
   can act on, not a sandbox -- it can't stop something that also controls
   the recorded hashes, only alert a human who runs live trading on an
   unreviewed checkout.
6. **Network egress from the sandboxed child is not fully denied** (layer 3
   above) -- it needs to reach the LLM provider, which is inherent to
   calling an LLM at all. `sandbox.smoke_test_import` (a separate,
   zero-network check with `unshare --net`, used before any credentialed
   call) shows what full isolation looks like when no network is needed at
   all. A real egress allowlist (child can reach only the LLM provider's
   host, nothing else) would need an authenticated forwarding proxy or
   network-namespace + iptables rules -- real follow-up work, not done here.

## Backtest realism

- Chronological only: indicators for day *i* are a pure function of
  `closes[:i+1]` (`test_realdata_indicators_are_pure_function_of_past_prefix_only`
  checks this directly) -- no future data ever reaches a decision.
- Transaction costs: Alpaca charges no commission on US equities
  (`COMMISSION_BPS = 0.0`, realistic); `SLIPPAGE_BPS = 5.0` models bid-ask
  spread/market impact against the trader on every fill. Override both in
  `config.py` if you want to stress-test a strategy under worse conditions.
  There's no borrow cost modeled because shorting isn't implemented at all.
- Baselines reported alongside every fitness score: buy-and-hold on the
  benchmark (SPY) and an equal-weight buy-and-hold across the tradeable
  watchlist -- both computed from the same real cached data, so "did the
  strategy beat doing nothing" is always visible in `report.json`, not just
  its own return.

## What wasn't run in this session, and why

- **A real LLM call and a real Alpaca account** were not configured when
  this domain was first built, but both were later verified by hand once
  credentials were provided (see "What's real here" above) -- committed
  tests still don't require credentials, since CI has none. If you're
  starting fresh yourself: no key configured means every test either uses
  real data with no LLM involved, mocks `litellm.completion`, or asserts
  the real (and correctly handled) auth failure. Add a key and re-run
  `domains.harness` directly to get a real decision; add Alpaca keys and
  call `broker.get_account()` to check connectivity before trying
  `run_live_episode.py`.
- **The full containerized `generate_loop.py` run.** Its `Dockerfile` builds
  from a multi-GB CUDA devel image and installs Genesis/MiniHack/torch for
  domains this one doesn't use -- a large, slow build with real resource
  cost, and even a successful build still can't exercise the meta-agent's
  real patch-generation step without your LLM credentials. Instead, this
  session verified the domain-specific parts that a container build
  wouldn't have tested anyway: `domains.harness`/`domains.report` dispatch
  wired correctly, and `utils.gl_utils.get_score`/`select_parent` (the real
  scoring/parent-selection code `generate_loop.py` calls) correctly ranking
  real candidate generations by score
  (`test_realdata_upstream_get_score_and_select_parent_rank_candidates_correctly`).
  If you have Docker resources and LLM credentials to spare, `generate_loop.py
  --domains alpaca_trading` should work as-is; report back if it doesn't.

## Honest limitations

- This searches one Python file's logic with an LLM, not a trained model --
  don't expect it to reliably beat buy-and-hold. A backtest that looks good
  can be overfit to `train`/`val`; that's exactly what the held-out `test`
  window is for, so keep it out of the optimization loop.
- 220 trading days total across train+val is a short history for a strategy
  search; results here should be read as "does the pipeline work," not "is
  this strategy good."
