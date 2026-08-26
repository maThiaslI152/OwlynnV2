// Owlynn Content UI Script
// Injects a floating status indicator into the active tab

(function () {
  if (window.__owlynn_ui_injected) return;
  window.__owlynn_ui_injected = true;

  let uiContainer = null;
  let textContainer = null;
  let hideTimeout = null;

  // Sanitize text for safe DOM insertion
  function sanitize(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = String(text);
    return div.textContent;
  }

  function initUI() {
    uiContainer = document.createElement("div");
    uiContainer.id = "owlynn-floating-ui";
    uiContainer.className = "hidden";

    const indicator = document.createElement("div");
    indicator.className = "owlynn-indicator";

    textContainer = document.createElement("div");
    textContainer.className = "owlynn-text";
    textContainer.textContent = "Owlynn is working...";

    const cancelBtn = document.createElement("button");
    cancelBtn.className = "owlynn-cancel-btn";
    cancelBtn.textContent = "Cancel";
    cancelBtn.onclick = () => {
      chrome.runtime.sendMessage({ type: "OWLYNN_ABORT_AUTOMATION" });
      hideUI();
    };

    uiContainer.appendChild(indicator);
    uiContainer.appendChild(textContainer);
    uiContainer.appendChild(cancelBtn);

    document.body.appendChild(uiContainer);
  }

  function showUI(messageText, duration = null) {
    if (!uiContainer) initUI();
    textContainer.textContent = sanitize(messageText);
    uiContainer.classList.remove("hidden");
    uiContainer.classList.add("visible");

    if (hideTimeout) clearTimeout(hideTimeout);

    if (duration) {
      hideTimeout = setTimeout(() => hideUI(), duration);
    }
  }

  function hideUI() {
    if (!uiContainer) return;
    uiContainer.classList.remove("visible");
    uiContainer.classList.add("hidden");
  }

  // Build status UI using DOM APIs (safe, no innerHTML)
  function buildStatusHtml(data) {
    const { action, target, value } = data;
    const container = document.createDocumentFragment();

    if (action) {
      const actionSpan = document.createElement("span");
      actionSpan.className = "owlynn-action";
      actionSpan.textContent = sanitize(action);
      container.appendChild(actionSpan);
    }

    if (target) {
      const targetSpan = document.createElement("span");
      targetSpan.className = "owlynn-target";
      targetSpan.textContent = sanitize(target);
      container.appendChild(targetSpan);
    }

    if (value) {
      const valueSpan = document.createElement("span");
      valueSpan.className = "owlynn-value";
      valueSpan.textContent = "→ " + sanitize(value);
      container.appendChild(valueSpan);
    }

    return container;
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "OWLYNN_STATUS_UPDATE") {
      const { action, duration } = message.data;

      if (action === "done" || action === "hide") {
        hideUI();
        return;
      }

      if (!uiContainer) initUI();
      textContainer.textContent = "";
      textContainer.appendChild(buildStatusHtml(message.data));

      uiContainer.classList.remove("hidden");
      uiContainer.classList.add("visible");

      if (hideTimeout) clearTimeout(hideTimeout);
      if (duration) {
        hideTimeout = setTimeout(() => hideUI(), duration);
      }
    } else if (message.type === "OWLYNN_COOKIE_CONSENT") {
      const approved = confirm(
        `Owlynn requests cookies for ${message.domain}. Allow?`
      );
      sendResponse({ approved: approved });
    }
  });
})();
