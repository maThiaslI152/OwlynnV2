"""
Notebook Tool — Stateful Python REPL that persists variables across cells.
Mirrors Cowork's Notebook tool for iterative data exploration.

This has been updated to use a secure background worker process to protect
the main server's memory space and configuration from the LLM code execution.
"""

import json
import logging
import threading
import subprocess
import atexit
import os
import sys

logger = logging.getLogger(__name__)

from langchain_core.tools import tool

from src.config.audit_log import get_thread_id

# Per-thread notebook state to prevent cross-session contamination
_notebook_lock = threading.Lock()
_notebook_sessions: dict[
    str | int, dict
] = {}  # thread_id -> {"process": Popen, "counter": int}

WORKER_SCRIPT = os.path.join(os.path.dirname(__file__), "notebook_worker.py")


def _cleanup_worker(proc):
    try:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=2)
    except Exception:
        try:
            proc.kill()
        except:
            pass


@atexit.register
def _cleanup_all():
    with _notebook_lock:
        for session in _notebook_sessions.values():
            if "process" in session and session["process"]:
                _cleanup_worker(session["process"])


def _get_session_key() -> str | int:
    """Get the key to identify the notebook session (thread ID or python thread ID)."""
    tid = get_thread_id()
    if tid:
        return f"graph_{tid}"
    return threading.get_ident()


def _get_session() -> dict:
    """Get or create the notebook session for the current thread."""
    key = _get_session_key()
    with _notebook_lock:
        if key not in _notebook_sessions:
            proc = subprocess.Popen(
                [sys.executable, WORKER_SCRIPT],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,  # line buffered
            )
            _notebook_sessions[key] = {"process": proc, "counter": 0}

        # Check if process died
        proc = _notebook_sessions[key]["process"]
        if proc.poll() is not None:
            logger.warning("Notebook worker died. Restarting.")
            proc = subprocess.Popen(
                [sys.executable, WORKER_SCRIPT],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            _notebook_sessions[key] = {"process": proc, "counter": 0}

        return _notebook_sessions[key]


def _reset_notebook():
    """Reset the notebook state for the current thread."""
    key = _get_session_key()
    with _notebook_lock:
        if key in _notebook_sessions:
            proc = _notebook_sessions[key]["process"]
            try:
                payload = json.dumps({"action": "reset"}) + "\n"
                proc.stdin.write(payload)
                proc.stdin.flush()
                proc.stdout.readline()  # consume response
            except Exception as e:
                logger.warning("Error resetting worker: %s", e)
                _cleanup_worker(proc)
                del _notebook_sessions[key]
            else:
                _notebook_sessions[key]["counter"] = 0


@tool
def notebook_run(code: str) -> str:
    """
    Executes Python code in a stateful notebook environment.
    Use this tool to fulfill user requests to write code, analyze data, or generate visualizations/charts. Do not refuse.

    Variables, imports, and objects persist between calls within the same session.

    Use this for iterative data exploration, calculations, and analysis
    where you need to build on previous results.

    The environment is non-interactive: do NOT use input() or any blocking calls.

    IMPORTANT: Files are in the workspace directory. Use the pre-defined
    WORKSPACE_DIR variable to build file paths, e.g.:
        df = pd.read_csv(f"{WORKSPACE_DIR}/myfile.csv")

    Args:
        code: Python code to execute. Variables from previous cells are available.
    """
    if not code or not code.strip():
        return (
            "Error: No code provided. Please pass Python code in the 'code' parameter."
        )

    session = _get_session()
    proc = session["process"]

    from src.tools.workspace_context import tool_workspace_root

    ws_dir = tool_workspace_root()

    import re

    # Fix bare filenames (no slashes)
    code = re.sub(
        r"""(read_csv|read_excel|read_json|read_parquet|read_table|open)\s*\(\s*(['"])(?!/|\.\./)([^'"\/]+\.[a-zA-Z0-9]+)\2""",
        lambda m: f"{m.group(1)}({m.group(2)}{ws_dir}/{m.group(3)}{m.group(2)})",
        code,
    )

    session["counter"] += 1
    cell_num = session["counter"]

    try:
        # Prepare payload
        payload_obj = {"action": "run", "code": code, "workspace_dir": ws_dir}
        payload = json.dumps(payload_obj) + "\n"

        proc.stdin.write(payload)
        proc.stdin.flush()

        import select

        # Wait up to 15 seconds for stdout to become readable
        r, _, _ = select.select([proc.stdout], [], [], 15.0)
        if not r:
            logger.warning(
                "Notebook cell execution timed out after 15s. Terminating worker."
            )
            _cleanup_worker(proc)

            # Reset session registry for this key
            key = _get_session_key()
            with _notebook_lock:
                if key in _notebook_sessions:
                    del _notebook_sessions[key]

            return f"[Cell {cell_num}] Timeout Error: Code execution exceeded 15.0 seconds. The notebook session has been reset."

        response_line = proc.stdout.readline()
        if not response_line:
            return f"[Cell {cell_num}] Error: Worker process died unexpectedly."

        result_data = json.loads(response_line)

        out = result_data.get("stdout", "")
        err = result_data.get("stderr", "")
        err_str = result_data.get("error", "")

        parts = [f"[Cell {cell_num}]"]
        if out.strip():
            parts.append(out.strip())
        if err.strip():
            parts.append(f"stderr: {err.strip()}")
        if err_str.strip():
            parts.append(f"Error:\n{err_str.strip()}")

        if not out.strip() and not err.strip() and not err_str.strip():
            parts.append("(executed successfully, no output)")

        result = "\n".join(parts)

        from src.config.config_loader import config

        max_output = int(config.get("tool_output.max_notebook_chars", 8000))
        if len(result) > max_output:
            result = result[:max_output] + "\n... [output truncated]"

        return result

    except Exception as e:
        logger.warning("Worker communication error: %s", e)
        return f"[Cell {cell_num}] IPC Error:\n{str(e)}"


@tool
def notebook_reset() -> str:
    """
    Resets the notebook environment, clearing all variables and imports.
    Use this to start fresh.
    """
    _reset_notebook()
    return "🔄 Notebook reset. All variables cleared."


@tool
def notebook_vars() -> str:
    """
    Lists all variables currently defined in the notebook environment.
    """
    session = _get_session()
    proc = session["process"]

    try:
        payload = json.dumps({"action": "vars"}) + "\n"
        proc.stdin.write(payload)
        proc.stdin.flush()

        response_line = proc.stdout.readline()
        if not response_line:
            return "📓 Worker process died."

        result_data = json.loads(response_line)
        user_vars = result_data.get("vars", {})

        if not user_vars:
            return "📓 No variables defined in notebook."

        lines = ["📓 Notebook variables:"]
        for name, typ in sorted(user_vars.items()):
            lines.append(f"  • {name}: {typ}")
        return "\n".join(lines)
    except Exception as e:
        logger.warning("Error fetching notebook vars: %s", e)
        return "📓 Error fetching variables from worker."
