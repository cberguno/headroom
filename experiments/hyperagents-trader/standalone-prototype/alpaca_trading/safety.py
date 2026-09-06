"""Static safety check for meta-agent-generated strategy code.

task_agent.decide() is only supposed to read the `context` dict it's given
and return an orders list — no reason for it to ever import anything with
network, filesystem, or process access. This is enforced by AST inspection
before a candidate is ever imported and executed, on top of (not instead of)
broker.py's paper-endpoint guard and risk.py's order clamping.
"""
import ast

DENIED_MODULES = {
    "os", "sys", "subprocess", "socket", "shutil", "pathlib", "requests",
    "urllib", "http", "ftplib", "smtplib", "multiprocessing", "threading",
    "asyncio", "pickle", "marshal", "ctypes", "importlib", "ssl", "ftp",
}
DENIED_CALLS = {"eval", "exec", "compile", "__import__", "open", "input", "globals", "vars"}


def validate_strategy_source(source_code):
    """Returns (ok: bool, reason: str). `reason` explains the rejection when ok is False."""
    try:
        tree = ast.parse(source_code)
    except SyntaxError as exc:
        return False, f"syntax error: {exc}"

    has_decide = any(isinstance(node, ast.FunctionDef) and node.name == "decide" for node in tree.body)
    if not has_decide:
        return False, "no top-level decide(context) function defined"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in DENIED_MODULES:
                    return False, f"disallowed import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in DENIED_MODULES:
                return False, f"disallowed import: {node.module}"
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name in DENIED_CALLS:
                return False, f"disallowed call: {name}"

    return True, ""
