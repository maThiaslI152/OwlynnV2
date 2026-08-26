let socket = null;
let authToken = null; // Memory-only auth token (not persisted to storage)
const activeSearches = new Map();
const RESTRICTED_PREFIXES = ["chrome://", "chrome-extension://", "brave://", "edge://", "about:"];

// ── Backend URL Configuration (loopback-only by default) ───────────────
const DEFAULT_BACKEND_HTTP = "http://127.0.0.1:8000";
const DEFAULT_BACKEND_WS = "ws://127.0.0.1:8000";
let backendHttpUrl = DEFAULT_BACKEND_HTTP;
let backendWsUrl = DEFAULT_BACKEND_WS;

const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);

function isLoopbackHostname(hostname) {
  const h = String(hostname || "").toLowerCase().replace(/^\[|\]$/g, "");
  return LOOPBACK_HOSTS.has(h) || LOOPBACK_HOSTS.has(hostname);
}

function httpOriginToWsOrigin(httpOrigin) {
  const url = new URL(httpOrigin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.origin;
}

function applyBackendUrl(rawUrl, { allowStoredRemote = false } = {}) {
  try {
    const url = new URL(rawUrl);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return false;
    }
    if (!isLoopbackHostname(url.hostname) && !allowStoredRemote) {
      console.warn("[Owlynn Bridge] Rejected non-loopback backend URL:", url.hostname);
      return false;
    }
    backendHttpUrl = url.origin;
    backendWsUrl = httpOriginToWsOrigin(url.origin);
    return true;
  } catch {
    return false;
  }
}

chrome.storage.local.get(["owlynnBackendUrl"], (result) => {
  if (result.owlynnBackendUrl) {
    // Stored remote URLs were user-confirmed in the popup; loopback always OK.
    if (!applyBackendUrl(result.owlynnBackendUrl, { allowStoredRemote: true })) {
      backendHttpUrl = DEFAULT_BACKEND_HTTP;
      backendWsUrl = DEFAULT_BACKEND_WS;
    }
  }
});

const SENSITIVE_DOMAINS = [
  "bank", "paypal", "stripe", "chase", "wellsfargo", "citi", "capitalone",
  "login", "auth", "oauth", "sso", "password", "credential",
  "localhost", "127.0.0.1"
];

const ALLOWED_SEARCH_HOSTS = new Set([
  "www.google.com",
  "google.com",
  "www.bing.com",
  "bing.com",
  "duckduckgo.com",
  "html.duckduckgo.com",
  "lite.duckduckgo.com",
]);

// Track hidden scrape/search tabs so orphans can be cleaned up
const orphanScrapeTabs = new Set();

// ── Rate Limiting / serialization ──────────────────────────────────────
const MAX_QUEUE_SIZE = 10;
const MIN_COMMAND_INTERVAL_MS = 100;
let commandQueue = [];
let lastCommandTime = 0;
/** Serialize overlapping DOM actions (one at a time). */
let browserActionChain = Promise.resolve();

// ── Reconnect Backoff ─────────────────────────────────────────────────
const RECONNECT_BASE_MS = 3000;
const RECONNECT_MAX_MS = 30000;
const RECONNECT_MAX_RETRIES = 20;
let reconnectAttempts = 0;
let reconnectTimer = null;

// ── Service Worker Keepalive ───────────────────────────────────────────
chrome.alarms.create("owlynn-keepalive", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== "owlynn-keepalive") return;

  // Clean any orphan scrape tabs left after SW restart / failed cleanup
  for (const tabId of [...orphanScrapeTabs]) {
    chrome.tabs.remove(tabId).catch(() => {});
    orphanScrapeTabs.delete(tabId);
  }

  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "ping" }));
  } else if (!socket || socket.readyState === WebSocket.CLOSED) {
    // Recover from hard-stop after max retries via periodic alarm reset
    if (reconnectAttempts >= RECONNECT_MAX_RETRIES) {
      console.log("[Owlynn Bridge] Keepalive resetting reconnect counter after max retries.");
      reconnectAttempts = 0;
    }
    console.log("[Owlynn Bridge] Keepalive detected closed connection. Reconnecting...");
    connect().catch(() => {});
  }
});

