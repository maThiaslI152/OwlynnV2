// Owlynn Content UI Script
// Injects a floating status indicator into the active tab

(function() {
  if (window.__owlynn_ui_injected) return;
  window.__owlynn_ui_injected = true;

  let uiContainer = null;
  let textContainer = null;
  let hideTimeout = null;

  function initUI() {
    uiContainer = document.createElement('div');
    uiContainer.id = 'owlynn-floating-ui';
    uiContainer.className = 'hidden';

    const indicator = document.createElement('div');
    indicator.className = 'owlynn-indicator';

    textContainer = document.createElement('div');
    textContainer.className = 'owlynn-text';
    textContainer.innerText = 'Owlynn is working...';

    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'owlynn-cancel-btn';
    cancelBtn.innerText = 'Cancel';
    cancelBtn.onclick = () => {
      chrome.runtime.sendMessage({ type: "OWLYNN_ABORT_AUTOMATION" });
      hideUI();
    };

    uiContainer.appendChild(indicator);
    uiContainer.appendChild(textContainer);
    uiContainer.appendChild(cancelBtn);

    document.body.appendChild(uiContainer);
  }

  function showUI(messageHtml, duration = null) {
    if (!uiContainer) initUI();
    
    textContainer.innerHTML = messageHtml;
    
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

  function initSidebar() {
    sidebarContainer = document.createElement('div');
    sidebarContainer.id = 'owlynn-sidebar-container';
    sidebarContainer.className = 'hidden';

    const closeBtn = document.createElement('button');
    closeBtn.className = 'owlynn-sidebar-close';
    closeBtn.innerText = '✕';
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
    iframe.src = `http://127.0.0.1:5173/chat/${threadId}?mode=sidebar`;
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

  // Listen for messages from the background script
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'OWLYNN_STATUS_UPDATE') {
      const { action, target, value, duration } = message.data;
      
      if (action === 'done' || action === 'hide') {
        hideUI();
        return;
      }

      let html = `<span class="owlynn-action">${action || 'Working...'}</span>`;
      if (target) {
        html += `<span class="owlynn-target">${target}</span>`;
      }
      if (value) {
        html += `<span class="owlynn-value">→ ${value}</span>`;
      }

      showUI(html, duration);
    } else if (message.type === 'OWLYNN_OPEN_SIDEBAR') {
      showSidebar(message.thread_id);
    }
  });

  // Export a function just in case background script needs to call it directly
  window.owlynnShowStatus = showUI;
  window.owlynnHideStatus = hideUI;

})();
