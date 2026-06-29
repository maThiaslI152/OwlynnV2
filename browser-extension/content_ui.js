// Owlynn Content UI Script
// Injects a floating status indicator into the active tab

(function() {
  if (window.__owlynn_ui_injected) return;
  window.__owlynn_ui_injected = true;

  let uiContainer = null;
  let textContainer = null;
  let hideTimeout = null;

  // Sanitize text for safe DOM insertion
  function sanitize(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.textContent;
  }

  function initUI() {
    uiContainer = document.createElement('div');
    uiContainer.id = 'owlynn-floating-ui';
    uiContainer.className = 'hidden';

    const indicator = document.createElement('div');
    indicator.className = 'owlynn-indicator';

    textContainer = document.createElement('div');
    textContainer.className = 'owlynn-text';
    textContainer.textContent = 'Owlynn is working...';

    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'owlynn-cancel-btn';
    cancelBtn.textContent = 'Cancel';
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
    uiContainer.classList.remove('hidden');
    uiContainer.classList.add('visible');

    if (hideTimeout) clearTimeout(hideTimeout);
    
    if (duration) {
      hideTimeout = setTimeout(() => hideUI(), duration);
    }
  }

  function hideUI() {
    if (!uiContainer) return;
    uiContainer.classList.remove('visible');
    uiContainer.classList.add('hidden');
  }

  let sidebarContainer = null;
  let sidebarBaseUrl = 'http://127.0.0.1:8000'; // Default, overridden by popup config

  // Load configured URL from storage
  chrome.storage.local.get(['owlynnBackendUrl'], (result) => {
    if (result.owlynnBackendUrl) {
      sidebarBaseUrl = result.owlynnBackendUrl;
    }
  });

  function initSidebar() {
    sidebarContainer = document.createElement('div');
    sidebarContainer.id = 'owlynn-sidebar-container';
    sidebarContainer.className = 'hidden';

    const closeBtn = document.createElement('button');
    closeBtn.className = 'owlynn-sidebar-close';
    closeBtn.textContent = '✕';
    closeBtn.onclick = () => hideSidebar();

    const iframe = document.createElement('iframe');
    iframe.id = 'owlynn-sidebar-iframe';
    
    sidebarContainer.appendChild(closeBtn);
    sidebarContainer.appendChild(iframe);
    document.body.appendChild(sidebarContainer);
  }

  function showSidebar(threadId) {
    if (!sidebarContainer) initSidebar();
    const iframe = sidebarContainer.querySelector('iframe');
    // Sanitize threadId to prevent URL injection
    const safeThreadId = sanitize(threadId).replace(/[^a-zA-Z0-9\-_]/g, '');
    iframe.src = `${sidebarBaseUrl}/chat/${safeThreadId}?mode=sidebar`;
    sidebarContainer.classList.remove('hidden');
    sidebarContainer.classList.add('visible');
  }

  function hideSidebar() {
    if (!sidebarContainer) return;
    sidebarContainer.classList.remove('visible');
    sidebarContainer.classList.add('hidden');
    const iframe = sidebarContainer.querySelector('iframe');
    if (iframe) iframe.src = 'about:blank';
  }

  // Build status UI using DOM APIs (safe, no innerHTML)
  function buildStatusHtml(data) {
    const { action, target, value } = data;
    const container = document.createDocumentFragment();

    if (action) {
      const actionSpan = document.createElement('span');
      actionSpan.className = 'owlynn-action';
      actionSpan.textContent = sanitize(action);
      container.appendChild(actionSpan);
    }

    if (target) {
      const targetSpan = document.createElement('span');
      targetSpan.className = 'owlynn-target';
      targetSpan.textContent = sanitize(target);
      container.appendChild(targetSpan);
    }

    if (value) {
      const valueSpan = document.createElement('span');
      valueSpan.className = 'owlynn-value';
      valueSpan.textContent = '→ ' + sanitize(value);
      container.appendChild(valueSpan);
    }

    return container;
  }

  // Listen for messages from the background script
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'OWLYNN_STATUS_UPDATE') {
      const { action, target, value, duration } = message.data;
      
      if (action === 'done' || action === 'hide') {
        hideUI();
        return;
      }

      // Use DOM APIs instead of innerHTML (XSS-safe)
      if (!uiContainer) initUI();
      textContainer.textContent = '';
      textContainer.appendChild(buildStatusHtml(message.data));

      uiContainer.classList.remove('hidden');
      uiContainer.classList.add('visible');

      if (hideTimeout) clearTimeout(hideTimeout);
      if (duration) {
        hideTimeout = setTimeout(() => hideUI(), duration);
      }
    } else if (message.type === 'OWLYNN_OPEN_SIDEBAR') {
      showSidebar(message.thread_id);
    } else if (message.type === 'OWLYNN_COOKIE_CONSENT') {
      // Show cookie consent toast
      const approved = confirm(`Owlynn requests cookies for ${message.domain}. Allow?`);
      sendResponse({ approved: approved });
    }
  });

})();
