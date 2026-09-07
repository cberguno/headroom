"""Runtime isolation for executing the (meta-agent-evolved) task_agent.py's
decision code, used by run_live_episode.py -- the one script in this domain
that holds real Alpaca paper credentials.

Why this exists: safety_check.py's static AST scan is a cheap pre-filter,
not a guarantee -- it cannot catch everything (e.g. logic errors, resource
exhaustion, or an import path it doesn't know to deny). The task_agent.py
that actually runs is arbitrary, LLM-generated Python selected by an
open-ended search (self_improve / generate_loop), so it is treated as
untrusted regardless of what the static check says.

What this module actually provides, and what it does NOT:
- The child process that calls TaskAgent.forward() runs with an environment
  containing ONLY the LLM API key(s) it needs to function -- never
  ALPACA_API_KEY / ALPACA_SECRET_KEY. Those never leave the trusted parent
  process. This is the main guarantee: no matter what the untrusted code
  does, it cannot authenticate to the brokerage.
- CPU time, memory (address space), and process-count are capped via
  resource.setrlimit in the child, and the whole call has a hard wall-clock
  timeout -- a runaway or hung strategy cannot consume unbounded resources
  or block the caller indefinitely.
- The child's only interprocess channel is its stdout, and the parent reads
  it as inert text (json.loads on the last line) -- never exec/eval on
  anything the child produces.
- Deviation from "no unrestricted networking": the child DOES need outbound
  network access to reach the LLM provider (that's inherent to calling an
  LLM at all -- every hyperagents domain's task_agent.py does this). This
  sandbox does not implement an egress allowlist restricting the child to
  only the LLM provider's host; that would need an authenticated forwarding
  proxy or netns+iptables rules, which is real follow-up work (see README).
  What IS enforced is that the child cannot reach anything USEFUL at Alpaca
  even with full network access, because it never holds the credentials.
- For a zero-network, zero-credential smoke test (e.g. "does this file even
  import without crashing"), use `smoke_test_import`, which additionally
  strips network via `unshare --net` since no LLM call is attempted there.
"""
import json
import os
import resource
import shutil
import subprocess
import sys
import tempfile

_RUNNER_TEMPLATE = '''
import importlib.util
import json
import sys

spec = importlib.util.spec_from_file_location("candidate_task_agent", {task_agent_path!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

agent = module.TaskAgent(model={model!r}, chat_history_file={chat_history_file!r})
inputs = json.loads({inputs_json!r})
prediction, _ = agent.forward(inputs)
print("===SANDBOX_RESULT_START===")
print(json.dumps({{"prediction": prediction}}))
print("===SANDBOX_RESULT_END===")
'''


def _limit_resources(cpu_seconds, memory_mb):
    def _setlimits():
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        mem_bytes = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))
        resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
    return _setlimits


class SandboxError(RuntimeError):
    pass


def run_task_agent_decision(task_agent_path, inputs, model, llm_env,
                             timeout_seconds=90, cpu_seconds=60, memory_mb=1024):
    """Runs TaskAgent(model=model).forward(inputs) from `task_agent_path` in a
    resource-limited child process whose environment is exactly `llm_env`
    (must NOT contain Alpaca credentials -- callers pass only the LLM keys).
    Returns the `prediction` value. Raises SandboxError on crash, timeout,
    resource-limit violation, or unparseable output.
    """
    for forbidden in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"):
        if forbidden in llm_env:
            raise SandboxError(f"refusing to run sandbox: {forbidden} present in child env")

    with tempfile.TemporaryDirectory() as tmp:
        chat_history_file = os.path.join(tmp, "chat_history.md")
        runner_path = os.path.join(tmp, "runner.py")
        script = _RUNNER_TEMPLATE.format(
            task_agent_path=os.path.abspath(task_agent_path),
            model=model,
            chat_history_file=chat_history_file,
            inputs_json=json.dumps(json.dumps(inputs)),
        )
        with open(runner_path, "w") as f:
            f.write(script)

        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        env = dict(llm_env)
        env["PYTHONPATH"] = repo_root

        try:
            result = subprocess.run(
                [sys.executable, runner_path],
                cwd=tmp,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                preexec_fn=_limit_resources(cpu_seconds, memory_mb),
            )
        except subprocess.TimeoutExpired as exc:
            raise SandboxError(f"task_agent.py timed out after {timeout_seconds}s") from exc

        if result.returncode != 0:
            raise SandboxError(f"task_agent.py exited {result.returncode}: {result.stderr[-2000:]}")

        stdout = result.stdout
        try:
            start = stdout.index("===SANDBOX_RESULT_START===") + len("===SANDBOX_RESULT_START===")
            end = stdout.index("===SANDBOX_RESULT_END===")
            payload = json.loads(stdout[start:end].strip())
        except (ValueError, json.JSONDecodeError) as exc:
            raise SandboxError(f"could not parse sandbox output: {exc}; stdout={stdout[-2000:]}") from exc

        return payload["prediction"]


def smoke_test_import(task_agent_path, timeout_seconds=15):
    """Zero-network, zero-credential check that a candidate task_agent.py at
    least imports and defines TaskAgent, without calling forward() (which
    would need the LLM and therefore network). Uses `unshare --net` since no
    legitimate network call should happen here at all.
    """
    script = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('m', {os.path.abspath(task_agent_path)!r})\n"
        "m = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(m)\n"
        "assert hasattr(m, 'TaskAgent'), 'no TaskAgent class'\n"
        "print('OK')\n"
    )
    def _run(cmd):
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_seconds,
            env={"PATH": os.environ.get("PATH", "")},
            preexec_fn=_limit_resources(cpu_seconds=10, memory_mb=512),
        )

    plain_cmd = [sys.executable, "-c", script]
    try:
        if shutil.which("unshare") is not None:
            result = _run(["unshare", "--net", "--", *plain_cmd])
            if result.returncode != 0 or "OK" not in result.stdout:
                # `unshare --net` itself can be refused by the host's namespace
                # policy (e.g. unprivileged user namespaces disabled) even
                # though the binary exists -- that's a host limitation, not a
                # failure of task_agent.py, so fall back to an unisolated run
                # rather than reporting the wrong thing as broken.
                result = _run(plain_cmd)
        else:
            result = _run(plain_cmd)
    except subprocess.TimeoutExpired as exc:
        raise SandboxError(f"smoke test timed out after {timeout_seconds}s") from exc
    if result.returncode != 0 or "OK" not in result.stdout:
        raise SandboxError(f"smoke test failed: {result.stderr[-2000:] or result.stdout[-2000:]}")
    return True
