let socket = null;
let authToken = null; // Memory-only auth token (not persisted to storage)
const activeSearches = new Map();
const RESTRICTED_PREFIXES = ["chrome://", "chrome-extension://", "brave://", "edge://", "about:"];

// ── Backend URL Configuration ──────────────────────────────────────────
const DEFAULT_BACKEND_HTTP = "http://127.0.0.1:8000";
const DEFAULT_BACKEND_WS = "ws://127.0.0.1:8000";
let backendHttpUrl = DEFAULT_BACKEND_HTTP;
let backendWsUrl = DEFAULT_BACKEND_WS;

// Load configured URL from storage on startup
chrome.storage.local.get(["owlynnBackendUrl"], (result) => {
  if (result.owlynnBackendUrl) {
    try {
      const url = new URL(result.owlynnBackendUrl);
      backendHttpUrl = url.origin;
      backendWsUrl = `ws://${url.host}`;
    } catch {
      // Invalid URL, keep defaults
    }
  }
});

const SENSITIVE_DOMAINS = [
  "bank", "paypal", "stripe", "chase", "wellsfargo", "citi", "capitalone",
  "login", "auth", "oauth", "sso", "password", "credential",
  "localhost", "127.0.0.1"
];

// ── Rate Limiting ──────────────────────────────────────────────────────
const MAX_QUEUE_SIZE = 10;
const MIN_COMMAND_INTERVAL_MS = 100;
let commandQueue = [];
let lastCommandTime = 0;

// ── Reconnect Backoff ─────────────────────────────────────────────────
const RECONNECT_BASE_MS = 3000;
const RECONNECT_MAX_MS = 30000;
const RECONNECT_MAX_RETRIES = 20;
let reconnectAttempts = 0;
let reconnectTimer = null;

// ── Service Worker Keepalive ───────────────────────────────────────────
// MV3 service workers can be terminated. Use chrome.alarms to keep alive.
chrome.alarms.create('owlynn-keepalive', { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'owlynn-keepalive') {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "ping" }));
    }
  }
});

