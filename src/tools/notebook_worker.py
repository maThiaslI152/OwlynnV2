import sys
import json
import traceback
import io
import os
import signal
import threading
from contextlib import redirect_stdout, redirect_stderr

_globals = {}

# ── Restricted builtins for sandboxed execution ──────────────────────────
_SAFE_BUILTINS = (
    {
        k: v
        for k, v in __builtins__.items()
        if k
        not in (
            "exec",
            "eval",
            "compile",
            "__import__",
            "open",
            "breakpoint",
            "exit",
            "quit",
            "globals",
            "locals",
            "vars",
            "dir",
            "help",
            "memoryview",
            "classmethod",
            "staticmethod",
            "super",
            "type",
            "__build_class__",
            "__subclasshook__",
            "__init_subclass__",
            "__new__",
            "__class__",
        )
    }
    if isinstance(__builtins__, dict)
    else {
        k: getattr(__builtins__, k)
        for k in dir(__builtins__)
        if not k.startswith("_")
        and k
        not in (
            "exec",
            "eval",
            "compile",
            "__import__",
            "open",
            "breakpoint",
            "exit",
            "quit",
            "globals",
            "locals",
            "vars",
            "dir",
            "help",
            "memoryview",
            "classmethod",
            "staticmethod",
            "super",
            "type",
        )
    }
)

# Allow safe imports via a custom __import__ that whitelists modules
_ALLOWED_MODULES = {
    "math",
    "random",
    "datetime",
    "json",
    "csv",
    "re",
    "collections",
    "itertools",
    "functools",
    "string",
    "textwrap",
    "unicodedata",
    "statistics",
    "decimal",
    "fractions",
    "copy",
    "pprint",
    "typing",
    "dataclasses",
    "enum",
    # NOTE: pathlib and os.path intentionally excluded.
    # pathlib.Path.read_bytes() / write_bytes() bypass the removed `open` builtin
    # by calling OS-level syscalls directly, enabling sandbox escape.
    # pathlib also exposes pathlib.os which gives access to os.system.
    "hashlib",
    "hmac",
    "secrets",
    "base64",
    "binascii",
    "time",
    "calendar",
    "locale",
    "operator",
    "numpy",
    "pandas",
    "matplotlib",
    "seaborn",
    "scipy",
    "sklearn",
    "PIL",
}


def _safe_import(name, *args, **kwargs):
    """Restricted import that only allows whitelisted modules."""
    base = name.split(".")[0]
    if base not in _ALLOWED_MODULES:
        raise ImportError(f"Import of '{name}' is not allowed in sandboxed mode")
    return __import__(name, *args, **kwargs)


_SAFE_BUILTINS["__import__"] = _safe_import


def _timeout_handler(_signum, _frame):
    raise TimeoutError("Code execution timed out (30 second limit)")


def main():
    # Initialize globals with restricted builtins
    _globals["__builtins__"] = _SAFE_BUILTINS

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                # Parent closed pipe or died, shutdown naturally
                break

            line = line.strip()
            if not line:
                continue

            payload = json.loads(line)

            if payload.get("action") == "reset":
                _globals.clear()
                sys.stdout.write(json.dumps({"status": "reset"}) + "\n")
                sys.stdout.flush()
                continue

            if payload.get("action") == "vars":
                user_vars = {
                    k: type(v).__name__
                    for k, v in _globals.items()
                    if not k.startswith("_") and k not in ("__builtins__",)
                }
                sys.stdout.write(json.dumps({"vars": user_vars}) + "\n")
                sys.stdout.flush()
                continue

            if payload.get("action") == "run":
                code = payload.get("code", "")
                workspace_dir = payload.get("workspace_dir", "")

                _globals["WORKSPACE_DIR"] = workspace_dir

                stdout_buf = io.StringIO()
                stderr_buf = io.StringIO()

                error_str = ""
                try:
                    # Set timeout alarm (30 seconds)
                    signal.signal(signal.SIGALRM, _timeout_handler)
                    signal.alarm(30)

                    with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                        try:
                            compiled = compile(code, "<cell>", "exec")
                            exec(compiled, _globals)
                        except SyntaxError:
                            # Maybe it's a single expression
                            try:
                                result = eval(code, _globals)
                                if result is not None:
                                    print(repr(result))
                            except Exception:
                                raise
                except TimeoutError:
                    error_str = (
                        "TimeoutError: Code execution timed out (30 second limit)"
                    )
                except Exception:
                    error_str = traceback.format_exc()
                finally:
                    # Cancel alarm
                    signal.alarm(0)

                out = stdout_buf.getvalue()
                err = stderr_buf.getvalue()

                response = {"stdout": out, "stderr": err, "error": error_str}
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                continue

        except EOFError:
            break
        except Exception as e:
            try:
                sys.stdout.write(
                    json.dumps({"error": f"Worker internal error: {str(e)}"}) + "\n"
                )
                sys.stdout.flush()
            except Exception:
                pass  # stdout write failed; parent will see worker timeout


if __name__ == "__main__":
    main()
