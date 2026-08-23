from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

router = APIRouter()

import asyncio
import json
import os

from src.api.shared import connected_websockets, logger
from src.config.audit_log import audit_info
from src.config.config_loader import config
from src.config.settings import WORKSPACE_DIR, get_project_workspace


def notify_file_processed(filepath_or_name, status="processed"):
    """Callback for FileWatcher background thread to broadcast over websockets and auto-index projects."""
    import os

    # Gracefully handle both full path and legacy plain filename
    filepath = (
        os.path.abspath(filepath_or_name)
        if (
            isinstance(filepath_or_name, str)
            and (os.path.isabs(filepath_or_name) or os.path.exists(filepath_or_name))
        )
        else filepath_or_name
    )
    filename = (
        os.path.basename(filepath) if isinstance(filepath, str) else str(filepath)
    )

    from src.api.server import app

    loop = getattr(app.state, "loop", None)
    if not loop:
        logger.warning("Loop not preserved, cannot notify websocket clients.")
        return

    # Broadcast to all active websockets
    for ws in list(connected_websockets):
        try:
            coro = ws.send_json(
                {"type": "file_status", "name": filename, "status": status}
            )
            asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception as e:
            logger.warning("Failed to send ws notification: %s", e)

    # Auto-index into project knowledge base if it's inside a project workspace and is successfully processed
    if status == "processed" and isinstance(filepath, str) and os.path.exists(filepath):
        from src.api.attachment_intake import is_vision_filename

        if is_vision_filename(filename):
            return
        try:
            rel_path = os.path.relpath(filepath, WORKSPACE_DIR)
            parts = rel_path.split(os.sep)
            if len(parts) >= 3 and parts[0] == "projects":
                project_id = parts[1]
                # Auto-index all projects, including default
                # Read the processed text format in .processed/
                # Check both project-local and root workspace cache paths
                project_workspace = get_project_workspace(project_id)
                root_processed = os.path.join(WORKSPACE_DIR, ".processed")
                cache_path = None

                for search_dir in [
                    root_processed,
                    os.path.join(project_workspace, ".processed"),
                ]:  # root first (fast path)
                    for ext in [".txt", ".md"]:
                        candidate = os.path.join(search_dir, filename + ext)
                        if os.path.exists(candidate):
                            cache_path = candidate
                            break
                    if cache_path:
                        break

                if cache_path:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        text = f.read()

                    if text and len(text.strip()) > 50:

                        async def index_task():
                            try:
                                # Broadcast indexing status
                                for ws in list(connected_websockets):
                                    try:
                                        coro = ws.send_json(
                                            {
                                                "type": "file_status",
                                                "name": filename,
                                                "status": "indexing",
                                            }
                                        )
                                        asyncio.run_coroutine_threadsafe(coro, loop)
                                    except Exception as e:
                                        logger.warning("Error suppressed: %s", e)

                                from src.memory.vector_lifecycle import (
                                    VectorLifecycleManager,
                                )

                                num_chunks = (
                                    await VectorLifecycleManager.index_processed_file(
                                        project_id, filename, text
                                    )
                                )

                                # Broadcast index success
                                for ws in list(connected_websockets):
                                    try:
                                        coro = ws.send_json(
                                            {
                                                "type": "file_status",
                                                "name": filename,
                                                "status": "indexed",
                                                "chunks": num_chunks,
                                            }
                                        )
                                        asyncio.run_coroutine_threadsafe(coro, loop)
                                    except Exception as e:
                                        logger.warning("Error suppressed: %s", e)
                            except Exception as e:
                                logger.error(
                                    "Failed to auto-index file %s: %s", filepath, e
                                )
                                # Broadcast index failure
                                for ws in list(connected_websockets):
                                    try:
                                        coro = ws.send_json(
                                            {
                                                "type": "file_status",
                                                "name": filename,
                                                "status": "indexing_failed",
                                                "error": str(e),
                                            }
                                        )
                                        asyncio.run_coroutine_threadsafe(coro, loop)
                                    except Exception as e:
                                        logger.warning("Error suppressed: %s", e)

                        asyncio.run_coroutine_threadsafe(index_task(), loop)
        except Exception as e:
            logger.error("Error in watcher auto-indexing: %s", e)