let isLiveTracking = false;
chrome.storage.local.get(["liveTracking"], (res) => {
  isLiveTracking = !!res.liveTracking;
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

function isSecureUrl(url) {
  if (isRestrictedUrl(url)) return false;
  try {
    const hostname = new URL(url).hostname.toLowerCase();
    // Exact match or subdomain match (not substring)
    for (const d of SENSITIVE_DOMAINS) {
      if (hostname === d || hostname.endsWith('.' + d)) return false;
    }
    return true;
  } catch (e) {
    return false;
  }
}

async function connect() {
  // Exponential backoff — don't retry infinitely
  if (reconnectAttempts >= RECONNECT_MAX_RETRIES) {
    console.warn(`[Owlynn Bridge] Max reconnect retries (${RECONNECT_MAX_RETRIES}) reached. Stopping.`);
    return;
  }

  console.log("[Owlynn Bridge] Connecting to backend WebSocket...");
  
  // Fetch auth token first
  if (!authToken) {
    await fetchAuthToken();
  }

  socket = new WebSocket(`${backendWsUrl}/api/browser_extension/ws`);

  socket.onopen = () => {
    console.log("[Owlynn Bridge] WebSocket connected. Sending auth...");
    reconnectAttempts = 0; // Reset backoff on successful connection
    
    // Send auth token as first message
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
      // Reject oversized messages (1MB)
      if (event.data && event.data.length > 1048576) {
        console.warn("[Owlynn Bridge] Rejected oversized message");
        return;
      }
      const message = JSON.parse(event.data);
      // Log message type/action only — never full content (may contain sensitive data)
      const msgType = message.action || message.type || 'unknown';
      console.debug(`[Owlynn Bridge] Message received: ${msgType}`);
      // Validate message type — allowlist of known types
      const knownActions = new Set(["search", "get_active_tab", "capture_screenshot", "browser_action", "fetch_urls", "get_cookies", "ui_status"]);
      const knownTypes = new Set(["page_context_response", "RELOAD"]);
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
        await handleBrowserActionRequest(message.id, message.payload);
      } else if (message.action === "fetch_urls") {
        await handleFetchUrlsRequest(message.id, message.urls);
      } else if (message.action === "get_cookies") {
        await handleGetCookiesRequest(message.id, message.url);
      } else if (message.action === "ui_status") {
        const tab = await getActiveTab();
        if (tab && message.payload) {
          chrome.tabs.sendMessage(tab.id, {
            type: 'OWLYNN_STATUS_UPDATE',
            data: { action: message.payload.action, value: message.payload.value, duration: 15000 }
          }).catch(() => {});
        }
      } else if (message.type === "page_context_response") {
        const tab = await getActiveTab();
        if (tab && message.thread_id) {
          chrome.tabs.sendMessage(tab.id, {
            type: 'OWLYNN_OPEN_SIDEBAR',
            thread_id: message.thread_id
          }).catch(() => {});
        }
      } else if (message.type === "RELOAD") {
        console.log("[Owlynn Bridge] Received RELOAD command. Reloading extension...");
        chrome.runtime.reload();
      }
    } catch (err) {
      console.error("[Owlynn Bridge] Error handling WebSocket message:", err);
    }
  };

  socket.onclose = (e) => {
    socket = null;
    authToken = null; // Re-fetch on next reconnect
    chrome.runtime.sendMessage({ type: "CONNECTION_STATUS", connected: false }).catch(() => {});
    
    // Exponential backoff
    reconnectAttempts++;
    const delay = Math.min(RECONNECT_BASE_MS * Math.pow(2, reconnectAttempts - 1), RECONNECT_MAX_MS);
    console.log(`[Owlynn Bridge] Disconnected. Reconnecting in ${Math.round(delay / 1000)}s (attempt ${reconnectAttempts}/${RECONNECT_MAX_RETRIES})...`);
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
    
    // Inject hints, capture, remove hints — all in one script injection
    const [{ result: dataUrl }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        // Inject hints
        const domMap = window.__owlynn_dom_map;
        const hints = [];
        if (domMap) {
          domMap.forEach((el, id) => {
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0 || rect.top < 0 || rect.left < 0 || rect.bottom > window.innerHeight || rect.right > window.innerWidth) return;
            const hint = document.createElement('div');
            hint.textContent = `[${id}]`;
            hint.setAttribute('data-owlynn-hint', '1');
            hint.style.cssText = `position: absolute; top: ${rect.top + window.scrollY}px; left: ${rect.left + window.scrollX}px; background: yellow; color: black; font-size: 12px; font-weight: bold; border: 1px solid black; z-index: 2147483647; padding: 2px; pointer-events: none;`;
            document.body.appendChild(hint);
            hints.push(hint);
          });
        }
        // Store for removal
        window.__owlynn_hints = hints;
        return null; // We don't need the result, just the side effect
      }
    });

    // Wait for hints to render
    await new Promise(resolve => setTimeout(resolve, 100));

    const screenshot = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "jpeg", quality: 50 });
    
    // Remove hints in a separate call (can't return screenshot from first call due to DOM mutation)
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        if (window.__owlynn_hints) {
          window.__owlynn_hints.forEach(h => h.remove());
          window.__owlynn_hints = [];
        }
      }
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
  // Rate limiting
  if (commandQueue.length >= MAX_QUEUE_SIZE) {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ 
        id: requestId, 
        error: `Queue full (${commandQueue.length}/${MAX_QUEUE_SIZE}). Try again later.` 
      }));
    }
    return;
  }
  
  // Throttle commands to same tab
  const now = Date.now();
  const timeSinceLastCommand = now - lastCommandTime;
  if (timeSinceLastCommand < MIN_COMMAND_INTERVAL_MS) {
    await new Promise(r => setTimeout(r, MIN_COMMAND_INTERVAL_MS - timeSinceLastCommand));
  }
  
  commandQueue.push(requestId);
  lastCommandTime = Date.now();
  
  try {
    const tab = await getActiveTab();
    if (!tab) throw new Error("No active tab.");
    
    // Tab ID pinning: verify the tab is still active
    if (payload.tabId && payload.tabId !== tab.id) {
      throw new Error(`Tab mismatch: expected ${payload.tabId}, got ${tab.id}`);
    }
    
    // Broadcast status to UI (sanitized — no raw selectors or text)
    chrome.tabs.sendMessage(tab.id, {
      type: 'OWLYNN_STATUS_UPDATE',
      data: {
        action: payload.action,
        target: payload.element_id !== undefined ? `Element #${payload.element_id}` : '',
        value: payload.text ? '...' : ''
      }
    }).catch(() => {});

    if (payload.action === "read_dom_tree" || payload.action === "read_full_dom_tree") {
      const includeText = payload.action === "read_full_dom_tree";
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: (includeText) => { window.__owlynn_include_text = includeText; },
        args: [includeText]
      });

      const [{ result }] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ["buildDomTree.js"]
      });
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ id: requestId, result: { success: true, dom_tree: result } }));
      }
      return;
    }
    
    if (payload.action === "show_hints") {
      const [{ result }] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ["content_hints.js"]
      });
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ id: requestId, result: result || { success: false, error: "No result" } }));
      }
      return;
    }
    
    if (payload.action === "go_back") {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => { window.history.back(); }
      });
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ id: requestId, result: { success: true } }));
      }
      return;
    }

    if (payload.action === "go_forward") {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => { window.history.forward(); }
      });
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ id: requestId, result: { success: true } }));
      }
      return;
    }
    
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: (args) => { window.__owlynn_interact_args = args; },
      args: [payload]
    });
    
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content_interact.js"]
    });
    
    // Auto-return the updated DOM tree for mutating actions to save the agent a round-trip
    if (result && result.success && ["click", "type", "scroll", "hover"].includes(payload.action)) {
      try {
        await new Promise(r => setTimeout(r, 600)); // allow SPA to render
        const [{ result: domResult }] = await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ["buildDomTree.js"]
        });
        result.dom_tree = domResult;
      } catch (err) {
        // Ignored: Action likely caused a hard page navigation
      }
    }
    
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ id: requestId, result: result || { success: false, error: "No result" } }));
    }
  } catch (err) {
    console.error("[Owlynn Bridge] browser_action failed:", err);
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ id: requestId, error: String(err) }));
    }
  } finally {
    commandQueue = commandQueue.filter(id => id !== requestId);
    const tab = await getActiveTab();
    if (tab) {
      chrome.tabs.sendMessage(tab.id, { type: 'OWLYNN_STATUS_UPDATE', data: { action: 'Thinking...', duration: 15000 } }).catch(() => {});
    }
  }
}