// ── Auth token management ──────────────────────────────────────────────
async function fetchAuthToken() {
  try {
    const resp = await fetch(`${backendHttpUrl}/api/browser_extension/token`);
    if (resp.ok) {
      const data = await resp.json();
      authToken = data.token;
      return authToken;
    }
  } catch (err) {
    console.error("[Owlynn Bridge] Failed to fetch auth token:", err.message || err);
  }
  // Fallback: try from storage (cached from previous successful fetch)
  return new Promise((resolve) => {
    chrome.storage.local.get(["owlynnAuthToken"], (result) => {
      authToken = result.owlynnAuthToken || null;
      resolve(authToken);
    });
  });
}

/** Return false when URL looks like banking / SSO / loopback (agent must not read/act). */
function isAgentAllowedUrl(url) {
  if (isRestrictedUrl(url)) return false;
  try {
    const hostname = new URL(url).hostname.toLowerCase();
    for (const d of SENSITIVE_DOMAINS) {
      if (new RegExp("\\b" + d + "\\b").test(hostname)) {
        return false;
      }
    }
    return true;
  } catch (e) {
    return false;
  }
}

/**
 * Mirror of Python url_fetch_blocked_reason (literal checks only — no DNS).
 * Returns a reason string if blocked, else null.
 */
function urlFetchBlockedReason(url) {
  if (!url || typeof url !== "string") return "Empty or invalid URL";
  const raw = url.trim();
  if (raw.length > 8192) return "URL too long";
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    return "Invalid URL";
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return "Only http and https URLs are allowed";
  }
  const host = (parsed.hostname || "").toLowerCase().replace(/^\[|\]$/g, "");
  if (!host) return "Missing hostname";
  if (
    host === "localhost" ||
    host === "0.0.0.0" ||
    host === "::" ||
    host.endsWith(".localhost") ||
    host === "metadata.google.internal" ||
    host === "metadata.goog"
  ) {
    return "Hostname is not allowed";
  }
  // IPv4 literal
  const ipv4 = host.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (ipv4) {
    const parts = ipv4.slice(1).map(Number);
    if (parts.some((n) => n > 255)) return "Address is not a public endpoint";
    const [a, b] = parts;
    if (a === 127 || a === 10 || a === 0) return "Address is not a public endpoint";
    if (a === 172 && b >= 16 && b <= 31) return "Address is not a public endpoint";
    if (a === 192 && b === 168) return "Address is not a public endpoint";
    if (a === 169 && b === 254) return "Address is not a public endpoint";
    return null;
  }
  // IPv6 loopback / ULA / link-local (simplified)
  if (host === "::1" || host.startsWith("fc") || host.startsWith("fd") || host.startsWith("fe80")) {
    return "Address is not a public endpoint";
  }
  return null;
}

