const statusEl = document.getElementById("status");
const sendBtn = document.getElementById("sendBtn");
const liveBtn = document.getElementById("liveBtn");
const feedbackEl = document.getElementById("feedback");

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

refreshStatus();
