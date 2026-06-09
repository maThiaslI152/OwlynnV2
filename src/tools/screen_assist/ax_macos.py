"""macOS Accessibility + coordinate crop fallback."""

from __future__ import annotations

import asyncio
import platform
import tempfile
from pathlib import Path

from src.config.config_loader import config

_AX_SCRIPT = """
on run argv
  set coordX to item 1 of argv as integer
  set coordY to item 2 of argv as integer
  tell application "System Events"
    set frontProc to first application process whose frontmost is true
    set appName to name of frontProc
    set winName to ""
    try
      set winName to name of front window of frontProc
    end try
    set axText to ""
    try
      set focused to value of attribute "AXFocusedUIElement" of frontProc
      try
        set axText to value of focused
      end try
      if axText is missing value or axText is "" then
        try
          set axText to title of focused
        end try
      end if
    end try
    return appName & "|" & winName & "|" & coordX & "," & coordY & "|" & axText
  end tell
end run
"""


async def read_ax_context(x: int, y: int) -> tuple[str, bool]:
    """
    Read focused AX element context near ``(x, y)``.

    Returns ``(text, used_vision_fallback)``.
    """
    if platform.system() != "Darwin":
        return ("Error: Accessibility capture is macOS-only.", False)

    proc = await asyncio.create_subprocess_exec(
        "osascript",
        "-",
        str(x),
        str(y),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(_AX_SCRIPT.encode("utf-8"))
    if proc.returncode != 0:
        err = (stderr or b"").decode("utf-8", errors="replace").strip()
        return (f"Error: AX read failed ({err})", False)

    raw = (stdout or b"").decode("utf-8", errors="replace").strip()
    parts = raw.split("|", 3)
    app = parts[0] if len(parts) > 0 else ""
    window = parts[1] if len(parts) > 1 else ""
    coords = parts[2] if len(parts) > 2 else f"{x},{y}"
    ax_value = parts[3] if len(parts) > 3 else ""

    lines = [
        f"application={app}",
        f"window={window}",
        f"coords={coords}",
    ]
    if ax_value.strip():
        lines.append(f"ax_value={ax_value.strip()}")
        return ("\n".join(lines), False)

    crop_text = await _vision_crop_fallback(x, y)
    if crop_text:
        lines.append("source=vision_crop_fallback")
        lines.append(crop_text)
        return ("\n".join(lines), True)

    lines.append("ax_value=(empty — enable Accessibility for Owlynn/Python in System Settings)")
    return ("\n".join(lines), False)


async def _vision_crop_fallback(x: int, y: int) -> str:
    """512×512 crop around cursor when AX returns no text."""
    from src.agent.nodes.complex_utils.vision_proxy import transcribe_crop

    size = int(config.get("screen_assist.ax_blindspot_crop_size", 512))
    half = size // 2
    left = max(0, x - half)
    top = max(0, y - half)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        out_path = Path(tmp.name)

    try:
        proc = await asyncio.create_subprocess_exec(
            "screencapture",
            "-x",
            "-R",
            f"{left},{top},{size},{size}",
            str(out_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0 or not out_path.exists():
            err = (stderr or b"").decode("utf-8", errors="replace").strip()
            return f"vision_crop_failed: {err or proc.returncode}"

        image_bytes = out_path.read_bytes()
        if not image_bytes:
            return "vision_crop_failed: empty image"
        return await transcribe_crop(image_bytes, mime_type="image/png")
    except Exception as exc:
        return f"vision_crop_failed: {exc}"
    finally:
        out_path.unlink(missing_ok=True)