async function connect() {
  if (reconnectAttempts >= RECONNECT_MAX_RETRIES) {
    console.warn(
      `[Owlynn Bridge] Max reconnect retries (${RECONNECT_MAX_RETRIES}) reached. Stopping until keepalive reset.`
    );
    return;
  }

  console.log("[Owlynn Bridge] Connecting to backend WebSocket...");

  if (!authToken) {
    await fetchAuthToken();
  }

  socket = new WebSocket(`${backendWsUrl}/api/browser_extension/ws`);

  socket.onopen = () => {
    console.log("[Owlynn Bridge] WebSocket connected. Sending auth...");
    reconnectAttempts = 0;

    if (authToken) {
      socket.send(JSON.stringify({ type: "auth", token: authToken }));
    } else {
      console.error("[Owlynn Bridge] No auth token available!");
      socket.close();
      return;
    }

    chrome.runtime.sendMessage({ type: "CONNECTION_STATUS", connected: true }).catch(() => {});
  };

  socket.onmessage = async (event) => {
    try {
      if (event.data && event.data.length > 1048576) {
        console.warn("[Owlynn Bridge] Rejected oversized message");
        return;
      }
      const message = JSON.parse(event.data);
      const msgType = message.action || message.type || "unknown";
      console.debug(`[Owlynn Bridge] Message received: ${msgType}`);
      const knownActions = new Set([
        "search",
        "get_active_tab",
        "capture_screenshot",
        "browser_action",
        "fetch_urls",
        "get_cookies",
        "ui_status",
      ]);
      const knownTypes = new Set(["RELOAD"]);
      if (!knownActions.has(message.action) && !knownTypes.has(message.type)) {
        console.debug(`[Owlynn Bridge] Ignoring unknown message type: ${msgType}`);
        return;
      }

      if (message.action === "search") {
        await handleSearchRequest(message.id, message.url);
      } else if (message.action === "get_active_tab") {
        await handleGetActiveTabRequest(message.id);
      } else if (message.action === "capture_screenshot") {
        await handleCaptureScreenshotRequest(message.id);
      } else if (message.action === "browser_action") {
        await enqueueBrowserAction(() =>
          handleBrowserActionRequest(message.id, message.payload)
        );
      } else if (message.action === "fetch_urls") {
        await handleFetchUrlsRequest(message.id, message.urls);
      } else if (message.action === "get_cookies") {
        await handleGetCookiesRequest(message.id, message.url);
      } else if (message.action === "ui_status") {
        const tab = await getActiveTab();
        if (tab && message.payload) {
          chrome.tabs
            .sendMessage(tab.id, {
              type: "OWLYNN_STATUS_UPDATE",
              data: {
                action: message.payload.action,
                value: message.payload.value,
                duration: 15000,
              },
            })
            .catch(() => {});
        }
      } else if (message.type === "RELOAD") {
        console.log("[Owlynn Bridge] Received RELOAD command. Reloading extension...");
        chrome.runtime.reload();
      }
    } catch (err) {
      console.error("[Owlynn Bridge] Error handling WebSocket message:", err);
    }
  };

  socket.onclose = () => {
    socket = null;
    authToken = null;
    chrome.runtime.sendMessage({ type: "CONNECTION_STATUS", connected: false }).catch(() => {});

    reconnectAttempts++;
    const delay = Math.min(
      RECONNECT_BASE_MS * Math.pow(2, reconnectAttempts - 1),
      RECONNECT_MAX_MS
    );
    console.log(
      `[Owlynn Bridge] Disconnected. Reconnecting in ${Math.round(delay / 1000)}s (attempt ${reconnectAttempts}/${RECONNECT_MAX_RETRIES})...`
    );
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connect, delay);
  };

  socket.onerror = () => {
    console.error("[Owlynn Bridge] WebSocket error occurred");
    socket.close();
  };
}

function isRestrictedUrl(url) {
  if (!url) return true;
  return RESTRICTED_PREFIXES.some((prefix) => url.startsWith(prefix));
}

function enqueueBrowserAction(fn) {
  const run = browserActionChain.then(fn, fn);
  browserActionChain = run.catch(() => {});
  return run;
}

async function extractTabContext(tab) {
  if (!tab || !tab.id) {
    return { url: "", title: "", text: "", selection: "", error: "No active tab." };
  }

  const base = {
    url: tab.url || "",
    title: tab.title || "",
    text: "",
    selection: "",
  };

  if (isRestrictedUrl(tab.url)) {
    return {
      ...base,
      error: "Restricted page — only URL and title are available.",
    };
  }

  if (!isAgentAllowedUrl(tab.url)) {
    return {
      ...base,
      text: "",
      selection: "",
      error: "Sensitive site — page content blocked for agent access.",
    };
  }

  try {
    const [{ result: moodleResult }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content_moodle.js"],
    });

    if (moodleResult && moodleResult.isMoodle) {
      return {
        url: moodleResult.url || base.url,
        title: moodleResult.title || base.title,
        text: moodleResult.text || "",
        selection: moodleResult.selection || "",
      };
    }

    const executionResults = await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      files: ["content_extract.js"],
    });

    if (executionResults && executionResults.length > 0) {
      let fullText = "";
      let fullSelection = "";
      executionResults.forEach((frame) => {
        if (frame.result && typeof frame.result === "object") {
          if (frame.result.text) {
            if (fullText) fullText += "\n\n--- iframe ---\n\n";
            fullText += frame.result.text;
          }
          if (frame.result.selection) {
            fullSelection += frame.result.selection + "\n";
          }
        }
      });

      const mainFrame = executionResults[0].result || {};
      return {
        url: mainFrame.url || base.url,
        title: mainFrame.title || base.title,
        text: fullText.trim(),
        selection: fullSelection.trim(),
      };
    }
  } catch (err) {
    console.warn("[Owlynn Bridge] Could not extract page body:", err);
    return {
      ...base,
      error: "Could not read page body on this tab.",
    };
  }

  return base;
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0] || null;
}

