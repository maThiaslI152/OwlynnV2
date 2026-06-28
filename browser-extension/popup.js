const statusEl = document.getElementById("status");
const sendBtn = document.getElementById("sendBtn");
const liveBtn = document.getElementById("liveBtn");
const feedbackEl = document.getElementById("feedback");
const backendUrlInput = document.getElementById("backendUrl");
const saveUrlBtn = document.getElementById("saveUrlBtn");
const urlFeedbackEl = document.getElementById("urlFeedback");

function setConnected(connected) {
  if (connected) {
    statusEl.textContent = "Connected to Owlynn";
    statusEl.className = "status ok";
    sendBtn.disabled = false;
  } else {
    statusEl.textContent = "Not connected — start Owlynn backend";
    statusEl.className = "status off";
    sendBtn.disabled = true;
  }
}

function refreshStatus() {
  chrome.runtime.sendMessage({ type: "GET_CONNECTION_STATUS" }, (response) => {
    setConnected(!!response?.connected);
  });
}

sendBtn.addEventListener("click", () => {
  feedbackEl.textContent = "Sending…";
  sendBtn.disabled = true;
  chrome.runtime.sendMessage({ type: "PUSH_ACTIVE_TAB" }, (response) => {
    refreshStatus();
    if (response?.ok) {
      feedbackEl.textContent = "Page sent to Owlynn.";
    } else {
      feedbackEl.textContent = response?.error || "Failed to send page.";
    }
    setTimeout(() => {
      feedbackEl.textContent = "";
    }, 3000);
  });
});

let isLive = false;
chrome.storage.local.get(["liveTracking"], (res) => {
  isLive = !!res.liveTracking;
  updateLiveBtn();
});

function updateLiveBtn() {
  if (isLive) {
    liveBtn.textContent = "Live Tracking: ON (Watching)";
    liveBtn.style.background = "#059669";
  } else {
    liveBtn.textContent = "Live Tracking: OFF";
    liveBtn.style.background = "#6b7280";
  }
}

liveBtn.addEventListener("click", () => {
  isLive = !isLive;
  chrome.storage.local.set({ liveTracking: isLive });
  updateLiveBtn();
  chrome.runtime.sendMessage({ type: "LIVE_TRACKING_TOGGLED", isLive });
});

// ── Backend URL Configuration ──────────────────────────────────────────
const DEFAULT_BACKEND_URL = "http://127.0.0.1:5173";

// Load saved URL
chrome.storage.local.get(["owlynnBackendUrl"], (result) => {
  backendUrlInput.value = result.owlynnBackendUrl || DEFAULT_BACKEND_URL;
});

saveUrlBtn.addEventListener("click", () => {
  const url = backendUrlInput.value.trim() || DEFAULT_BACKEND_URL;
  
  // Validate URL
  try {
    new URL(url);
  } catch {
    urlFeedbackEl.textContent = "Invalid URL format.";
    urlFeedbackEl.style.color = "#c33";
    setTimeout(() => { urlFeedbackEl.textContent = ""; }, 3000);
    return;
  }

  chrome.storage.local.set({ owlynnBackendUrl: url }, () => {
    urlFeedbackEl.textContent = "URL saved! Reload extension to apply.";
    urlFeedbackEl.style.color = "#0a7";
    setTimeout(() => { urlFeedbackEl.textContent = ""; }, 3000);
    
    // Notify background script to update
    chrome.runtime.sendMessage({ type: "BACKEND_URL_UPDATED", url });
  });
});

refreshStatus();
