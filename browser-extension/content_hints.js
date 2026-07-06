(async function injectHints() {
  // Remove existing hints if any
  document.querySelectorAll('.owlynn-hint').forEach(e => e.remove());
  
  // Get config
  const config = await new Promise(resolve => {
    chrome.storage.local.get(['owlynnHintConfig'], (res) => {
      resolve(res.owlynnHintConfig || {
        background: '#ffef00',
        color: '#000',
        opacity: '1'
      });
    });
  });
  
  const interactables = document.querySelectorAll('a, button, input, select, textarea, [role="button"], [role="link"], [tabindex]:not([tabindex="-1"])');
  let counter = 1;
  
  interactables.forEach(el => {
    const rect = el.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden') {
      const hint = document.createElement('div');
      hint.className = 'owlynn-hint';
      hint.textContent = counter;
      el.setAttribute('data-owlynn-hint', counter);
      
      Object.assign(hint.style, {
        position: 'absolute',
        left: (rect.left + window.scrollX) + 'px',
        top: (rect.top + window.scrollY) + 'px',
        background: config.background || '#ffef00',
        color: config.color || '#000',
        opacity: config.opacity || '1',
        padding: '2px 4px',
        fontSize: '12px',
        fontWeight: 'bold',
        border: `1px solid ${config.color || '#000'}`,
        zIndex: '2147483647',
        pointerEvents: 'none',
        borderRadius: '3px'
      });
      
      document.body.appendChild(hint);
      counter++;
    }
  });
  
  return { success: true, count: counter - 1 };
})();
