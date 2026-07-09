from langchain_core.tools import tool
import subprocess, os, shutil


@tool
def ingest_github_repo(repo_url: str) -> str:
    """Clones a GitHub repo and reads its markdown/code files into the workspace."""
    repo_name = repo_url.split("/")[-1].replace(".git", "")
    target_dir = os.path.join(os.getcwd(), repo_name)
    subprocess.run(["git", "clone", repo_url, target_dir], check=False)
    return f"Cloned {repo_url} into {target_dir}."


@tool
def ingest_youtube_transcript(video_url: str) -> str:
    """Fetches the transcript of a YouTube video using youtube-transcript-api."""
    from youtube_transcript_api import YouTubeTranscriptApi

    video_id = video_url.split("v=")[-1].split("&")[0]
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        text = "\n".join([t["text"] for t in transcript])
        path = os.path.join(os.getcwd(), f"{video_id}_transcript.txt")
        with open(path, "w") as f:
            f.write(text)
        return f"Saved transcript to {path}."
    except Exception as e:
        return f"Failed to get transcript: {e}"


@tool
def ingest_obsidian_vault(vault_path: str) -> str:
    """Copies .md files from an Obsidian vault into the workspace."""
    target_dir = os.path.join(os.getcwd(), "obsidian_import")
    os.makedirs(target_dir, exist_ok=True)
    count = 0
    for root, _, files in os.walk(vault_path):
        for file in files:
            if file.endswith(".md"):
                shutil.copy2(os.path.join(root, file), os.path.join(target_dir, file))
                count += 1
    return f"Imported {count} markdown files."
