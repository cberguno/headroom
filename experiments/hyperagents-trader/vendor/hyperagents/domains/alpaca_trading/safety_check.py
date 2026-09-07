"""Static pre-filter over a candidate task_agent.py before it is ever
executed. This is ONE layer, not the only one -- see sandbox.py for the
runtime isolation (resource limits, stripped credentials) that backs it up.
A file passing this check is still run only inside sandbox.py's restrictions,
never trusted outright.
"""
import ast

DENIED_MODULES = {
    "socket", "subprocess", "ftplib", "smtplib", "multiprocessing", "threading",
    "asyncio", "pickle", "marshal", "ctypes", "shutil",
}
DENIED_CALLS = {"eval", "exec", "compile", "__import__"}


def check_task_agent_source(source_code):
    """Returns (ok: bool, reason: str)."""
    try:
        tree = ast.parse(source_code)
    except SyntaxError as exc:
        return False, f"syntax error: {exc}"

    has_task_agent = any(
        isinstance(node, ast.ClassDef) and node.name == "TaskAgent" for node in tree.body
    )
    if not has_task_agent:
        return False, "no top-level TaskAgent class defined"

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
