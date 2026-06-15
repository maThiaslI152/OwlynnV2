let socket = null;
const activeSearches = new Map();
const RESTRICTED_PREFIXES = ["chrome://", "chrome-extension://", "brave://", "edge://", "about:"];

function connect() {
  console.log("[Owlynn Bridge] Connecting to backend WebSocket...");
  socket = new WebSocket("ws://127.0.0.1:8000/api/browser_extension/ws");

  socket.onopen = () => {
    console.log("[Owlynn Bridge] WebSocket connected.");
    chrome.runtime.sendMessage({ type: "CONNECTION_STATUS", connected: true }).catch(() => {});
  };

  socket.onmessage = async (event) => {
    try {
      const message = JSON.parse(event.data);
      console.log("[Owlynn Bridge] Message received:", message);
      if (message.action === "search") {
        await handleSearchRequest(message.id, message.url);
      } else if (message.action === "get_active_tab") {
        await handleGetActiveTabRequest(message.id);
      }
    } catch (err) {
      console.error("[Owlynn Bridge] Error handling WebSocket message:", err);
    }
  };

  socket.onclose = (e) => {
    console.log("[Owlynn Bridge] WebSocket disconnected. Retrying in 3s...", e.reason);
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
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content_extract.js"],
    });
    if (result && typeof result === "object") {
      return {
        url: result.url || base.url,
        title: result.title || base.title,
        text: result.text || "",
        selection: result.selection || "",
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

async function pushActiveTabToOwlynn() {
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
    })
  );
  return context;
}

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
    pushActiveTabToOwlynn()
      .then((context) => sendResponseCallback({ ok: true, context }))
      .catch((err) => sendResponseCallback({ ok: false, error: String(err) }));
    return true;
  }

  if (message.type === "GET_CONNECTION_STATUS") {
    sendResponseCallback({
      connected: !!(socket && socket.readyState === WebSocket.OPEN),
    });
    return false;
  }

  return false;
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "owlynn-send-page",
    title: "Send page to Owlynn",
    contexts: ["page"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "owlynn-send-page") return;
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
      })
    );
  } catch (err) {
    console.error("[Owlynn Bridge] Context menu push failed:", err);
  }
});

connect();