async function handleGetActiveTabRequest(requestId) {
  try {
    const tab = await getActiveTab();
    const context = await extractTabContext(tab);
    sendTabResponse(requestId, context);
  } catch (err) {
    console.error("[Owlynn Bridge] get_active_tab failed:", err);
    sendTabResponse(requestId, {
      url: "",
      title: "",
      text: "",
      selection: "",
      error: String(err),
    });
  }
}

async function handleCaptureScreenshotRequest(requestId) {
  try {
    const tab = await getActiveTab();
    if (!tab) throw new Error("No active tab.");
    if (!isAgentAllowedUrl(tab.url)) {
      throw new Error("Sensitive site — screenshot blocked for agent access.");
    }

    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const domMap = window.__owlynn_dom_map;
        const hints = [];
        if (domMap) {
          domMap.forEach((el, id) => {
            const rect = el.getBoundingClientRect();
            if (
              rect.width === 0 ||
              rect.height === 0 ||
              rect.top < 0 ||
              rect.left < 0 ||
              rect.bottom > window.innerHeight ||
              rect.right > window.innerWidth
            )
              return;
            const hint = document.createElement("div");
            hint.textContent = `[${id}]`;
            hint.setAttribute("data-owlynn-hint", "1");
            hint.style.cssText = `position: absolute; top: ${rect.top + window.scrollY}px; left: ${rect.left + window.scrollX}px; background: yellow; color: black; font-size: 12px; font-weight: bold; border: 1px solid black; z-index: 2147483647; padding: 2px; pointer-events: none;`;
            document.body.appendChild(hint);
            hints.push(hint);
          });
        }
        window.__owlynn_hints = hints;
        return null;
      },
    });

    await new Promise((resolve) => setTimeout(resolve, 100));

    const screenshot = await chrome.tabs.captureVisibleTab(tab.windowId, {
      format: "jpeg",
      quality: 50,
    });

    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        if (window.__owlynn_hints) {
          window.__owlynn_hints.forEach((h) => h.remove());
          window.__owlynn_hints = [];
        }
      },
    });

    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ id: requestId, image_data: screenshot }));
      console.debug(`[Owlynn Bridge] Sent screenshot for ID ${requestId}`);
    }
  } catch (err) {
    console.error("[Owlynn Bridge] capture_screenshot failed:", err);
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ id: requestId, error: String(err) }));
    }
  }
}

