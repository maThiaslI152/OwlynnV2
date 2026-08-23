import logging
import os

logger = logging.getLogger(__name__)


class VectorLifecycleManager:
    @staticmethod
    async def on_file_deleted(workspace_dir: str, filename: str):
        """Handle physical file deletion from a workspace."""
        from src.config.settings import WORKSPACE_DIR

        try:
            rel_path = os.path.relpath(workspace_dir, WORKSPACE_DIR)
            parts = rel_path.split(os.sep)
            if len(parts) >= 2 and parts[0] == "projects":
                project_id = parts[1]
            elif (
                workspace_dir == str(WORKSPACE_DIR)
                or workspace_dir == str(WORKSPACE_DIR) + "/"
            ):
                project_id = "default"
            else:
                return
        except ValueError:
            return

        logger.info(f"VectorLifecycle: File deleted {filename} in project {project_id}")

        # 1. Delete from Qdrant and project_manager knowledge
        from src.memory.project import project_manager

        await project_manager.remove_knowledge(project_id, filename)

        # 2. Delete from .processed cache
        processed_dir = os.path.join(workspace_dir, ".processed")
        for ext in [".txt", ".md"]:
            cache_path = os.path.join(processed_dir, filename + ext)
            if os.path.exists(cache_path):
                try:
                    os.remove(cache_path)
                except OSError as e:
                    logger.warning(f"Could not remove cache {cache_path}: {e}")

    @staticmethod
    async def on_file_renamed(workspace_dir: str, old_filename: str, new_filename: str):
        """Handle physical file renaming/moving."""
        logger.info(f"VectorLifecycle: File renamed {old_filename} -> {new_filename}")

        # 1. Delete old metadata
        await VectorLifecycleManager.on_file_deleted(workspace_dir, old_filename)

        # 2. Re-index new file (FileWatcher on_modified will handle this if the new file is written to,
        # but on_moved needs explicit trigger if the file content wasn't modified)
        from src.api.file_processor import FileWatcherHandler

        handler = FileWatcherHandler(workspace_dir)
        new_filepath = os.path.join(workspace_dir, new_filename)
        if os.path.exists(new_filepath):
            handler.process_file(new_filepath)

    @staticmethod
    async def index_processed_file(project_id: str, filename: str, text: str) -> int:
        """Centralized indexing path. De-duplicates previous chunks before indexing and skips identical files."""
        import hashlib
        import json

        from src.api.attachment_intake import is_vision_filename
        from src.config.settings import get_project_workspace

        if is_vision_filename(filename):
            logger.info(
                "VectorLifecycle: skipping RAG index for vision-only file %s",
                filename,
            )
            return 0

        if not text or len(text.strip()) < 50:
            return 0

        # 1. Delta-Indexing: Check if file content has changed using MD5
        file_hash = hashlib.md5(text.encode("utf-8")).hexdigest()

        project_workspace = get_project_workspace(project_id)
        hashes_path = os.path.join(project_workspace, ".processed", "hashes.json")

        file_hashes = {}
        if os.path.exists(hashes_path):
            try:
                with open(hashes_path, "r", encoding="utf-8") as f:
                    file_hashes = json.load(f)
            except Exception:
                pass

        if file_hashes.get(filename) == file_hash:
            logger.info(
                "VectorLifecycle: File %s has not changed, skipping indexing.", filename
            )
            return 0

        # Update hash record
        file_hashes[filename] = file_hash
        try:
            with open(hashes_path, "w", encoding="utf-8") as f:
                json.dump(file_hashes, f)
        except Exception as e:
            logger.warning(f"Could not save hash for {filename}: {e}")

        from src.memory.project import project_manager

        # 2. Delete old vectors for this file to prevent duplicates (H1)
        await project_manager.remove_knowledge(project_id, filename)

        # 3. Index new chunks using Langchain Text Splitter
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        from src.config.config_loader import config

        chunk_size = int(config.get("file_indexing.chunk_size", 1500))
        overlap = int(config.get("file_indexing.overlap", 200))
        max_chunks = int(config.get("file_indexing.max_chunks", 20))

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            separators=["\n\n", "\n", " ", ""],
        )

        chunks = [c.strip() for c in splitter.split_text(text) if c.strip()]

        # Execute sequentially or chunked to avoid overloading memory
        chunks_to_index = chunks[:max_chunks]
        if chunks_to_index:
            await project_manager.index_knowledge_document(
                project_id, filename, chunks_to_index
            )

        logger.info(
            "Auto-indexed %d chunks of %s into project %s",
            len(chunks_to_index),
            filename,
            project_id,
        )
        return len(chunks_to_index)

    @staticmethod
    async def delete_project_cascade(project_id: str):
        """Handle complete project deletion including vectors and checkpoints (H2)"""
        logger.info(f"VectorLifecycle: Deleting project cascade {project_id}")

        # 1. Delete Qdrant vectors for the entire project
        from src.memory.long_term import memory

        if memory is not None:
            try:
                # Mem0 uses user_id="project:{project_id}"
                memory.delete_all(user_id=f"project:{project_id}")
            except Exception as e:
                logger.warning(
                    f"Failed to clear Mem0 vectors for project {project_id}: {e}"
                )

        # 2. Delete Checkpoints (graph state)
        # Checkpointer clears state if the sqlite file is removed, but for now we just delete the workspace directory
        # which project_manager.delete_project does.
        # If checkpointer uses the main sqlite DB, we might want to delete by thread_id.
        from src.memory.project import project_manager

        return await project_manager.delete_project(project_id)
