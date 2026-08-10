from langchain_core.tools import tool
import subprocess
import os
import shutil
from pathlib import Path


@tool
def ingest_github_repo(repo_url: str) -> str:
    """Clones a GitHub repo and reads its markdown/code files into the workspace."""
    from src.tools.url_policy import url_fetch_blocked_reason
    from src.config.settings import WORKSPACE_DIR

    # Validate URL against SSRF policy — blocks file://, private IPs, localhost
    reason = url_fetch_blocked_reason(repo_url)
    if reason:
        return f"Blocked: {reason}"

    # Sanitize repo name — strip path separators and traversal sequences
    raw_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    repo_name = "".join(c for c in raw_name if c.isalnum() or c in "-_.")
    if not repo_name:
        return "Invalid repo URL — cannot derive safe directory name."

    # Always clone into workspace, not cwd
    target_dir = str(WORKSPACE_DIR / repo_name)
    if not target_dir.startswith(str(WORKSPACE_DIR)):
        return "Access denied: target directory is outside workspace."

    result = subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, target_dir],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        return f"Clone failed: {result.stderr[:500]}"
    return f"Cloned {repo_url} into {target_dir}."


@tool
def ingest_youtube_transcript(video_url: str) -> str:
    """Fetches the transcript of a YouTube video using youtube-transcript-api."""
    from youtube_transcript_api import YouTubeTranscriptApi
    from src.config.settings import WORKSPACE_DIR

    video_id = video_url.split("v=")[-1].split("&")[0]
    # Sanitize video_id — only allow alphanumeric and -_
    video_id = "".join(c for c in video_id if c.isalnum() or c in "-_")
    if not video_id or len(video_id) > 20:
        return "Invalid YouTube video URL."

    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        text = "\n".join([t["text"] for t in transcript])
        path = str(WORKSPACE_DIR / f"{video_id}_transcript.txt")
        with open(path, "w") as f:
            f.write(text)
        return f"Saved transcript to {path}."
    except Exception as e:
        return f"Failed to get transcript: {e}"


@tool
def ingest_obsidian_vault(vault_path: str) -> str:
    """Copies .md files from an Obsidian vault into the workspace."""
    from src.config.settings import WORKSPACE_DIR

    # Validate vault_path is under the user's home directory
    vault = Path(vault_path).expanduser().resolve()
    home = Path.home()
    if not str(vault).startswith(str(home)):
        return f"Access denied: vault_path must be under your home directory ({home})."
    if not vault.is_dir():
        return f"vault_path does not exist or is not a directory: {vault}"

    target_dir = WORKSPACE_DIR / "obsidian_import"
    target_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for root, _, files in os.walk(vault):
        for file in files:
            if file.endswith(".md"):
                src = Path(root) / file
                # Flatten to single directory to avoid path traversal via nested vault dirs
                dst = target_dir / Path(file).name
                shutil.copy2(src, dst)
                count += 1
    return f"Imported {count} markdown files into {target_dir}."
