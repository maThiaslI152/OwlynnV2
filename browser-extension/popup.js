const statusEl = document.getElementById("status");
const sendBtn = document.getElementById("sendBtn");
const feedbackEl = document.getElementById("feedback");
const backendUrlInput = document.getElementById("backendUrl");
const saveUrlBtn = document.getElementById("saveUrlBtn");
const urlFeedbackEl = document.getElementById("urlFeedback");

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);

function isLoopbackHostname(hostname) {
  const h = String(hostname || "").toLowerCase().replace(/^\[|\]$/g, "");
  return LOOPBACK_HOSTS.has(h) || LOOPBACK_HOSTS.has(hostname);
}

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

chrome.storage.local.get(["owlynnBackendUrl"], (result) => {
  backendUrlInput.value = result.owlynnBackendUrl || DEFAULT_BACKEND_URL;
});

saveUrlBtn.addEventListener("click", () => {
  const url = backendUrlInput.value.trim() || DEFAULT_BACKEND_URL;

  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    urlFeedbackEl.textContent = "Invalid URL format.";
    urlFeedbackEl.style.color = "#c33";
    setTimeout(() => {
      urlFeedbackEl.textContent = "";
    }, 3000);
    return;
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    urlFeedbackEl.textContent = "Only http(s) backends are allowed.";
    urlFeedbackEl.style.color = "#c33";
    setTimeout(() => {
      urlFeedbackEl.textContent = "";
    }, 3000);
    return;
  }

  if (!isLoopbackHostname(parsed.hostname)) {
    const ok = confirm(
      `Use remote Owlynn backend at ${parsed.origin}? ` +
        "This sends auth tokens, page text, cookies, and screenshots off this machine."
    );
    if (!ok) {
      urlFeedbackEl.textContent = "Remote backend cancelled.";
      urlFeedbackEl.style.color = "#c33";
      setTimeout(() => {
        urlFeedbackEl.textContent = "";
      }, 3000);
      return;
    }
  }

  chrome.storage.local.set({ owlynnBackendUrl: parsed.origin }, () => {
    urlFeedbackEl.textContent = "URL saved! Reconnecting…";
    urlFeedbackEl.style.color = "#0a7";
    setTimeout(() => {
      urlFeedbackEl.textContent = "";
    }, 3000);

    chrome.runtime.sendMessage({
      type: "BACKEND_URL_UPDATED",
      url: parsed.origin,
    });
  });
});

refreshStatus();
