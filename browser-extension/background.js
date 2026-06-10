let socket = null;
const activeSearches = new Map();

function connect() {
  console.log("[Owlynn Extension] Connecting to backend WebSocket...");
  socket = new WebSocket("ws://127.0.0.1:8000/api/browser_extension/ws");

  socket.onopen = () => {
    console.log("[Owlynn Extension] WebSocket connected successfully.");
  };

  socket.onmessage = async (event) => {
    try {
      const message = JSON.parse(event.data);
      console.log("[Owlynn Extension] Message received:", message);
      if (message.action === "search") {
        await handleSearchRequest(message.id, message.url);
      }
    } catch (err) {
      console.error("[Owlynn Extension] Error handling WebSocket message:", err);
    }
  };

  socket.onclose = (e) => {
    console.log("[Owlynn Extension] WebSocket disconnected. Retrying in 3 seconds...", e.reason);
    socket = null;
    setTimeout(connect, 3000);
  };

  socket.onerror = (err) => {
    console.error("[Owlynn Extension] WebSocket error:", err);
    socket.close();
  };
}

async function handleSearchRequest(requestId, url) {
  try {
    console.log(`[Owlynn Extension] Starting search for ID ${requestId} -> ${url}`);
    
    // Create the search tab in the background (active: false)
    const tab = await chrome.tabs.create({ url, active: false });
    
    const timeoutId = setTimeout(async () => {
      console.warn(`[Owlynn Extension] Timeout triggered for search ID ${requestId}`);
      cleanupSearch(requestId, tab.id);
      sendResponse(requestId, []);
    }, 15000); // 15 seconds max execution window

    activeSearches.set(tab.id, {
      requestId,
      timeoutId,
      tabId: tab.id
    });
  } catch (err) {
    console.error("[Owlynn Extension] Error creating search tab:", err);
    sendResponse(requestId, []);
  }
}

function sendResponse(requestId, results) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ id: requestId, results }));
    console.log(`[Owlynn Extension] Sent results for ID ${requestId}. Count: ${results.length}`);
  } else {
    console.error("[Owlynn Extension] Failed to send response: WebSocket is closed");
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
    console.log(`[Owlynn Extension] Closed search tab ${tabId}`);
  } catch (err) {
    // Suppress errors if the tab was already closed by the user
  }
}

// Listen for messages from content scripts
chrome.runtime.onMessage.addListener((message, sender, sendResponseCallback) => {
  if (message.type === "SCRAPE_RESULTS" && sender.tab) {
    const tabId = sender.tab.id;
    const search = activeSearches.get(tabId);
    if (search) {
      console.log(`[Owlynn Extension] Received results from content script on tab ${tabId}`);
      sendResponse(search.requestId, message.hits || []);
      cleanupSearch(search.requestId, tabId);
    }
  }
  return false; // synchronous message handling
});

// Start connection on load
connect();
