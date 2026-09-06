# HyperAgents Trader

A real integration of [facebookresearch/hyperagents](https://github.com/facebookresearch/hyperagents)
("Self-referential self-improving agents that can optimize for any computable
task", [arXiv:2603.19461](https://arxiv.org/abs/2603.19461)), extended with a
new `alpaca_trading` domain for **paper-trading-only** experiments.

## Start here

**[`vendor/hyperagents/domains/alpaca_trading/README.md`](vendor/hyperagents/domains/alpaca_trading/README.md)**
is the real documentation: setup, cost math, how to run backtests /
self-improvement / live paper trading, the safety architecture, and what was
and wasn't actually verified in this environment (no LLM or Alpaca
credentials were available here -- see that file for exactly where that
boundary is and how to configure your own).

**[`vendor/UPSTREAM_COMMIT.md`](vendor/UPSTREAM_COMMIT.md)** records the
exact upstream commit this is built on, and why it's vendored into this repo
rather than a fork or submodule (this session's GitHub write access is
scoped to this one repository).

## Layout

```
experiments/hyperagents-trader/
├── vendor/
│   ├── UPSTREAM_COMMIT.md          -- provenance: exact commit, why vendored
│   └── hyperagents/                -- the actual upstream source, plus:
│       ├── task_agent.py           -- upstream file, minimally extended (new domain branch)
│       ├── domains/harness.py      -- upstream file, dispatch to the new domain added
│       ├── domains/report.py       -- upstream file, dispatch to the new domain added
│       ├── utils/domain_utils.py   -- upstream file, scoring metadata for the new domain added
│       └── domains/alpaca_trading/ -- NEW: the domain itself (see its README)
└── standalone-prototype/           -- the original, pre-audit implementation (see its README:
                                       it doesn't integrate the real framework -- kept for its
                                       reusable risk/cost/reward logic, which was ported into
                                       the real domain above, not for its own use)
```

## CI

`.github/workflows/alpaca-trading-domain.yml` runs `domains/alpaca_trading/tests/`
(20 tests, all real-data-or-mocked, no credentials needed) on any change
under this directory. It's path-scoped and never touches headroom's own
`ci.yml`.