async function handleFetchUrlsRequest(requestId, urls) {
  try {
    const results = [];
    const urlList = Array.isArray(urls) ? urls : [urls];
    
    // Parallel fetch with concurrency limit
    const CONCURRENCY = 5;
    for (let i = 0; i < urlList.length; i += CONCURRENCY) {
      const batch = urlList.slice(i, i + CONCURRENCY);
      const batchResults = await Promise.all(batch.map(async (u) => {
        if (isRestrictedUrl(u)) {
          return { url: u, text: "Restricted URL", error: true };
        }
        try {
          const resp = await fetch(u, { signal: AbortSignal.timeout(10000) });
          if (!resp.ok) return { url: u, text: "", error: `HTTP ${resp.status}` };
          const html = await resp.text();
          // Extract visible text from HTML
          const doc = new DOMParser().parseFromString(html, 'text/html');
          // Remove script/style/nav/footer
          doc.querySelectorAll('script,style,nav,footer,header,noscript,svg').forEach(el => el.remove());
          const text = (doc.body?.innerText || doc.body?.textContent || '').trim().substring(0, 12000);
          return { url: u, text };
        } catch (e) {
          return { url: u, text: "", error: String(e.message || e) };
        }
      }));
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
// Cookie consent cache — persisted to chrome.storage.session (survives SW restart, cleared on browser close)
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
    
    // Check if user already approved this domain this session
    if (!cookieConsentCache.has(domain)) {
      // Show toast notification asking for consent
      const tab = await getActiveTab();
      if (tab) {
        const approved = await new Promise((resolve) => {
          chrome.tabs.sendMessage(tab.id, {
            type: 'OWLYNN_COOKIE_CONSENT',
            domain: domain,
            callbackId: requestId
          }, (response) => {
            resolve(response && response.approved);
          });
          
          // Timeout after 10 seconds
          setTimeout(() => resolve(false), 10000);
        });
        
        if (!approved) {
          if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ id: requestId, error: "User denied cookie access for " + domain }));
          }
          return;
        }
        
        // Cache approval for this session
        cookieConsentCache.set(domain, true);
        chrome.storage.session.set({ cookieConsentCache: Object.fromEntries(cookieConsentCache) });
      }
    }
    
    const cookies = await chrome.cookies.getAll({ domain });
    const cookieString = cookies.map(c => `${c.name}=${c.value}`).join('; ');
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