async function handleBrowserActionRequest(requestId, payload) {
  if (commandQueue.length >= MAX_QUEUE_SIZE) {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(
        JSON.stringify({
          id: requestId,
          error: `Queue full (${commandQueue.length}/${MAX_QUEUE_SIZE}). Try again later.`,
        })
      );
    }
    return;
  }

  const now = Date.now();
  const timeSinceLastCommand = now - lastCommandTime;
  if (timeSinceLastCommand < MIN_COMMAND_INTERVAL_MS) {
    await new Promise((r) => setTimeout(r, MIN_COMMAND_INTERVAL_MS - timeSinceLastCommand));
  }

  commandQueue.push(requestId);
  lastCommandTime = Date.now();

  try {
    const tab = await getActiveTab();
    if (!tab) throw new Error("No active tab.");
    if (!isAgentAllowedUrl(tab.url)) {
      throw new Error("Sensitive site — browser actions blocked for agent access.");
    }

    if (payload.tabId && payload.tabId !== tab.id) {
      throw new Error(`Tab mismatch: expected ${payload.tabId}, got ${tab.id}`);
    }

    chrome.tabs
      .sendMessage(tab.id, {
        type: "OWLYNN_STATUS_UPDATE",
        data: {
          action: payload.action,
          target: payload.element_id !== undefined ? `Element #${payload.element_id}` : "",
          value: payload.text ? "..." : "",
        },
      })
      .catch(() => {});

    if (payload.action === "read_dom_tree" || payload.action === "read_full_dom_tree") {
      const includeText = payload.action === "read_full_dom_tree";
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: (includeText) => {
          window.__owlynn_include_text = includeText;
        },
        args: [includeText],
      });

      const [{ result }] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ["buildDomTree.js"],
      });
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(
          JSON.stringify({ id: requestId, result: { success: true, dom_tree: result } })
        );
      }
      return;
    }

    if (payload.action === "show_hints") {
      const [{ result }] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ["content_hints.js"],
      });
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(
          JSON.stringify({
            id: requestId,
            result: result || { success: false, error: "No result" },
          })
        );
      }
      return;
    }

    if (payload.action === "set_hint_config") {
      await chrome.storage.local.set({ owlynnHintConfig: payload.config || {} });
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ id: requestId, result: { success: true } }));
      }
      return;
    }

    if (payload.action === "go_back") {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => {
          window.history.back();
        },
      });
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ id: requestId, result: { success: true } }));
      }
      return;
    }

    if (payload.action === "go_forward") {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => {
          window.history.forward();
        },
      });
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ id: requestId, result: { success: true } }));
      }
      return;
    }

    if (payload.action === "wait_for_navigation") {
      const timeout = payload.timeout || 10000;

      const currentTab = await chrome.tabs.get(tab.id);
      if (currentTab.status === "loading") {
        try {
          await new Promise((resolve, reject) => {
            const listener = (tabId, changeInfo) => {
              if (tabId === tab.id && changeInfo.status === "complete") {
                chrome.tabs.onUpdated.removeListener(listener);
                resolve();
              }
            };
            chrome.tabs.onUpdated.addListener(listener);
            setTimeout(() => {
              chrome.tabs.onUpdated.removeListener(listener);
              reject(new Error("Timeout waiting for navigation"));
            }, timeout);
          });
          if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(
              JSON.stringify({
                id: requestId,
                result: { success: true, result: "Page loaded." },
              })
            );
          }
        } catch (err) {
          if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(
              JSON.stringify({
                id: requestId,
                result: { success: true, result: `Waited ${timeout}ms (timeout).` },
              })
            );
          }
        }
      } else {
        try {
          await new Promise((resolve, reject) => {
            let started = false;
            const listener = (tabId, changeInfo) => {
              if (tabId === tab.id) {
                if (changeInfo.status === "loading") {
                  started = true;
                } else if (changeInfo.status === "complete" && started) {
                  chrome.tabs.onUpdated.removeListener(listener);
                  resolve("Page loaded after transition.");
                }
              }
            };
            chrome.tabs.onUpdated.addListener(listener);

            setTimeout(() => {
              if (!started) {
                chrome.tabs.onUpdated.removeListener(listener);
                resolve("Page already loaded (no transition started).");
              }
            }, 600);

            setTimeout(() => {
              chrome.tabs.onUpdated.removeListener(listener);
              reject(new Error("Timeout waiting for navigation"));
            }, timeout);
          });
          if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(
              JSON.stringify({
                id: requestId,
                result: { success: true, result: "Page loaded." },
              })
            );
          }
        } catch (err) {
          if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(
              JSON.stringify({
                id: requestId,
                result: { success: true, result: `Waited ${timeout}ms (timeout).` },
              })
            );
          }
        }
      }
      return;
    }

    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: (args) => {
        window.__owlynn_interact_args = args;
      },
      args: [payload],
    });

    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content_interact.js"],
    });

    if (result && result.success && ["click", "type", "scroll", "hover"].includes(payload.action)) {
      try {
        await new Promise((r) => setTimeout(r, 600));
        const [{ result: domResult }] = await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ["buildDomTree.js"],
        });
        result.dom_tree = domResult;
      } catch (err) {
        // Action likely caused a hard page navigation
      }
    }

    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(
        JSON.stringify({
          id: requestId,
          result: result || { success: false, error: "No result" },
        })
      );
    }
  } catch (err) {
    console.error("[Owlynn Bridge] browser_action failed:", err);
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ id: requestId, error: String(err) }));
    }
  } finally {
    commandQueue = commandQueue.filter((id) => id !== requestId);
    const tab = await getActiveTab();
    if (tab) {
      chrome.tabs
        .sendMessage(tab.id, {
          type: "OWLYNN_STATUS_UPDATE",
          data: { action: "Thinking...", duration: 15000 },
        })
        .catch(() => {});
    }
  }
}

