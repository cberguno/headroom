# Standalone prototype (superseded)

This is the original implementation from this project's first PR: a
clean-room, from-scratch reimplementation of the "meta-agent evolves a
strategy" idea, inspired by facebookresearch/hyperagents but sharing no code
or mechanism with it -- it doesn't use `AgentSystem`/`TaskAgent`, the
`domains/harness.py` dispatch, or `generate_loop.py`'s archive/parent
selection.

When asked to verify whether this actually integrated the upstream
framework, the answer was no -- see `../vendor/UPSTREAM_COMMIT.md` and
`../vendor/hyperagents/domains/alpaca_trading/` for the real integration,
built afterward: the actual upstream source (pinned at a recorded commit),
extended through its real domain contract (`domains/harness.py`,
`domains/report.py`, `utils/domain_utils.py`), so it can run under
`generate_loop.py`'s real self-improvement loop, not a reimplementation of
its idea.

This folder is kept only because its logic (risk clamping, cost/slippage
modeling, fitness scoring) was ported into the real integration rather than
rewritten from scratch -- see `../vendor/hyperagents/domains/alpaca_trading/risk.py`,
`costs.py`, and `reward.py`. Treat this folder as historical; don't run it
expecting it to reflect the actual hyperagents framework.
