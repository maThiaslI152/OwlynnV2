"""
Web Tools: Search + Fetch
-------------------------
web_search           : Tiered reliability pipeline:
                       wttr.in (weather) -> SearXNG -> curl_cffi -> DDGS -> httpx -> Playwright.
fetch_webpage        : Static fetching via httpx + BeautifulSoup
fetch_webpage_dynamic: Dynamic fetching via Playwright
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from langchain_core.tools import tool
from src.config.settings import (
    SEARXNG_URL,
    WEB_SEARCH_ENABLE_BROWSER_FALLBACK,
    WEB_SEARCH_ENABLE_CURL_CFFI,
    WEB_SEARCH_TIMEOUT_SECONDS,
)
from src.config.config_loader import config

logger = logging.getLogger(__name__)

# Static HTML shorter than this may be an SPA shell; merge in meta/OG fallback text.
_FETCH_MIN_MEANINGFUL_TEXT = int(
    config.get("web_search.fetch_min_meaningful_text", 100)
)

_WEATHER_QUERY_RE = re.compile(
    r"\b(weather|forecast|temperature|rain|snow|humidity|celsius|fahrenheit|°f|°c)\b",
    re.IGNORECASE,
)

_BOT_BLOCK_MARKERS = (
    "cf-turnstile",
    "challenges.cloudflare.com",
    "checkpoint/challenge",
    "one last step",
    "verify you are human",
    "captcha",
    "are you a robot",
    "unusual traffic",
    "akamai bot",
)


@dataclass
class SearchAttempt:
    tier: str
    source: str
    status: str
    detail: str = ""


def detect_bot_block(html_content: str) -> bool:
    """Detect common anti-bot/challenge pages in HTML responses."""
    text = (html_content or "").lower()
    return any(m in text for m in _BOT_BLOCK_MARKERS)


def _bot_block_detail(html_content: str) -> str:
    text = (html_content or "").lower()
    if "cf-turnstile" in text or "challenges.cloudflare.com" in text:
        return "Cloudflare Turnstile challenge detected"
    if "akamai" in text:
        return "Akamai challenge detected"
    if "captcha" in text:
        return "CAPTCHA challenge detected"
    if "one last step" in text:
        return '"One last step" bot check interstitial detected'
    if "verify you are human" in text:
        return '"Verify you are human" interstitial detected'
    return "Anti-bot challenge detected"


def _structured_search_failure(
    query: str, attempts: list[SearchAttempt], extra: str = ""
) -> str:
    lines = [
        f'[web_search] Unable to retrieve online results for "{query}".',
    ]
    if extra:
        lines.append(extra)
    lines.extend(["", "Diagnostics:"])
    for a in attempts:
        detail = f" ({a.detail})" if a.detail else ""
        lines.append(f"- {a.tier} / {a.source}: {a.status}{detail}")
    lines.extend(
        [
            "",
            "This may be caused by anti-bot challenges, provider/API-key issues, or temporary network blocks.",
            "Try again with a narrower query, enable a search API key, or retry later.",
        ]
    )
    return "\n".join(lines)


def unwrap_redirect_search_url(url: str) -> str:
    """
    Expand common search-engine redirect URLs to the real http(s) destination.
    DuckDuckGo HTML results often use /l/?uddg=https%3A%2F%2F...
    """
    raw = (url or "").strip()
    if not raw.startswith("http"):
        return raw
    try:
        p = urlparse(raw)
        host = (p.netloc or "").lower()
        if "duckduckgo.com" in host:
            path = p.path or ""
            if path == "/l" or path.startswith("/l/"):
                uddg = (parse_qs(p.query).get("uddg") or [""])[0]
                if uddg:
                    return unquote(uddg)
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        pass
    return raw


def _get_ddgs_class():
    """Resolve DDGS from duckduckgo-search (PyPI: duckduckgo-search)."""
    try:
        from duckduckgo_search import DDGS  # type: ignore

        return DDGS
    except ImportError:
        pass
    try:
        from ddgs import DDGS  # type: ignore

        return DDGS
    except ImportError:
        return None


def _ddg_html_url(query: str, news: bool) -> str:
    q = quote_plus(query)
    base = f"https://html.duckduckgo.com/html/?q={q}"
    return f"{base}&ia=news" if news else base


def _parse_ddg_html_results(html: str, max_hits: int = 5) -> list[dict[str, str]]:
    """Extract result rows from DuckDuckGo HTML (lite / classic) response."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str]] = []

    def push(title: str, href: str, snippet: str) -> None:
        href = (href or "").strip()
        title = (title or "").strip()
        if not href or not title:
            return
        if href.startswith("//"):
            href = "https:" + href
        if not href.startswith("http"):
            return
        if any(r["href"] == href for r in results):
            return
        results.append({"title": title, "href": href, "body": snippet or "No snippet"})
        return None

    for a in soup.select("a.result__a"):
        href = (a.get("href") or "").strip()
        title = a.get_text(separator=" ", strip=True)
        snippet = ""
        sn = a.find_next_sibling("a", class_="result__snippet")
        if not sn:
            body = a.find_parent("div", class_="result__body")
            if body:
                sn = body.select_one("a.result__snippet")
        if sn:
            snippet = sn.get_text(separator=" ", strip=True)
        push(title, href, snippet)
        if len(results) >= max_hits:
            return results

    # DDG / layout variants
    for a in soup.select('a[href^="http"][class*="result"]'):
        if len(results) >= max_hits:
            break
        href = (a.get("href") or "").strip()
        push(a.get_text(separator=" ", strip=True), href, "")

    # lite.duckduckgo.com: results in table rows
    for tr in soup.select("table tr"):
        if len(results) >= max_hits:
            break
        link = tr.select_one('a[href^="http"]')
        if not link:
            continue
        t = link.get_text(separator=" ", strip=True)
        rest = tr.get_text(separator=" ", strip=True)
        snippet = rest.replace(t, "", 1).strip()[:400] if rest else ""
        push(t, link.get("href", ""), snippet)

    return results


