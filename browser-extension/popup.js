const statusEl = document.getElementById("status");
const sendBtn = document.getElementById("sendBtn");
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

refreshStatus();
