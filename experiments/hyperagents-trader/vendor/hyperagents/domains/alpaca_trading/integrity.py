"""Guards against the one gap the sandboxing in this domain cannot close on
its own: upstream's meta-agent has an unrestricted bash/edit tool
("Modify any part of the codebase at {repo_path}" -- see meta_agent.py) and
there is no upstream flag that scopes it to task_agent.py only (the
existing reset_task_agent flag *discards* task_agent.py diffs, it does not
*restrict* edits to that file -- see utils/gl_utils.py:filter_patch_by_files).
So a self-improvement run could, in principle, rewrite risk.py, broker.py,
sandbox.py, or safety_check.py themselves, not just the trading strategy.

self_improve/generate_loop never invoke run_live_episode.py, so a rewritten
risk.py has no effect unless a human later runs run_live_episode.py against
that same mutated checkout. This module is the check for that: it hashes
the safety-critical files and refuses to run live if they don't match the
hashes recorded the last time a human deliberately reviewed and accepted
them. It is a tripwire, not a sandbox -- it cannot stop a determined attacker
who also controls this file and its recorded hashes, only alert an operator
who runs run_live_episode.py after an unreviewed self-improvement session.
"""
import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
HASHES_PATH = os.path.join(_HERE, "trusted_hashes.json")
PROTECTED_FILES = ["risk.py", "broker.py", "sandbox.py", "safety_check.py"]


def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def compute_hashes():
    return {name: _sha256(os.path.join(_HERE, name)) for name in PROTECTED_FILES}


def write_trusted_hashes():
    """Run this deliberately, after a human has reviewed `git diff` on the
    protected files, to accept their current state as trusted."""
    with open(HASHES_PATH, "w") as f:
        json.dump(compute_hashes(), f, indent=2)
        f.write("\n")


class IntegrityError(RuntimeError):
    pass


def verify_or_raise():
    if not os.path.exists(HASHES_PATH):
        raise IntegrityError(
            f"{HASHES_PATH} does not exist. Run "
            "`python -c 'from domains.alpaca_trading.integrity import write_trusted_hashes; write_trusted_hashes()'` "
            "once, after reviewing risk.py/broker.py/sandbox.py/safety_check.py yourself, to accept them as trusted."
        )
    with open(HASHES_PATH) as f:
        trusted = json.load(f)
    current = compute_hashes()
    changed = [name for name in PROTECTED_FILES if trusted.get(name) != current[name]]
    if changed:
        raise IntegrityError(
            f"refusing to run: {changed} differ from the last human-reviewed hashes in {HASHES_PATH}. "
            "This can happen after a self-improvement run, whose meta-agent has unrestricted write access "
            "to the whole repo (see this module's docstring) -- review `git diff` on these files before "
            "trusting them again, then re-run write_trusted_hashes()."
        )