def _parse_bing_html_results(html: str, max_hits: int = 8) -> list[dict[str, str]]:
    """Extract main web results from Bing SERP HTML."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, str]] = []
    for li in soup.select("li.b_algo"):
        if len(out) >= max_hits:
            break
        a = li.select_one("h2 a")
        if not a:
            continue
        href = (a.get("href") or "").strip()
        title = a.get_text(separator=" ", strip=True)
        if not href.startswith("http"):
            continue
        p = li.select_one(".b_caption p") or li.select_one("p")
        snippet = p.get_text(separator=" ", strip=True) if p else ""
        if any(x["href"] == href for x in out):
            continue
        out.append(
            {"title": title or "Result", "href": href, "body": snippet or "No snippet"}
        )
    return out


def _normalize_hits(raw: list[dict], max_hits: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for r in raw:
        title = str(r.get("title") or r.get("name") or "No title").strip()
        href = str(r.get("href") or r.get("url") or "").strip()
        body = str(
            r.get("body") or r.get("snippet") or r.get("description") or "No snippet"
        ).strip()
        if not href.startswith("http"):
            continue
        if not title:
            title = "Result"
        out.append({"title": title, "href": href, "body": body or "No snippet"})
        if len(out) >= max_hits:
            break
    return out


async def _web_search_curl_cffi(
    query: str, backend: str, news: bool, focus_query: str = ""
) -> tuple[str | None, SearchAttempt]:
    if not WEB_SEARCH_ENABLE_CURL_CFFI:
        return None, SearchAttempt(
            "tier1", "curl_cffi", "disabled", "WEB_SEARCH_ENABLE_CURL_CFFI=false"
        )
    try:
        from curl_cffi import requests as curl_requests  # type: ignore
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return None, SearchAttempt(
            "tier1", "curl_cffi", "unavailable_dependency", "curl_cffi not installed"
        )

    max_h = 15 if (focus_query or "").strip() else 5
    targets: list[tuple[str, str]] = []
    if backend in {"bing"}:
        targets.append(("bing", f"https://www.bing.com/search?q={quote_plus(query)}"))
    elif backend in {"duckduckgo"}:
        targets.append(("ddg", _ddg_html_url(query, news)))
        targets.append(
            ("ddg_lite", f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}")
        )
    else:
        targets.append(("ddg", _ddg_html_url(query, news)))
        targets.append(
            ("ddg_lite", f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}")
        )
        targets.append(("bing", f"https://www.bing.com/search?q={quote_plus(query)}"))

    def _get(url: str) -> str:
        r = curl_requests.get(
            url,
            impersonate="chrome120",
            timeout=WEB_SEARCH_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        r.raise_for_status()
        return r.text

    blocked_details: list[str] = []
    for source, url in targets:
        try:
            html = await asyncio.to_thread(_get, url)
        except Exception as e:
            logger.warning("Error suppressed: %s", e)
            blocked_details.append(f"{source}: {str(e)[:80]}")
            continue
        if detect_bot_block(html):
            blocked_details.append(f"{source}: {_bot_block_detail(html)}")
            continue
        if source == "bing":
            hits = _parse_bing_html_results(html, max_hits=max_h)
        else:
            hits = _parse_ddg_html_results(html, max_hits=max_h)
        if hits:
            hits = await _maybe_rerank_search_hits(focus_query, hits)
            return (
                _format_search_hits_markdown(
                    query, backend, news, hits, f"via curl_cffi/{source}"
                ),
                SearchAttempt("tier1", "curl_cffi", "ok", f"source={source}"),
            )
    if blocked_details:
        return None, SearchAttempt(
            "tier1",
            "curl_cffi",
            "blocked_by_captcha",
            "; ".join(blocked_details)[:220],
        )
    return None, SearchAttempt("tier1", "curl_cffi", "empty", "No parseable hits")


def _extract_wttr_location(query: str) -> str | None:
    """Best-effort place name for wttr.in when the query is weather-related."""
    if not _WEATHER_QUERY_RE.search(query):
        return None
    q = query.strip()
    # "weather in Bangkok today", "what's the weather in Paris"
    m = re.search(
        r"\bin\s+([a-zA-Z][a-zA-Z\s,.'-]{1,48}?)(?:\s+(?:today|now|tonight|please|right)\b|[?.!]|$)",
        q,
        re.IGNORECASE,
    )
    if m:
        loc = m.group(1).strip().rstrip(",.")
        if len(loc) >= 2:
            return loc[:60]
    m2 = re.search(
        r"^([a-zA-Z][a-zA-Z\s,.'-]{1,48}?)\s+(?:weather|forecast)\b",
        q,
        re.IGNORECASE,
    )
    if m2:
        return m2.group(1).strip()[:60]
    return None


async def _web_search_wttr_in(query: str, backend: str, news: bool) -> str | None:
    """Real-time weather via wttr.in (no API key) when the query looks like weather."""
    if news:
        return None
    loc = _extract_wttr_location(query)
    if not loc:
        return None
    import httpx

    path = quote_plus(loc)
    url = f"https://wttr.in/{path}?format=j1"
    headers = {"User-Agent": config.get("web_search.user_agents.weather", "Owlynn/1.0")}
    try:
        async with httpx.AsyncClient(
            timeout=float(config.get("web_search.timeouts.weather", 10.0)),
            headers=headers,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        data = json.loads(resp.text)
    except Exception as e:
        logger.warning("wttr.in failed: %s", e)
        return None

    try:
        cur = (data.get("current_condition") or [{}])[0]
        locn = (data.get("nearest_area") or [{}])[0]
        name = (locn.get("areaName") or [{}])[0].get("value", loc)
        country = (locn.get("country") or [{}])[0].get("value", "")
        temp_c = cur.get("temp_C", "?")
        feels = cur.get("FeelsLikeC", "?")
        desc = (cur.get("weatherDesc") or [{}])[0].get("value", "")
        hum = cur.get("humidity", "?")
        lines = [
            f'🔍 Weather for "{query}" (via wttr.in)',
            "",
            f"**{name}**{', ' + country if country else ''}",
            f"- **Now:** {desc}",
            f"- **Temperature:** {temp_c}°C (feels like {feels}°C)",
            f"- **Humidity:** {hum}%",
            "",
            f"URL: https://wttr.in/{path}",
        ]
        return "\n".join(lines)
    except Exception as e:
        logger.warning("wttr.in parse failed: %s", e)
        return None


async def _web_search_bing_httpx(
    query: str, backend: str, news: bool, focus_query: str = ""
) -> str | None:
    import httpx

    url = f"https://www.bing.com/search?q={quote_plus(query)}"
    if news:
        url = f"https://www.bing.com/news/search?q={quote_plus(query)}"
    headers = {
        "User-Agent": config.get(
            "web_search.user_agents.bing",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        ),
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        async with httpx.AsyncClient(
            timeout=float(config.get("web_search.timeouts.bing", 15.0)),
            headers=headers,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        if detect_bot_block(resp.text):
            logger.warning("Bing httpx blocked by challenge page")
            return None
        hits = _parse_bing_html_results(resp.text, max_hits=8)
    except Exception as e:
        logger.warning("Bing httpx search failed: %s", e)
        return None
    if not hits:
        return None
    hits = await _maybe_rerank_search_hits(focus_query, hits)
    return _format_search_hits_markdown(query, backend, news, hits, "via Bing (HTTP)")


async def _web_search_ddg_lite_httpx(
    query: str, backend: str, news: bool, focus_query: str = ""
) -> str | None:
    """Alternate DDG endpoint sometimes reachable when html.duckduckgo.com differs."""
    import httpx

    q = quote_plus(query)
    path = f"https://lite.duckduckgo.com/lite/?q={q}"
    if news:
        path += "&iar=news"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        async with httpx.AsyncClient(
            timeout=22.0, headers=headers, follow_redirects=True
        ) as client:
            resp = await client.get(path)
            resp.raise_for_status()
        if detect_bot_block(resp.text):
            logger.warning("DDG lite blocked by challenge page")
            return None
        max_h = 15 if (focus_query or "").strip() else 5
        results = _parse_ddg_html_results(resp.text, max_hits=max_h)
    except Exception as e:
        logger.warning("DDG lite httpx failed: %s", e)
        return None
    if not results:
        return None
    results = await _maybe_rerank_search_hits(focus_query, results)
    return _format_ddg_hits(query, backend, news, results, "via DDG Lite (HTTP)")


def _format_ddg_hits(
    query: str,
    backend: str,
    news: bool,
    results: list[dict[str, str]],
    via: str,
) -> str:
    return _format_search_hits_markdown(query, backend, news, results, via)


def _format_search_hits_markdown(
    query: str,
    backend: str,
    news: bool,
    hits: list[dict[str, str]],
    via: str,
) -> str:
    label = "News" if news else "Web"
    lines = [
        f'🔍 {label} search results for: "{query}" (Backend: {backend}, {via})',
        "",
    ]
    for i, r in enumerate(hits, 1):
        href = unwrap_redirect_search_url(r.get("href", "") or "")
        lines.append(f"**{i}. {r['title']}**")
        lines.append(f"   URL: {href}")
        lines.append(f"   {r['body']}")
        lines.append("")
    return "\n".join(lines)


async def _maybe_rerank_search_hits(
    focus_query: str, hits: list[dict[str, str]]
) -> list[dict[str, str]]:
    fq = (focus_query or "").strip()
    if not fq or len(hits) <= 1:
        return hits
    from src.tools.web_retrieval import rerank_search_hits

    return await rerank_search_hits(fq, hits)


async def _web_search_httpx_ddg_html(
    query: str, backend: str, news: bool, focus_query: str = ""
) -> str | None:
    """Plain HTTP GET to DDG HTML lite."""
    import httpx

    ddg_timeout = float(config.get("web_search.timeouts.ddg", 15.0))
    ddg_ua = config.get(
        "web_search.user_agents.ddg",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )

    url = _ddg_html_url(query, news)
    headers = {
        "User-Agent": ddg_ua,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        async with httpx.AsyncClient(
            timeout=ddg_timeout, headers=headers, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        text = resp.text
    except Exception as e:
        logger.warning("httpx DDG search failed: %s", e)
        return None

    if detect_bot_block(text):
        logger.warning("DDG HTML blocked by challenge page")
        return None

    # Some responses are minimal; try lxml parse
    max_h = 15 if (focus_query or "").strip() else 5
    results = _parse_ddg_html_results(text, max_hits=max_h)
    if not results:
        # Rare: anti-bot interstitial — try POST form DDG sometimes expects
        try:
            async with httpx.AsyncClient(
                timeout=ddg_timeout, headers=headers, follow_redirects=True
            ) as client:
                resp = await client.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": query, "b": ""},
                )
                resp.raise_for_status()
            results = _parse_ddg_html_results(resp.text, max_hits=max_h)
        except Exception as e:
            logger.debug("DDG POST fallback failed: %s", e)

    if not results:
        return None
    results = await _maybe_rerank_search_hits(focus_query, results)
    return _format_ddg_hits(query, backend, news, results, "via HTTP (DDG HTML)")


async def _google_search_playwright(query: str, focus_query: str = "") -> str:
    """Fallback Google search using Playwright to handle fragile selectors or CAPTCHAs."""
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # Navigate to Google with search query
            url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            await page.goto(url, wait_until="networkidle")
            content = await page.content()
            await browser.close()

            soup = BeautifulSoup(content, "lxml")

            # Check for CAPTCHA or Bot detection
            if "captcha" in content.lower() or "unusual traffic" in content.lower():
                logger.warning("Google search blocked by CAPTCHA")
                return "[google_search_playwright] Error: Blocked by Google CAPTCHA/Bot detection."

            results = []

            # Google results usually sit in 'div.g'
            for g in soup.find_all("div", class_="g"):
                title_el = g.find("h3")
                link_el = g.find("a")
                if title_el and link_el:
                    href = link_el.get("href")
                    if href and href.startswith("http"):
                        # Extract snippet - find div for snippet or iterate children
                        # Snippets often sit in -webkit-line-clamp divs or similar
                        # We will make copies of title/link to not destroy soup, or clone
                        # But simpler is getting all text excluding title/link
                        title_text = title_el.get_text()

                        # Copy 'g' and decompose title/link to get raw text snippet
                        # Wait, decomposing modifies the tree. We can just use text extraction.
                        # Using raw text for now
                        all_text = g.get_text(separator=" ", strip=True)
                        snippet = all_text.replace(title_text, "").strip()

                        results.append(
                            {
                                "title": title_text,
                                "href": href,
                                "body": snippet[:200] + "..."
                                if len(snippet) > 200
                                else snippet,
                            }
                        )

            if not results:
                # Let's try alternative selector for simple results
                # Sometimes Google shows 'kp-blk' or other things
                pass

            if not results:
                return f'No Google search results found for: "{query}" via Playwright.'

            max_h = 15 if (focus_query or "").strip() else 5
            hits = [
                {
                    "title": r["title"],
                    "href": r["href"],
                    "body": r["body"],
                }
                for r in results[:max_h]
            ]
            hits = await _maybe_rerank_search_hits(focus_query, hits)
            return _format_search_hits_markdown(
                query, "google", False, hits, "via Playwright"
            )
    except Exception as e:
        logger.error(f"_google_search_playwright error: {e}")
        return f"[google_search_playwright] Error: {str(e)}"


async def _web_search_dynamic_playwright(
    query: str, backend: str, news: bool, focus_query: str = ""
) -> tuple[str | None, SearchAttempt]:
    if not WEB_SEARCH_ENABLE_BROWSER_FALLBACK:
        return None, SearchAttempt(
            "tier3",
            "playwright_dynamic",
            "disabled",
            "WEB_SEARCH_ENABLE_BROWSER_FALLBACK=false",
        )
    try:
        from playwright.async_api import async_playwright
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return None, SearchAttempt(
            "tier3",
            "playwright_dynamic",
            "unavailable_dependency",
            "playwright not installed",
        )

    if backend == "duckduckgo":
        url = _ddg_html_url(query, news)
    elif news:
        url = f"https://www.bing.com/news/search?q={quote_plus(query)}"
    else:
        url = f"https://www.bing.com/search?q={quote_plus(query)}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=45000)
            html = await page.content()
            await browser.close()
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return None, SearchAttempt(
            "tier3", "playwright_dynamic", "network_error", str(e)[:180]
        )

    if detect_bot_block(html):
        return None, SearchAttempt(
            "tier3", "playwright_dynamic", "blocked_by_captcha", _bot_block_detail(html)
        )

    max_h = 15 if (focus_query or "").strip() else 5
    hits = _parse_bing_html_results(html, max_hits=max_h)
    if not hits:
        hits = _parse_ddg_html_results(html, max_hits=max_h)
    if not hits:
        return None, SearchAttempt(
            "tier3", "playwright_dynamic", "empty", "No parseable hits"
        )

    hits = await _maybe_rerank_search_hits(focus_query, hits)
    return (
        _format_search_hits_markdown(
            query, backend, news, hits, "via Playwright dynamic"
        ),
        SearchAttempt("tier3", "playwright_dynamic", "ok"),
    )


@tool
async def web_search(
    query: str,
    backend: str = "auto",
    news: bool = False,
    focus_query: str = "",
) -> str:
    """
    Searches the web and returns top results.

    Order: SearXNG → curl_cffi → DDGS → httpx → Playwright.
    ``backend="google"`` uses Playwright only.

    Use this to look up current information, documentation, definitions, or
    any topic the user asks about that isn't already in your knowledge.

    Args:
        query: A clear, specific search query string.
        backend: The search engine to use. Options: "auto" (default), "google", "bing", "duckduckgo", "wikipedia".
        news: Set to True if you are explicitly looking for CURRENT EVENTS,
              NEWS ARTICLES, or RECENT press releases.
        focus_query: Optional. When set, reranks result snippets for relevance to this text
              (e.g. the user's precise question). Leave empty to keep default result order.
    """
    try:
        backend = (backend or "auto").strip().lower()
        attempts: list[SearchAttempt] = []

        # Wrap the entire sequential search pipeline in an aggregate timeout
        # to prevent cascading tier fallbacks from eating the eval window.
        aggregate_timeout = float(config.get("web_search.timeouts.aggregate", 60.0))

        async def _search_pipeline():
            # Explicit backend handling
            if backend == "google":
                return await _google_search_playwright(query, focus_query)

            # Weather fast path
            if not news:
                wt = await _web_search_wttr_in(query, backend, news)
                if wt:
                    attempts.append(SearchAttempt("tier0", "wttr", "ok"))
                    return wt
                attempts.append(
                    SearchAttempt(
                        "tier0",
                        "wttr",
                        "empty",
                        "Not a weather query or wttr unavailable",
                    )
                )

            # Tier 0.5: SearXNG (self-hosted metasearch — no API keys, no bot blocking)
            if SEARXNG_URL:
                try:
                    from src.tools.web_search_enhanced import searxng_search

                    categories = "news" if news else "general"
                    max_r = 15 if (focus_query or "").strip() else 8
                    sx_hits = await searxng_search(
                        query, categories=categories, max_results=max_r
                    )
                    if sx_hits:
                        hits = [
                            {"title": h["title"], "href": h["href"], "body": h["body"]}
                            for h in sx_hits
                        ]
                        hits = await _maybe_rerank_search_hits(focus_query, hits)
                        attempts.append(SearchAttempt("tier0.5", "searxng", "ok"))
                        return _format_search_hits_markdown(
                            query, backend, news, hits, "via SearXNG"
                        )
                    attempts.append(
                        SearchAttempt("tier0.5", "searxng", "empty", "No results")
                    )
                except Exception as e:
                    logger.warning("Error suppressed: %s", e)
                    attempts.append(
                        SearchAttempt("tier0.5", "searxng", "error", str(e)[:120])
                    )

            # Tier 1B: curl_cffi browser-like TLS fallback
            curl_out, curl_attempt = await _web_search_curl_cffi(
                query, backend, news, focus_query
            )
            attempts.append(curl_attempt)
            if curl_out:
                return curl_out

            # Tier 2: DDGS API
            DDGS = _get_ddgs_class()
            if DDGS is not None:
                try:
                    max_r = 15 if (focus_query or "").strip() else 5

                    def _search():
                        with DDGS() as ddgs:
                            if news:
                                return ddgs.news(
                                    query, backend=backend, max_results=max_r
                                )
                            return ddgs.text(query, backend=backend, max_results=max_r)

                    results = await asyncio.to_thread(_search)
                except Exception as e:
                    logger.warning("Error suppressed: %s", e)
                    attempts.append(
                        SearchAttempt("tier2", "ddgs", "network_error", str(e)[:180])
                    )
                    results = None
                else:
                    if results:
                        hits = _normalize_hits(results, max_hits=max_r)
                        if hits:
                            hits = await _maybe_rerank_search_hits(focus_query, hits)
                            return _format_search_hits_markdown(
                                query, backend, news, hits, "via DDGS"
                            )
                    attempts.append(SearchAttempt("tier2", "ddgs", "empty", "No hits"))
            else:
                attempts.append(
                    SearchAttempt(
                        "tier2",
                        "ddgs",
                        "unavailable_dependency",
                        "duckduckgo-search not installed",
                    )
                )

            # Tier 2C: legacy HTTP parsers
            hx = await _web_search_httpx_ddg_html(query, backend, news, focus_query)
            attempts.append(
                SearchAttempt("tier2", "httpx_ddg_html", "ok" if hx else "empty")
            )
            if hx:
                return hx
            bi = await _web_search_bing_httpx(query, backend, news, focus_query)
            attempts.append(
                SearchAttempt("tier2", "httpx_bing_html", "ok" if bi else "empty")
            )
            if bi:
                return bi
            dl = await _web_search_ddg_lite_httpx(query, backend, news, focus_query)
            attempts.append(
                SearchAttempt("tier2", "httpx_ddg_lite", "ok" if dl else "empty")
            )
            if dl:
                return dl

            # Tier 3: dynamic browser fallback
            dyn_out, dyn_attempt = await _web_search_dynamic_playwright(
                query, backend, news, focus_query
            )
            attempts.append(dyn_attempt)
            if dyn_out:
                return dyn_out

            return _structured_search_failure(query, attempts)

        try:
            return await asyncio.wait_for(_search_pipeline(), timeout=aggregate_timeout)
        except asyncio.TimeoutError:
            return _structured_search_failure(
                query,
                attempts,
                extra=f"(Search timed out after {aggregate_timeout:.0f}s)",
            )
    except Exception as e:
        logger.error(f"web_search error: {e}")
        return f"[web_search] Error: {str(e)}"


def _html_static_fallback_text(html: str) -> str:
    """Title + meta/OG descriptions when the body is an empty SPA shell."""
    from bs4 import BeautifulSoup

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        soup = BeautifulSoup(html, "html.parser")
    chunks: list[str] = []
    title = soup.find("title")
    if title:
        t = title.get_text(separator=" ", strip=True)
        if t:
            chunks.append(f"Title: {t}")
    for attrs in (
        {"name": "description"},
        {"property": "og:title"},
        {"property": "og:description"},
    ):
        m = soup.find("meta", attrs=attrs)
        c = (m.get("content") or "").strip() if m else ""
        if c:
            chunks.append(c)
    seen: set[str] = set()
    out: list[str] = []
    for c in chunks:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return "\n".join(out)


def _html_to_plain_text(html: str) -> str:
    from bs4 import BeautifulSoup

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        soup = BeautifulSoup(html, "html.parser")
    for tag in soup(
        ["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]
    ):
        tag.decompose()
    main = (
        soup.find("article") or soup.find("main") or soup.find("section") or soup.body
    )
    text = (
        main.get_text(separator="\n", strip=True)
        if main
        else soup.get_text(separator="\n", strip=True)
    )
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


@tool
async def fetch_webpage(url: str, focus_query: str = "") -> str:
    """
    Fetches a webpage and returns readable text, or ranked excerpts when focus_query is set.

    After web_search, open 1–3 authoritative URLs with a precise ``focus_query`` matching
    what you need from the page; the tool returns embedding-ranked excerpts for long pages.

    Args:
        url: Full http(s) URL to fetch.
        focus_query: What to extract (e.g. the user's question). When non-empty and the page
            is long enough, returns numbered excerpts optimized for that query. When empty,
            returns a single truncated plain-text body (legacy behavior).
    """
    import httpx

    from src.tools.url_policy import url_fetch_blocked_reason
    from src.tools.web_retrieval import rank_chunks_to_source_pack

    url = unwrap_redirect_search_url(url.strip())
    blocked = url_fetch_blocked_reason(url)
    if blocked:
        return f"[fetch_webpage] Blocked: {blocked}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        async with httpx.AsyncClient(
            timeout=15.0, headers=headers, follow_redirects=True, trust_env=False
        ) as client:
            try:
                resp = await client.get(url)
            except httpx.ConnectError as e:
                if "SSL" in str(e):
                    logger.warning(
                        "SSL error, retrying without verification for %s", url
                    )
                    async with httpx.AsyncClient(
                        timeout=15.0,
                        headers=headers,
                        follow_redirects=True,
                        verify=False,
                        trust_env=False,
                    ) as client_unsafe:
                        resp = await client_unsafe.get(url)
                else:
                    raise e
            resp.raise_for_status()

        clean = _html_to_plain_text(resp.text)
        if len(clean.strip()) < _FETCH_MIN_MEANINGFUL_TEXT:
            fb = _html_static_fallback_text(resp.text)
            if fb.strip():
                note = (
                    "[Note: Page body is mostly empty in static HTML — typical of JavaScript apps. "
                    "Below is metadata only; use fetch_webpage_dynamic for full rendered text.]\n\n"
                )
                clean = (
                    (clean.strip() + "\n\n" + note + fb).strip()
                    if clean.strip()
                    else (note + fb).strip()
                )

        pack = await rank_chunks_to_source_pack((focus_query or "").strip(), url, clean)
        if pack:
            return f"📄 {pack}"

        out = clean
        if not out.strip():
            return (
                f"📄 Content from {url}:\n\n"
                "[fetch_webpage] No extractable text in static HTML (likely a JavaScript SPA or "
                "blocking page). Retry with **fetch_webpage_dynamic** using the same URL, or pick "
                "another URL from **web_search** results."
            )
        if len(out) > 4000:
            out = out[:4000] + "\n\n... [content truncated for brevity]"

        return f"📄 Content from {url}:\n\n{out}"

    except httpx.HTTPStatusError as e:
        return f"[fetch_webpage] HTTP error {e.response.status_code} for {url}"
    except httpx.TimeoutException:
        return f"[fetch_webpage] Timed out fetching {url}"
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return f"[fetch_webpage] Error: {str(e)}"


@tool
async def fetch_webpage_dynamic(url: str, focus_query: str = "") -> str:
    """
    Fetches a dynamic (JavaScript-rendered) webpage and returns its text content.

    Use when fetch_webpage returns little text (SPA). Same ``focus_query`` behavior as fetch_webpage.
    """
    from src.tools.url_policy import url_fetch_blocked_reason
    from src.tools.web_retrieval import rank_chunks_to_source_pack

    url = unwrap_redirect_search_url(url.strip())
    blocked = url_fetch_blocked_reason(url)
    if blocked:
        return f"[fetch_webpage_dynamic] Blocked: {blocked}"

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.goto(url, wait_until="networkidle", timeout=30000)
            content = await page.content()
            await browser.close()

        clean = _html_to_plain_text(content)
        if len(clean.strip()) < _FETCH_MIN_MEANINGFUL_TEXT:
            fb = _html_static_fallback_text(content)
            if fb.strip():
                note = "[Note: Little visible text after render — metadata fallback follows.]\n\n"
                clean = (
                    (clean.strip() + "\n\n" + note + fb).strip()
                    if clean.strip()
                    else (note + fb).strip()
                )

        pack = await rank_chunks_to_source_pack((focus_query or "").strip(), url, clean)
        if pack:
            return f"📄 [Dynamic] {pack}"

        out = clean
        if not out.strip():
            return (
                f"📄 [Dynamic] Content from {url}:\n\n"
                "[fetch_webpage_dynamic] No visible text after load (empty app shell or blocked)."
            )
        if len(out) > 4000:
            out = out[:4000] + "\n\n... [content truncated for brevity]"

        return f"📄 [Dynamic] Content from {url}:\n\n{out}"

    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return f"[fetch_webpage_dynamic] Error: {str(e)}"


async def _crawl_urls(urls: list[str]) -> str:
    """Helper to crawl multiple URLs concurrently and extract markdown."""
    try:
        from crawl4ai import AsyncWebCrawler
    except ImportError:
        return "[deep_research] Error: crawl4ai is not installed."

    try:
        async with AsyncWebCrawler() as crawler:
            tasks = [crawler.arun(url=u) for u in urls]
            results = await asyncio.gather(*tasks)

            context = ""
            for res in results:
                if getattr(res, "markdown", None):
                    context += f"\n\n=== Source: {res.url} ===\n{res.markdown}\n"
            return context.strip()
    except Exception as e:
        logger.error(f"_crawl_urls error: {e}")
        return f"[deep_research crawl error]: {e}"


@tool
async def deep_research(
    query: str,
    max_urls: int = 3,
) -> str:
    """
    Perform a deep web research pass. This searches the web for the query,
    then automatically crawls the top resulting pages to extract full markdown context
    instead of just search snippets. Use this when you need deep, detailed information
    from inside web pages.

    Args:
        query: The search query.
        max_urls: Number of top results to crawl (default 3).
    """
    # 1. Run the existing tiered web search pipeline
    try:
        # We invoke the underlying python function of the tool
        search_out = await web_search.ainvoke({"query": query})
    except Exception as e:
        return f"[deep_research search error]: {e}"

    if not search_out or "[web_search] Unable to retrieve" in search_out:
        return f"Search failed or yielded no results.\n\n{search_out}"

    # 2. Extract URLs from the formatted markdown output
    # web_search format: "   URL: https://..."
    urls = re.findall(r"URL:\s+(https?://[^\s]+)", search_out)

    # Deduplicate and limit
    seen = set()
    unique_urls = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)
            if len(unique_urls) >= max_urls:
                break

    if not unique_urls:
        return f"Could not extract any URLs from search results.\n\nSearch Snippets:\n{search_out}"

    # 3. Crawl the top URLs
    crawl_markdown = await _crawl_urls(unique_urls)

    if not crawl_markdown or "Error:" in crawl_markdown:
        return f"Search succeeded but deep crawl failed. Fallback to snippets:\n\n{search_out}\n\nCrawl error: {crawl_markdown}"

    # 4. Context Reranking (Web RAG)
    from src.config.config_loader import config
    from src.tools.web_retrieval import rank_chunks_to_source_pack

    web_rag_enabled = (
        str(config.get("web_search.web_rag.enabled", "true")).lower() == "true"
    )
    min_chars = int(config.get("web_search.web_rag.min_chars_for_rank", 1800))

    final_output = crawl_markdown
    if web_rag_enabled and len(crawl_markdown) > min_chars:
        # We pass the full crawled markdown to be chunked and ranked against the query
        pack = await rank_chunks_to_source_pack(
            query, "Multiple Sources (deep_research)", crawl_markdown
        )
        if pack:
            final_output = pack

    # 5. Return combined deep context with Prompt Injection security tags
    return f"""🔍 Deep Research Results for: "{query}"

<web_context>
{final_output}
</web_context>"""
