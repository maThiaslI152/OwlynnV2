let socket = null;
let keepAliveInterval = null;
const activeSearches = new Map();
const RESTRICTED_PREFIXES = ["chrome://", "chrome-extension://", "brave://", "edge://", "about:"];

const SENSITIVE_DOMAINS = [
  "bank", "paypal", "stripe", "chase", "wellsfargo", "citi", "capitalone",
  "login", "auth", "oauth", "sso", "password", "credential",
  "localhost", "127.0.0.1"
];

let isLiveTracking = false;
chrome.storage.local.get(["liveTracking"], (res) => {
  isLiveTracking = !!res.liveTracking;
});

function isSecureUrl(url) {
  if (isRestrictedUrl(url)) return false;
  try {
    const hostname = new URL(url).hostname.toLowerCase();
    for (const d of SENSITIVE_DOMAINS) {
      if (hostname.includes(d)) return false;
    }
    return true;
  } catch (e) {
    return false;
  }
}

function connect() {
  console.log("[Owlynn Bridge] Connecting to backend WebSocket...");
  socket = new WebSocket("ws://127.0.0.1:8000/api/browser_extension/ws");

  socket.onopen = () => {
    console.log("[Owlynn Bridge] WebSocket connected.");
    chrome.runtime.sendMessage({ type: "CONNECTION_STATUS", connected: true }).catch(() => {});
    
    // Send a ping every 20 seconds to keep the Service Worker and WebSocket alive
    if (keepAliveInterval) clearInterval(keepAliveInterval);
    keepAliveInterval = setInterval(() => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "ping" }));
      }
    }, 20000);
  };

  socket.onmessage = async (event) => {
    try {
      const message = JSON.parse(event.data);
      console.log("[Owlynn Bridge] Message received:", message);
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
    console.log("[Owlynn Bridge] WebSocket disconnected. Retrying in 3s...", e.reason);
    if (keepAliveInterval) clearInterval(keepAliveInterval);
    socket = null;
    chrome.runtime.sendMessage({ type: "CONNECTION_STATUS", connected: false }).catch(() => {});
    setTimeout(connect, 3000);
  };

  socket.onerror = (err) => {
    console.error("[Owlynn Bridge] WebSocket error:", err);
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
    
    // Inject visual hints based on the DOM map
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => { window.__owlynn_interact_args = { action: 'inject_hints' }; }
    });
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content_interact.js"]
    }).catch(err => console.warn("Failed to inject hints:", err));
    
    // Wait for DOM to render the hints
    await new Promise(resolve => setTimeout(resolve, 150));

    const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "jpeg", quality: 50 });
    
    // Remove hints
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => { window.__owlynn_interact_args = { action: 'remove_hints' }; }
    });
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content_interact.js"]
    }).catch(err => console.warn("Failed to remove hints:", err));

    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ id: requestId, image_data: dataUrl }));
      console.log(`[Owlynn Bridge] Sent screenshot for ID ${requestId}`);
    }
  } catch (err) {
    console.error("[Owlynn Bridge] capture_screenshot failed:", err);
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ id: requestId, error: String(err) }));
    }
  }
}

async function handleBrowserActionRequest(requestId, payload) {
  try {
    const tab = await getActiveTab();
    if (!tab) throw new Error("No active tab.");
    
    // Broadcast status to UI
    chrome.tabs.sendMessage(tab.id, {
      type: 'OWLYNN_STATUS_UPDATE',
      data: {
        action: payload.action,
        target: payload.selector || (payload.element_ids ? `Elements: ${payload.element_ids.join(',')}` : payload.element_id),
        value: payload.text
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
    
    for (const u of urlList) {
      if (isRestrictedUrl(u)) {
        results.push({ url: u, text: "Restricted URL", error: true });
        continue;
      }
      try {
        const text = await scrapeSingleUrlInBackground(u);
        results.push({ url: u, text });
      } catch (e) {
        results.push({ url: u, text: "", error: String(e) });
      }
    }
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ id: requestId, results }));
    }
  } catch (err) {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ id: requestId, error: String(err) }));
    }
  }
}
async function handleGetCookiesRequest(requestId, targetUrl) {
  try {
    const urlObj = new URL(targetUrl);
    const domain = urlObj.hostname;
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
    console.log(`[Owlynn Bridge] Search ID ${requestId} -> ${url}`);
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
    console.log(`[Owlynn Bridge] Sent search results for ID ${requestId}. Count: ${results.length}`);
  } else {
    console.error("[Owlynn Bridge] Failed to send search response: WebSocket closed");
  }
}

function sendTabResponse(requestId, tab) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ id: requestId, tab }));
    console.log(`[Owlynn Bridge] Sent active tab for ID ${requestId}`);
  } else {
    console.error("[Owlynn Bridge] Failed to send tab response: WebSocket closed");
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

connect();