class Semaphore {
  constructor(max) {
    this.tasks = [];
    this.counter = max;
  }
  async acquire() {
    if (this.counter > 0) {
      this.counter--;
      return;
    }
    await new Promise((resolve) => this.tasks.push(resolve));
  }
  release() {
    if (this.tasks.length > 0) {
      const resolve = this.tasks.shift();
      resolve();
    } else {
      this.counter++;
    }
  }
}
const tabScrapeSemaphore = new Semaphore(3);

async function scrapeUrlViaTab(url) {
  await tabScrapeSemaphore.acquire();
  let tab = null;
  try {
    tab = await chrome.tabs.create({ url, active: false });
    if (tab?.id) orphanScrapeTabs.add(tab.id);

    await new Promise((resolve, reject) => {
      const listener = (tabId, changeInfo) => {
        if (tabId === tab.id && changeInfo.status === "complete") {
          chrome.tabs.onUpdated.removeListener(listener);
          resolve();
        }
      };
      chrome.tabs.onUpdated.addListener(listener);
      setTimeout(() => {
        chrome.tabs.onUpdated.removeListener(listener);
        reject(new Error("Timeout waiting for page load"));
      }, 15000);
    });

    await new Promise((r) => setTimeout(r, 1000));

    const executionResults = await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      files: ["content_extract.js"],
    });

    let fullText = "";
    if (executionResults && executionResults.length > 0) {
      executionResults.forEach((frame) => {
        if (frame.result && typeof frame.result === "object" && frame.result.text) {
          if (fullText) fullText += "\n\n--- iframe ---\n\n";
          fullText += frame.result.text;
        }
      });
    }
    return fullText.trim();
  } catch (err) {
    console.warn(`[Owlynn Bridge] Tab fallback scrape failed for ${url}:`, err);
    throw err;
  } finally {
    if (tab && tab.id) {
      orphanScrapeTabs.delete(tab.id);
      try {
        await chrome.tabs.remove(tab.id);
      } catch (e) {
        // Tab may already be closed
      }
    }
    tabScrapeSemaphore.release();
  }
}

async function handleFetchUrlsRequest(requestId, urls) {
  try {
    const results = [];
    const urlList = Array.isArray(urls) ? urls : [urls];

    const CONCURRENCY = 5;
    for (let i = 0; i < urlList.length; i += CONCURRENCY) {
      const batch = urlList.slice(i, i + CONCURRENCY);
      const batchResults = await Promise.all(
        batch.map(async (u) => {
          if (isRestrictedUrl(u)) {
            return { url: u, text: "Restricted URL", error: true };
          }
          const ssrfReason = urlFetchBlockedReason(u);
          if (ssrfReason) {
            return { url: u, text: "", error: `Blocked: ${ssrfReason}` };
          }
          let useFallback = false;
          let text = "";
          let errorMsg = null;
          try {
            const resp = await fetch(u, { signal: AbortSignal.timeout(6000) });
            if (!resp.ok) {
              useFallback = true;
              errorMsg = `HTTP ${resp.status}`;
            } else {
              const html = await resp.text();
              const doc = new DOMParser().parseFromString(html, "text/html");
              doc
                .querySelectorAll("script,style,nav,footer,header,noscript,svg")
                .forEach((el) => el.remove());
              text = (doc.body?.innerText || doc.body?.textContent || "")
                .trim()
                .substring(0, 12000);
              if (text.length < 300) {
                useFallback = true;
              }
            }
          } catch (e) {
            useFallback = true;
            errorMsg = String(e.message || e);
          }

          if (useFallback) {
            try {
              console.log(
                `[Owlynn Bridge] Falling back to background tab scrape for: ${u} (reason: ${errorMsg || "short text"})`
              );
              const renderedText = await scrapeUrlViaTab(u);
              return { url: u, text: renderedText.substring(0, 12000) };
            } catch (fallbackErr) {
              return {
                url: u,
                text: text || "",
                error: errorMsg || String(fallbackErr.message || fallbackErr),
              };
            }
          }
          return { url: u, text };
        })
      );
      results.push(...batchResults);
    }
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ id: requestId, results }));
    }
  } catch (err) {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ id: requestId, error: String(err.message || err) }));
    }
  }
}

