#!/usr/bin/env python3
import asyncio
import os
import sys
import argparse
import subprocess
import httpx
from pathlib import Path


def kill_process_on_port(port: int):
    try:
        # lsof -ti :<port>
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"], capture_output=True, text=True
        )
        pids = result.stdout.strip().split("\n")
        for pid in pids:
            if pid:
                subprocess.run(["kill", "-9", pid])
                print(f"Killed process {pid} on port {port}")
    except Exception as e:
        print(f"Error killing process on port {port}: {e}")


async def wait_for_backend(url="http://127.0.0.1:8000/api/health", timeout=30):
    async with httpx.AsyncClient() as client:
        for _ in range(timeout):
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return True
            except httpx.RequestError:
                pass
            await asyncio.sleep(1)
    return False


async def wait_for_frontend(url="http://127.0.0.1:5173", timeout=60):
    async with httpx.AsyncClient() as client:
        for _ in range(timeout):
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return True
                else:
                    print(f"Frontend returned status code {resp.status_code}")
                    return True  # Vite might return something else if routing is involved, we just need it to be up
            except httpx.RequestError as e:
                pass
            await asyncio.sleep(1)
    return False


async def main():
    parser = argparse.ArgumentParser(
        description="Automated runner for Extension Evaluation"
    )
    parser.add_argument(
        "--local-cloud",
        action="store_true",
        help="Run completely locally using LM Studio",
    )
    parser.add_argument("--track", type=str, help="Specify track to run (e.g. EX6)")
    args, unknown_args = parser.parse_known_args()

    print("Cleaning up ports...")
    kill_process_on_port(8000)
    kill_process_on_port(5173)

    env = os.environ.copy()
    if not env.get("OWLYNN_LOCAL_RUN_TOKEN"):
        import secrets

        env["OWLYNN_LOCAL_RUN_TOKEN"] = secrets.token_urlsafe(32)
        print(f"Generated test token: {env['OWLYNN_LOCAL_RUN_TOKEN']}")

    if args.local_cloud:
        print("Running in --local-cloud mode")
        env["CLOUD_LLM_BASE_URL"] = "http://127.0.0.1:1234/v1"
        env["CLOUD_LLM_MODEL_NAME"] = "qwen3-vl-4b-instruct-c_abliterated-v2-mlx"
        env["DEEPSEEK_API_KEY"] = "sk-local-mock-key"

    backend_proc = None
    frontend_proc = None

    repo_root = Path(__file__).resolve().parents[1]

    try:
        print("Starting backend...")
        backend_proc = await asyncio.create_subprocess_exec(
            "uv",
            "run",
            "python",
            "-m",
            "uvicorn",
            "src.api.server:app",
            "--port",
            "8000",
            env=env,
            cwd=str(repo_root),
        )

        print("Starting frontend...")
        frontend_proc = await asyncio.create_subprocess_exec(
            "npm",
            "run",
            "dev",
            "--",
            "--host",
            "127.0.0.1",
            env=env,
            cwd=str(repo_root / "frontend-v2"),
        )

        print("Waiting for backend health...")
        backend_ready = await wait_for_backend()
        if not backend_ready:
            print("Backend failed to start.")
            sys.exit(1)

        if args.local_cloud:
            print("Forcing local cloud settings via API...")
            async with httpx.AsyncClient() as client:
                await client.put(
                    "http://127.0.0.1:8000/api/unified-settings",
                    headers={
                        "X-Owlynn-Run-Token": env.get("OWLYNN_LOCAL_RUN_TOKEN", "")
                    },
                    json={
                        "cloud_llm_base_url": "http://127.0.0.1:1234/v1",
                        "cloud_llm_model_name": "qwen3-vl-4b-instruct-c_abliterated-v2-mlx",
                    },
                )

        print("Waiting for frontend health...")
        frontend_ready = await wait_for_frontend()
        if not frontend_ready:
            print("Frontend failed to start.")
            sys.exit(1)

        print("Servers are ready. Running evaluation suite...")
        cmd = ["python", "scripts/run_extension_eval.py"]
        if args.track:
            cmd.extend(["--track", args.track])
        cmd.extend(unknown_args)

        eval_proc = await asyncio.create_subprocess_exec(
            *cmd, env=env, cwd=str(repo_root)
        )
        await eval_proc.wait()

        sys.exit(eval_proc.returncode)

    except Exception as e:
        print(f"Error occurred: {e}")
        sys.exit(1)
    finally:
        print("Shutting down processes...")
        if backend_proc and backend_proc.returncode is None:
            backend_proc.terminate()
            try:
                await asyncio.wait_for(backend_proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                backend_proc.kill()

        if frontend_proc and frontend_proc.returncode is None:
            frontend_proc.terminate()
            try:
                await asyncio.wait_for(frontend_proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                frontend_proc.kill()

        # Double check cleanup
        kill_process_on_port(8000)
        kill_process_on_port(5173)
        print("Cleanup complete.")


if __name__ == "__main__":
    asyncio.run(main())