async function pushActiveTabToOwlynn(isLive = false, intent = "default") {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    throw new Error("Not connected to Owlynn backend.");
  }
  const tab = await getActiveTab();
  const context = await extractTabContext(tab);
  socket.send(
    JSON.stringify({
      type: "page_context_push",
      is_live_tracking: isLive,
      url: context.url,
      title: context.title,
      text: context.text,
      selection: context.selection,
      intent: intent,
    })
  );
  return context;
}

// Live tracking listener
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (isLiveTracking && changeInfo.status === 'complete' && tab.active) {
    if (isSecureUrl(tab.url)) {
      try {
        await pushActiveTabToOwlynn(true);
      } catch(err) {
        // Silently fail for live tracking
      }
    }
  }
});

async function handleSearchRequest(requestId, url) {
  try {
    const urlObj = new URL(url);
    console.debug(`[Owlynn Bridge] Search ID ${requestId} -> ${urlObj.hostname}`);
    const tab = await chrome.tabs.create({ url, active: false });

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
    console.debug(`[Owlynn Bridge] Sent search results for ID ${requestId}. Count: ${results.length}`);
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
      sendSearchResponse(search.requestId, message.hits || []);
      cleanupSearch(search.requestId, tabId);
    }
    return false;
  }

  if (message.type === "PUSH_ACTIVE_TAB") {
    pushActiveTabToOwlynn(false)
      .then((context) => sendResponseCallback({ ok: true, context }))
      .catch((err) => sendResponseCallback({ ok: false, error: String(err) }));
    return true;
  }

  if (message.type === "LIVE_TRACKING_TOGGLED") {
    isLiveTracking = !!message.isLive;
    return false;
  }

  if (message.type === "GET_CONNECTION_STATUS") {
    sendResponseCallback({
      connected: !!(socket && socket.readyState === WebSocket.OPEN),
    });
    return false;
  }

  if (message.type === "OWLYNN_ABORT_AUTOMATION") {
    if (socket && socket.readyState === WebSocket.OPEN) {
      console.log("[Owlynn Bridge] User aborted automation. Closing WebSocket to interrupt backend.");
      socket.close();
    }
    return false;
  }

  if (message.type === "BACKEND_URL_UPDATED") {
    console.log("[Owlynn Bridge] Backend URL updated. Reconnecting...");
    // Update URLs from the new value
    try {
      const url = new URL(message.url);
      backendHttpUrl = url.origin;
      backendWsUrl = `ws://${url.host}`;
    } catch {
      // Invalid URL, keep current
    }
    if (socket) socket.close();
    reconnectAttempts = 0; // Reset backoff for new URL
    // connect() will be triggered by onclose handler
    return false;
  }

  return false;
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

connect().catch(err => console.error("[Owlynn Bridge] Initial connection failed:", err));