// Cookie consent cache — persisted to chrome.storage.session
const cookieConsentCache = new Map();
chrome.storage.session.get(["cookieConsentCache"], (res) => {
  if (res.cookieConsentCache) {
    for (const [k, v] of Object.entries(res.cookieConsentCache)) {
      cookieConsentCache.set(k, v);
    }
  }
});

async function handleGetCookiesRequest(requestId, targetUrl) {
  try {
    const urlObj = new URL(targetUrl);
    const domain = urlObj.hostname;

    if (!isAgentAllowedUrl(targetUrl)) {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(
          JSON.stringify({
            id: requestId,
            error: "Sensitive site — cookie access blocked.",
          })
        );
      }
      return;
    }

    // Deny by default unless this domain was already approved this session
    if (!cookieConsentCache.has(domain)) {
      const tab = await getActiveTab();
      // Never fall through without an active tab + affirmative consent
      if (!tab) {
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(
            JSON.stringify({
              id: requestId,
              error: "No active tab for cookie consent — denied by default.",
            })
          );
        }
        return;
      }

      const approved = await new Promise((resolve) => {
        let settled = false;
        const finish = (value) => {
          if (settled) return;
          settled = true;
          resolve(value);
        };
        chrome.tabs.sendMessage(
          tab.id,
          {
            type: "OWLYNN_COOKIE_CONSENT",
            domain: domain,
            callbackId: requestId,
          },
          (response) => {
            if (chrome.runtime.lastError) {
              finish(false);
              return;
            }
            finish(!!(response && response.approved));
          }
        );
        setTimeout(() => finish(false), 10000);
      });

      if (!approved) {
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(
            JSON.stringify({
              id: requestId,
              error: "User denied cookie access for " + domain,
            })
          );
        }
        return;
      }

      cookieConsentCache.set(domain, true);
      chrome.storage.session.set({
        cookieConsentCache: Object.fromEntries(cookieConsentCache),
      });
    }

    // Prefer URL-scoped cookies over bare domain (narrower, matches request URL)
    const cookies = await chrome.cookies.getAll({ url: targetUrl });
    const cookieString = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ id: requestId, cookies: cookieString }));
    }
  } catch (err) {
    console.error("[Owlynn Bridge] get_cookies failed:", err);
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ id: requestId, error: String(err) }));
    }
  }
}

async function pushActiveTabToOwlynn(intent = "default") {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    throw new Error("Not connected to Owlynn backend.");
  }
  const tab = await getActiveTab();
  const context = await extractTabContext(tab);
  socket.send(
    JSON.stringify({
      type: "page_context_push",
      url: context.url,
      title: context.title,
      text: context.text,
      selection: context.selection,
      intent: intent,
    })
  );
  return context;
}

async function handleSearchRequest(requestId, url) {
  try {
    const urlObj = new URL(url);
    const host = urlObj.hostname.toLowerCase();
    if (!ALLOWED_SEARCH_HOSTS.has(host)) {
      console.warn(`[Owlynn Bridge] Rejected non-allowlisted search host: ${host}`);
      sendSearchResponse(requestId, []);
      return;
    }
    console.debug(`[Owlynn Bridge] Search ID ${requestId} -> ${host}`);
    const tab = await chrome.tabs.create({ url, active: false });
    if (tab?.id) orphanScrapeTabs.add(tab.id);

    const timeoutId = setTimeout(async () => {
      console.warn(`[Owlynn Bridge] Search timeout for ID ${requestId}`);
      cleanupSearch(requestId, tab.id);
      sendSearchResponse(requestId, []);
    }, 15000);

    activeSearches.set(tab.id, {
      requestId,
      timeoutId,
      tabId: tab.id,
    });
  } catch (err) {
    console.error("[Owlynn Bridge] Error creating search tab:", err);
    sendSearchResponse(requestId, []);
  }
}

function sendSearchResponse(requestId, results) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ id: requestId, results }));
    console.debug(
      `[Owlynn Bridge] Sent search results for ID ${requestId}. Count: ${results.length}`
    );
  }
}

