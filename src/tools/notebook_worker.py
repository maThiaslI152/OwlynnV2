import sys
import json
import traceback
import io
import os
import threading
from contextlib import redirect_stdout, redirect_stderr

_globals = {}


def main():
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
                except Exception:
                    error_str = traceback.format_exc()

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
