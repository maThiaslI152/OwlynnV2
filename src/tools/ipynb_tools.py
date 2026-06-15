"""Jupyter .ipynb read/write/export tools (no Jupyter kernel — execution via notebook_run)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from langchain_core.tools import tool

from src.tools.workspace_context import tool_workspace_root


def _resolve_path(filename: str) -> Path:
    root = Path(tool_workspace_root())
    path = (root / filename).resolve()
    if not str(path).startswith(str(root.resolve())):
        raise ValueError("Access denied: path outside workspace")
    return path


@tool
def read_ipynb(filename: str) -> str:
    """
    Read a Jupyter notebook (.ipynb) from the workspace and return a cell summary.

    Args:
        filename: Path relative to workspace (e.g. analysis.ipynb)
    """
    try:
        path = _resolve_path(filename)
    except ValueError as exc:
        return f"Error: {exc}"
    if not path.is_file():
        return f"Error: File not found: {filename}"
    if path.suffix.lower() != ".ipynb":
        return "Error: read_ipynb only supports .ipynb files."

    try:
        nb = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return f"Error: Invalid JSON in notebook: {exc}"

    cells = nb.get("cells") or []
    lines = [f"Notebook: {filename} ({len(cells)} cells)"]
    for idx, cell in enumerate(cells, start=1):
        ctype = cell.get("cell_type", "unknown")
        source = cell.get("source") or []
        if isinstance(source, list):
            text = "".join(source)
        else:
            text = str(source)
        preview = text.strip().replace("\n", " ")[:120]
        lines.append(f"  [{idx}] {ctype}: {preview or '(empty)'}")
    return "\n".join(lines)


@tool
def write_ipynb(filename: str, cells_json: str) -> str:
    """
    Create or overwrite a Jupyter notebook in the workspace.

    Args:
        filename: Output path (must end with .ipynb)
        cells_json: JSON array of cells, each with cell_type (markdown|code) and source (string)
    """
    if not filename.lower().endswith(".ipynb"):
        return "Error: filename must end with .ipynb"

    try:
        cells_in = json.loads(cells_json)
    except json.JSONDecodeError as exc:
        return f"Error: cells_json must be valid JSON array: {exc}"

    if not isinstance(cells_in, list):
        return "Error: cells_json must be a JSON array."

    cells = []
    for item in cells_in:
        if not isinstance(item, dict):
            return "Error: each cell must be an object."
        ctype = item.get("cell_type", "markdown")
        if ctype not in ("markdown", "code", "raw"):
            return f"Error: unsupported cell_type '{ctype}'."
        source = item.get("source", "")
        if isinstance(source, list):
            source_lines = source
        else:
            source_lines = str(source).splitlines(keepends=True)
            if source_lines and not source_lines[-1].endswith("\n"):
                source_lines[-1] += "\n"
        cell = {
            "cell_type": ctype,
            "metadata": item.get("metadata") or {},
            "source": source_lines,
        }
        if ctype == "code":
            cell["execution_count"] = None
            cell["outputs"] = item.get("outputs") or []
        cells.append(cell)

    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }

    try:
        path = _resolve_path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(notebook, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except ValueError as exc:
        return f"Error: {exc}"
    except OSError as exc:
        return f"Error writing notebook: {exc}"

    return f"Saved notebook {filename} ({len(cells)} cells)."


@tool
def export_ipynb_html(filename: str, output_html: str = "") -> str:
    """
    Export a workspace .ipynb notebook to standalone HTML via nbconvert (when available).

    Args:
        filename: Source .ipynb in workspace
        output_html: Optional output HTML filename (default: same stem + .html)
    """
    try:
        path = _resolve_path(filename)
    except ValueError as exc:
        return f"Error: {exc}"
    if not path.is_file():
        return f"Error: File not found: {filename}"

    out_name = output_html.strip() or f"{path.stem}.html"
    try:
        out_path = _resolve_path(out_name)
    except ValueError as exc:
        return f"Error: {exc}"

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "nbconvert",
                "--to",
                "html",
                "--output",
                out_path.name,
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(path.parent),
        )
    except subprocess.TimeoutExpired:
        return "Error: nbconvert timed out after 60s."
    except Exception as exc:
        return f"Error: nbconvert failed to start: {exc}"

    if result.returncode != 0:
        hint = result.stderr.strip() or result.stdout.strip()
        return f"Error: nbconvert export failed. Install with `pip install nbconvert`.\n{hint}"

    if not out_path.is_file():
        # nbconvert may write next to source with requested name
        alt = path.parent / out_path.name
        if alt.is_file():
            out_path = alt
        else:
            return f"Error: expected output at {out_name} but file was not created."

    return f"Exported {filename} → {out_name}. Embed inline with render_interactive_block(embed, ...)."