function sendTabResponse(requestId, tab) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ id: requestId, tab }));
    console.debug(`[Owlynn Bridge] Sent active tab for ID ${requestId}`);
  }
}

async function cleanupSearch(requestId, tabId) {
  const search = activeSearches.get(tabId);
  if (search) {
    clearTimeout(search.timeoutId);
    activeSearches.delete(tabId);
  }
  orphanScrapeTabs.delete(tabId);
  try {
    await chrome.tabs.remove(tabId);
  } catch (err) {
    // Tab may already be closed
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponseCallback) => {
  if (message.type === "SCRAPE_RESULTS" && sender.tab) {
    const tabId = sender.tab.id;
    const search = activeSearches.get(tabId);
    if (search) {
      // CAPTCHA / hard failure → empty results so backend falls through tiers
      const hits = message.error ? [] : message.hits || [];
      sendSearchResponse(search.requestId, hits);
      cleanupSearch(search.requestId, tabId);
    }
    return false;
  }

  if (message.type === "PUSH_ACTIVE_TAB") {
    pushActiveTabToOwlynn("default")
      .then((context) => sendResponseCallback({ ok: true, context }))
      .catch((err) => sendResponseCallback({ ok: false, error: String(err) }));
    return true;
  }

  if (message.type === "GET_CONNECTION_STATUS") {
    const isConnected = !!(socket && socket.readyState === WebSocket.OPEN);
    if (!isConnected && (!socket || socket.readyState === WebSocket.CLOSED)) {
      if (reconnectAttempts >= RECONNECT_MAX_RETRIES) {
        reconnectAttempts = 0;
      }
      connect().catch(() => {});
    }
    sendResponseCallback({
      connected: isConnected,
    });
    return false;
  }

  if (message.type === "OWLYNN_ABORT_AUTOMATION") {
    if (socket && socket.readyState === WebSocket.OPEN) {
      console.log(
        "[Owlynn Bridge] User aborted automation. Closing WebSocket to interrupt backend."
      );
      socket.close();
    }
    return false;
  }

  if (message.type === "BACKEND_URL_UPDATED") {
    console.log("[Owlynn Bridge] Backend URL updated. Reconnecting...");
    // Popup already confirmed remotes; allowStoredRemote accepts that choice.
    if (!applyBackendUrl(message.url, { allowStoredRemote: true })) {
      console.warn("[Owlynn Bridge] Backend URL rejected; keeping previous.");
      return false;
    }
    if (socket) socket.close();
    reconnectAttempts = 0;
    return false;
  }

  return false;
});

chrome.runtime.onStartup.addListener(() => {
  console.log("[Owlynn Bridge] Browser started. Connecting to backend...");
  connect().catch(() => {});
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "owlynn-send-page-parent",
    title: "Send page to Owlynn",
    contexts: ["page"],
  });

  chrome.contextMenus.create({
    parentId: "owlynn-send-page-parent",
    id: "owlynn-send-page-default",
    title: "Help me with this page (Default)",
    contexts: ["page"],
  });

  chrome.contextMenus.create({
    parentId: "owlynn-send-page-parent",
    id: "owlynn-send-page-summarize",
    title: "Summarize this page",
    contexts: ["page"],
  });

  chrome.contextMenus.create({
    parentId: "owlynn-send-page-parent",
    id: "owlynn-send-page-automate",
    title: "Automate interaction",
    contexts: ["page"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (!info.menuItemId.toString().startsWith("owlynn-send-page-")) return;
  const intent = info.menuItemId.toString().replace("owlynn-send-page-", "");
  try {
    if (!tab) {
      throw new Error("No active tab.");
    }
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      throw new Error("Owlynn backend is not connected.");
    }
    const context = await extractTabContext(tab);
    socket.send(
      JSON.stringify({
        type: "page_context_push",
        url: context.url,
        title: context.title,
        text: context.text,
        selection: context.selection,
        intent: intent,
      })
    );
  } catch (err) {
    console.error("[Owlynn Bridge] Context menu push failed:", err);
  }
});

connect().catch((err) =>
  console.error("[Owlynn Bridge] Initial connection failed:", err)
);
