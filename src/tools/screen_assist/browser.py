"""Active browser URL + optional Playwright DOM snapshot."""

from __future__ import annotations

import asyncio
import platform

_BROWSER_SCRIPT = """
set out to ""
try
  tell application "Google Chrome"
    if (count of windows) > 0 then
      set out to "chrome|" & (URL of active tab of front window) & "|" & (title of active tab of front window)
    end if
  end tell
end try
if out is "" then
  try
    tell application "Safari"
      if (count of windows) > 0 then
        set out to "safari|" & (URL of current tab of front window) & "|" & (name of current tab of front window)
      end if
    end tell
  end try
end if
if out is "" then
  try
    tell application "Arc"
      if (count of windows) > 0 then
        set out to "arc|" & (URL of active tab of front window) & "|" & (title of active tab of front window)
      end if
    end tell
  end try
end if
return out
"""


async def active_browser_tab() -> str:
    """Return ``browser|url|title`` via AppleScript."""
    if platform.system() != "Darwin":
        return "Error: browser URL detection is macOS-only."

    proc = await asyncio.create_subprocess_exec(
        "osascript",
        "-e",
        _BROWSER_SCRIPT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = (stderr or b"").decode("utf-8", errors="replace").strip()
        return f"Error: browser lookup failed ({err})"

    raw = (stdout or b"").decode("utf-8", errors="replace").strip()
    if not raw:
        return "No supported browser frontmost window (Chrome, Safari, Arc)."
    return raw


async def browser_dom_snapshot(cdp_url: str, *, max_chars: int = 8000) -> str:
    """Optional Playwright CDP snapshot when ``screen_assist.browser_cdp_url`` is set."""
    if not cdp_url.strip():
        return ""

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return "Error: playwright not installed."

    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(cdp_url)
            if not browser.contexts:
                return "Error: no browser contexts on CDP endpoint."
            page = browser.contexts[0].pages[0] if browser.contexts[0].pages else None
            if page is None:
                return "Error: no active page on CDP endpoint."
            title = await page.title()
            url = page.url
            text = await page.evaluate(
                "() => document.body ? document.body.innerText : ''"
            )
            text = (text or "")[:max_chars]
            return f"url={url}\ntitle={title}\n---\n{text}"
    except Exception as exc:
        return f"Error: CDP snapshot failed ({exc})"
