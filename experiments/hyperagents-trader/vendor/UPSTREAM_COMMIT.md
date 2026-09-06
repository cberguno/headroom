# Upstream provenance

This directory (`vendor/hyperagents/`) is a **vendored copy of the actual
[facebookresearch/hyperagents](https://github.com/facebookresearch/hyperagents)
source**, not a reimplementation.

- Repository: https://github.com/facebookresearch/hyperagents
- Commit: `59a68f672dfb92c74aeb7e61535d776fb36e172d`
- Commit date: 2026-04-14 12:07:47 -0700
- Fetched: shallow clone (`git clone --depth 1`), so this is upstream's `main`
  branch tip as of that date.
- License: CC BY-NC-SA 4.0 (non-commercial) — see `hyperagents/LICENSE.md`.
  This directory is under that license, distinct from headroom's own Apache-2.0
  license. Files here are Meta's, unmodified except where noted below.

## Why vendored instead of a fork or git submodule

This session's GitHub write access is scoped to `cberguno/headroom` only —
both forking `facebookresearch/hyperagents` and creating a new repository
under the user's account were rejected by GitHub with 403 "Resource not
accessible by integration" (the installed GitHub App/session credentials are
authorized for exactly one repository). A git submodule was also ruled out:
a submodule only works if the referenced commit is reachable from a repo
this session can push new commits to, and the modifications below need to
live in a real, fetchable commit — which none of `facebookresearch/hyperagents`
(no push access) or a new repo (create/fork both rejected) could provide.

Vendoring a full copy of the pinned commit directly into `cberguno/headroom`,
then editing those files in place, was the only option that let the actual
upstream files (not a reimplementation) end up somewhere genuinely pushable.
If you later get write access elsewhere (your own fork, or this session is
re-scoped), the diff between this directory and upstream commit
`59a68f672dfb92c74aeb7e61535d776fb36e172d` is exactly the patch to upstream
this represents — see `alpaca_trading_domain.patch` in this directory once
generated (or just `git log` the commits touching `vendor/hyperagents/` in
this repo's history).

## What was modified vs. upstream

Everything under `vendor/hyperagents/domains/alpaca_trading/` is new.
Modified upstream files (each has a comment marking the added block):

- `vendor/hyperagents/domains/harness.py` — dispatch to the new domain
- `vendor/hyperagents/domains/report.py` — dispatch to the new domain
- `vendor/hyperagents/utils/domain_utils.py` — scoring/split metadata for the new domain

No other upstream file was changed. `task_agent.py`, `meta_agent.py`,
`generate_loop.py`, `agent/`, and every other existing domain are byte-for-byte
what upstream shipped at the pinned commit.