def render_pdf_as_composite(raw_bytes: bytes, max_pages: int = 10) -> str | None:
    """
    Render ALL PDF pages and stitch them into a single tall composite JPEG.

    Since mlx_vlm vision models may struggle with multiple separate image_url entries,
    we sidestep the issue by combining all pages into ONE image. The model can still
    see and read all pages in a single pass.

    Constraints:
    - Each page is scaled to a fixed width of 392px (14×28 — a known-safe patch width)
    - Heights are rounded to nearest multiple of 28
    - Pages separated by a thin white divider line for visual clarity
    - Final composite W and H must both be multiples of 28

    Returns: base64-encoded JPEG string, or None on failure.
    """
    PATCH_SIZE = int(config.get("pdf_rendering.patch_size", 28))
    PAGE_WIDTH = int(
        config.get("pdf_rendering.page_width", 392)
    )  # 14 × 28 — safe patch count
    DIVIDER_H = int(config.get("pdf_rendering.divider_height", 28))

    try:
        import base64
        from io import BytesIO

        import fitz
        from PIL import Image

        doc = fitz.open(stream=raw_bytes, filetype="pdf")
        page_imgs = []

        for i, page in enumerate(doc):
            if i >= max_pages:
                break

            # Render at 1x
            pix = page.get_pixmap(matrix=fitz.Matrix(1.0, 1.0), alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Scale to fixed width, preserve aspect ratio
            w, h = img.size
            scale = PAGE_WIDTH / w
            new_h = int(h * scale)
            # Snap height to multiple of 28
            new_h = max(PATCH_SIZE, (new_h // PATCH_SIZE) * PATCH_SIZE)
            img = img.resize((PAGE_WIDTH, new_h), Image.LANCZOS)
            page_imgs.append(img)
            logger.debug("Rendered page %s as %sx%s", i + 1, PAGE_WIDTH, new_h)

        if not page_imgs:
            return None

        # Stitch pages vertically with dividers
        divider = Image.new("RGB", (PAGE_WIDTH, DIVIDER_H), color=(220, 220, 220))
        total_h = sum(img.height for img in page_imgs) + DIVIDER_H * (
            len(page_imgs) - 1
        )
        # Snap total height to multiple of 28
        total_h = max(PATCH_SIZE, (total_h // PATCH_SIZE) * PATCH_SIZE)

        composite = Image.new("RGB", (PAGE_WIDTH, total_h), color=(255, 255, 255))
        y = 0
        for i, img in enumerate(page_imgs):
            composite.paste(img, (0, y))
            y += img.height
            if i < len(page_imgs) - 1:
                composite.paste(divider, (0, y))
                y += DIVIDER_H

        # Encode final composite
        buf = BytesIO()
        composite.save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode()
        logger.debug(
            "Composite image: %sx%s (%s pages)", PAGE_WIDTH, total_h, len(page_imgs)
        )
        return b64

    except Exception as e:
        logger.error("Composite rendering failed: %s", e)
        return None


def extract_text_file(name: str, mime: str, raw_bytes: bytes) -> str:
    """Decode a plain text or code file from raw bytes."""
    text_mimes = [
        "text/",
        "application/json",
        "application/xml",
        "application/javascript",
    ]
    text_exts = [
        ".py",
        ".js",
        ".ts",
        ".txt",
        ".md",
        ".csv",
        ".yaml",
        ".yml",
        ".sh",
        ".json",
        ".toml",
    ]
    is_text = any(mime.startswith(m) for m in text_mimes) or any(
        name.lower().endswith(e) for e in text_exts
    )
    if is_text:
        try:
            return raw_bytes.decode("utf-8", errors="replace")[
                : int(config.get("file_decode.max_chars", 8000))
            ]
        except Exception as e:
            logger.error("Error: %s", e)
            raise HTTPException(status_code=500, detail=str(e))
    return ""


@router.get("/api/tools")
async def api_get_tools():
    """Returns a list of available tools for the Customize view."""
    from src.agent.tool_sets import COMPLEX_TOOLS_WITH_WEB

    tools = []
    for t in COMPLEX_TOOLS_WITH_WEB:
        name = getattr(t, "name", str(t))
        desc = getattr(t, "description", "")
        if not desc and hasattr(t, "__doc__") and t.__doc__:
            desc = t.__doc__.strip().split("\n")[0]
        tools.append(
            {
                "name": name,
                "description": desc or "No description available.",
                "type": "core",
            }
        )
    return tools


@router.get("/api/artifacts")
async def api_get_artifacts(project_id: str = "default"):
    """List interactive blocks persisted under `{workspace}/.artifacts/`."""
    from src.config.settings import get_project_workspace, normalize_project_id

    base = get_project_workspace(normalize_project_id(project_id))
    art_dir = os.path.join(base, ".artifacts")
    if not os.path.isdir(art_dir):
        return {"status": "ok", "artifacts": []}

    artifacts = []
    for name in sorted(os.listdir(art_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(art_dir, name)
        try:
            with open(path, encoding="utf-8") as fh:
                record = json.load(fh)
            artifacts.append(
                {
                    "id": record.get("id") or name.replace(".json", ""),
                    "name": record.get("block_type", "block"),
                    "type": record.get("block_type", "interactive"),
                    "category": "interactive",
                    "description": json.dumps(record.get("payload", {}))[:200],
                }
            )
        except (json.JSONDecodeError, OSError):
            continue
    return {"status": "ok", "artifacts": artifacts}


@router.get("/api/files")
async def api_list_files(sub_path: str = "", project_id: str = "default"):
    """Returns a list of files in the workspace with processing status and folder support."""
    try:
        import urllib.parse

        sub_path = urllib.parse.unquote(sub_path)

        base_dir = get_project_workspace(project_id)
        target_dir = os.path.abspath(os.path.join(base_dir, sub_path))
        if not target_dir.startswith(os.path.abspath(base_dir)):
            return {"status": "error", "message": "Access denied"}

        files = []
        if not os.path.exists(target_dir):
            return []

        processed_dir = os.path.join(base_dir, ".processed")
        root_processed_dir = os.path.join(
            str(WORKSPACE_DIR), ".processed"
        )  # Legacy watcher cache location

        for f in os.listdir(target_dir):
            if f.startswith(".") or f == "__pycache__":
                continue
            filepath = os.path.join(target_dir, f)
            stats = os.stat(filepath)

            # Identify if item is Folder or File
            is_dir = os.path.isdir(filepath)

            # File extraction status cache check (project-local or root watcher cache)
            has_cache = False
            if not is_dir:
                has_cache = (
                    os.path.exists(os.path.join(processed_dir, f + ".txt"))
                    or os.path.exists(os.path.join(processed_dir, f + ".md"))
                    or os.path.exists(os.path.join(root_processed_dir, f + ".txt"))
                    or os.path.exists(os.path.join(root_processed_dir, f + ".md"))
                )

            files.append(
                {
                    "name": f,
                    "size": stats.st_size if not is_dir else 0,
                    "modified": stats.st_mtime,
                    "type": "folder" if is_dir else "file",
                    "status": "processed" if has_cache else "idle",
                }
            )
        return sorted(files, key=lambda x: (x["type"] == "file", x["name"].lower()))
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/files/{filename}")
async def api_get_file(
    filename: str, sub_path: str = "", project_id: str = "default", mode: str = ""
):
    """Serve/View a file from the workspace. mode=text returns processed text content."""
    import urllib.parse

    filename = urllib.parse.unquote(filename)
    sub_path = urllib.parse.unquote(sub_path)

    base_dir = get_project_workspace(project_id)
    target_dir = os.path.abspath(os.path.join(base_dir, sub_path))
    if not target_dir.startswith(os.path.abspath(base_dir)):
        return {"status": "error", "message": "Access denied"}

    filepath = os.path.abspath(os.path.join(target_dir, filename))
    if not filepath.startswith(os.path.abspath(base_dir)):
        return {"status": "error", "message": "Access denied"}
    if not os.path.exists(filepath):
        return {"status": "error", "message": "File not found"}

    # Text mode: return processed/cached text content
    if mode == "text":
        # Check project-local .processed dir first, then root workspace .processed
        project_processed_dir = os.path.join(os.path.abspath(base_dir), ".processed")
        root_processed_dir = os.path.join(
            os.path.abspath(str(WORKSPACE_DIR)), ".processed"
        )

        for pdir in [project_processed_dir, root_processed_dir]:
            for ext in [".txt", ".md"]:
                cached = os.path.join(pdir, filename + ext)
                if os.path.exists(cached):
                    with open(cached, "r", encoding="utf-8") as f:
                        return PlainTextResponse(f.read())
        # Fallback: try reading as text directly
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return PlainTextResponse(f.read())
        except Exception as e:
            logger.error("Error: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    return FileResponse(filepath)


@router.delete("/api/files/{filename}")
async def api_delete_file(
    filename: str, sub_path: str = "", project_id: str = "default"
):
    """Deletes a file and its processed cache from the workspace."""
    try:
        import urllib.parse

        filename = urllib.parse.unquote(filename)
        sub_path = urllib.parse.unquote(sub_path)

        base_dir = get_project_workspace(project_id)
        target_dir = os.path.abspath(os.path.join(base_dir, sub_path))
        if not target_dir.startswith(os.path.abspath(base_dir)):
            return {"status": "error", "message": "Access denied"}

        filepath = os.path.abspath(os.path.join(target_dir, filename))
        if not filepath.startswith(os.path.abspath(base_dir)):
            return {"status": "error", "message": "Access denied"}
        if os.path.exists(filepath):
            if os.path.isdir(filepath):
                import shutil

                shutil.rmtree(filepath)  # Support deleting folders recursively!
            else:
                os.remove(filepath)

        # Clean up cache
        processed_dir = os.path.join(base_dir, ".processed")
        for cache_ext in [".txt", ".md"]:
            cache_path = os.path.join(processed_dir, filename + cache_ext)
            if os.path.exists(cache_path):
                os.remove(cache_path)

        # Broadcast removal to websocket
        notify_file_processed(filename, status="deleted")
        return {"status": "ok", "message": f"Deleted {filename}"}
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/files/{filename}/rename")
async def api_rename_file(filename: str, body: dict):
    """Renames a file in the workspace."""
    try:
        import urllib.parse

        filename = urllib.parse.unquote(filename)
        new_name = body.get("new_name")
        sub_path = urllib.parse.unquote(body.get("sub_path", ""))
        project_id = body.get("project_id", "default")

        if not new_name:
            return {"status": "error", "message": "new_name is required"}

        base_dir = get_project_workspace(project_id)
        target_dir = os.path.abspath(os.path.join(base_dir, sub_path))
        if not target_dir.startswith(os.path.abspath(base_dir)):
            return {"status": "error", "message": "Access denied"}

        old_path = os.path.abspath(os.path.join(target_dir, filename))
        new_path = os.path.abspath(os.path.join(target_dir, new_name))
        if not old_path.startswith(
            os.path.abspath(base_dir)
        ) or not new_path.startswith(os.path.abspath(base_dir)):
            return {"status": "error", "message": "Access denied"}

        if not os.path.exists(old_path):
            return {"status": "error", "message": "File not found"}
        if os.path.exists(new_path):
            return {"status": "error", "message": "File with new name already exists"}

        os.rename(old_path, new_path)

        # Rename cache too
        processed_dir = os.path.join(base_dir, ".processed")
        for cache_ext in [".txt", ".md"]:
            old_cache = os.path.join(processed_dir, filename + cache_ext)
            new_cache = os.path.join(processed_dir, new_name + cache_ext)
            if os.path.exists(old_cache):
                os.rename(old_cache, new_cache)

        notify_file_processed(filename, status="deleted")
        notify_file_processed(new_name, status="processed")

        return {"status": "ok", "message": f"Renamed to {new_name}"}
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/files/{filename}/move")
async def api_move_file(filename: str, body: dict):
    """Moves a file or folder into another subdirectory within the project workspace."""
    try:
        import urllib.parse

        filename = urllib.parse.unquote(filename)
        current_sub_path = urllib.parse.unquote(body.get("current_sub_path", ""))
        target_sub_path = urllib.parse.unquote(body.get("target_sub_path", ""))
        project_id = body.get("project_id", "default")

        base_dir = get_project_workspace(project_id)
        src_dir = os.path.abspath(os.path.join(base_dir, current_sub_path))
        dst_dir = os.path.abspath(os.path.join(base_dir, target_sub_path))

        if not src_dir.startswith(os.path.abspath(base_dir)) or not dst_dir.startswith(
            os.path.abspath(base_dir)
        ):
            return {"status": "error", "message": "Access denied"}

        old_path = os.path.abspath(os.path.join(src_dir, filename))
        new_path = os.path.abspath(os.path.join(dst_dir, filename))
        if not old_path.startswith(
            os.path.abspath(base_dir)
        ) or not new_path.startswith(os.path.abspath(base_dir)):
            return {"status": "error", "message": "Access denied"}

        if not os.path.exists(old_path):
            return {"status": "error", "message": f"Source file not found: {filename}"}
        if os.path.exists(new_path):
            return {
                "status": "error",
                "message": "Destination already contains an item with this name",
            }

        os.rename(old_path, new_path)
        return {"status": "ok", "message": f"Moved {filename} to {target_sub_path}"}
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/upload")
async def api_upload_file(
    file: UploadFile = File(...), sub_path: str = "", project_id: str = "default"
):
    """Saves a file directly to the workspace. Auto-indexes into project knowledge base for non-default projects."""
    try:
        import urllib.parse

        sub_path = urllib.parse.unquote(sub_path)
        base_dir = get_project_workspace(project_id)

        target_dir = os.path.abspath(os.path.join(base_dir, sub_path))
        if not target_dir.startswith(os.path.abspath(base_dir)):
            return {"status": "error", "message": "Access denied"}

        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        filepath = os.path.abspath(os.path.join(target_dir, file.filename))
        if not filepath.startswith(os.path.abspath(base_dir)):
            return {"status": "error", "message": "Access denied"}

        # Explicitly uploaded by user: bypass Eco-Mode watchdog skip
        from src.api.file_processor import FORCE_PROCESS_FILES

        FORCE_PROCESS_FILES.add(filepath)

        # Enforce a 200MB upload cap before reading into memory.
        _MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB
        file_bytes = await file.read(_MAX_UPLOAD_BYTES + 1)
        if len(file_bytes) > _MAX_UPLOAD_BYTES:
            return {
                "status": "error",
                "message": "File too large. Maximum upload size is 200 MB.",
            }
        with open(filepath, "wb") as f:
            f.write(file_bytes)

        # Auto-index into project knowledge base for all projects
        import asyncio

        from src.api.server import _auto_index_project_file

        asyncio.create_task(
            _auto_index_project_file(project_id, file.filename, filepath, file_bytes)
        )

        audit_info(
            "api.file",
            "file_uploaded",
            name=file.filename,
            size_bytes=len(file_bytes),
            project_id=project_id,
        )
        return {"status": "ok", "message": f"Uploaded {file.filename}"}
    except Exception as e:
        logger.error("Error: %s", e)
        audit_info(
            "api.file",
            "file_upload_failed",
            name=file.filename if file else "unknown",
            error=str(e)[:120],
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/folders")
async def api_create_folder(body: dict):
    """Creates a new directory in the workspace."""
    try:
        import urllib.parse

        name = body.get("name")
        sub_path = urllib.parse.unquote(body.get("sub_path", ""))
        project_id = body.get("project_id", "default")

        if not name:
            return {"status": "error", "message": "Folder name is required"}

        base_dir = get_project_workspace(project_id)
        target_dir = os.path.abspath(os.path.join(base_dir, sub_path, name))
        if not target_dir.startswith(os.path.abspath(base_dir)):
            return {"status": "error", "message": "Access denied"}

        if os.path.exists(target_dir):
            return {"status": "error", "message": "Folder already exists"}

        os.makedirs(target_dir, exist_ok=True)
        return {"status": "ok", "message": f"Created folder {name}"}
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
