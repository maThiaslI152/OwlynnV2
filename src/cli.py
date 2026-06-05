"""
Owlynn CLI — Command-Line Interface for Local AI Cowork Agent
============================================================

Provides power users with a terminal interface to query the running agent,
stream responses, and check server status.
"""

import os
import sys
import json
import click
import httpx

import logging
logger = logging.getLogger(__name__)
DEFAULT_URL = "http://127.0.0.1:8000"


def get_base_url() -> str:
    return os.getenv("OWLYNN_URL", DEFAULT_URL).rstrip("/")


@click.group()
def cli():
    """Owlynn local AI coworker command line helper."""
    pass


@cli.command()
@click.argument("prompt")
@click.option("--project", default="default", help="Project workspace ID")
@click.option(
    "--approve-sensitive", is_flag=True, help="Auto-approve sensitive tool calls"
)
def query(prompt: str, project: str, approve_sensitive: bool):
    """Send a single prompt to the agent and display the response."""
    url = f"{get_base_url()}/v1/chat/completions"

    payload = {
        "model": "qwen2.5-3b",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "project_id": project,
        "auto_approve_sensitive": approve_sensitive,
    }

    click.echo(f"Sending prompt to agent (project: {project})...")

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, json=payload)

            if response.status_code != 200:
                click.echo(f"Error: Server returned status {response.status_code}")
                try:
                    click.echo(response.json())
                except Exception as e:
                    logger.warning("Error suppressed: %s", e)
                    click.echo(response.text[:200])
                sys.exit(1)

            data = response.json()
            choices = data.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                click.echo("\n--- Agent Response ---")
                click.echo(content)
            else:
                click.echo("Error: No choices in response payload.")
                click.echo(json.dumps(data, indent=2))

    except httpx.RequestError:
        click.echo(
            f"Failed to connect to agent server at {url}. Make sure start.sh is running."
        )
        sys.exit(1)


@cli.command()
@click.argument("prompt")
@click.option("--project", default="default", help="Project workspace ID")
@click.option(
    "--approve-sensitive", is_flag=True, help="Auto-approve sensitive tool calls"
)
def stream(prompt: str, project: str, approve_sensitive: bool):
    """Send a prompt and stream token chunks in real-time."""
    url = f"{get_base_url()}/v1/chat/completions"

    payload = {
        "model": "qwen2.5-3b",
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "project_id": project,
        "auto_approve_sensitive": approve_sensitive,
    }

    click.echo(f"Streaming prompt response (project: {project})...")
    click.echo("--- Agent Response ---", nl=True)

    try:
        with httpx.stream("POST", url, json=payload, timeout=60.0) as r:
            if r.status_code != 200:
                click.echo(f"Error: Server returned status {r.status_code}")
                sys.exit(1)

            for line in r.iter_lines():
                if not line.strip():
                    continue
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                click.echo(content, nl=False)
                                sys.stdout.flush()
                    except json.JSONDecodeError:
                        continue
            click.echo()  # final newline

    except httpx.RequestError:
        click.echo(
            f"Failed to connect to agent server at {url}. Make sure start.sh is running."
        )
        sys.exit(1)


@cli.command()
def status():
    """Check the connection and status of the local agent."""
    url = f"{get_base_url()}/api/health"
    try:
        response = httpx.get(url, timeout=5.0)
        if response.status_code == 200:
            click.echo("🟢 Owlynn Agent Server is running locally!")
            try:
                click.echo(json.dumps(response.json(), indent=2))
            except Exception as e:
                logger.warning("Error suppressed: %s", e)
                click.echo(f"Response: {response.text}")
        else:
            click.echo(f"🔴 Agent returned server status {response.status_code}")
    except httpx.RequestError:
        click.echo("🔴 Failed to connect to local Owlynn Agent server.")
        click.echo("   Run `./start.sh` or `uvicorn src.api.server:app` first.")


if __name__ == "__main__":
    cli()
