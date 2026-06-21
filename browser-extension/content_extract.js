(function extractPageContext() {
  const maxText = 12000;
  const maxSelection = 4000;

  function getVisibleText(root) {
    let text = "";
    const walker = document.createTreeWalker(
      root,
      NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT,
      {
        acceptNode: function(node) {
          if (node.nodeType === Node.ELEMENT_NODE) {
            const tag = node.tagName.toLowerCase();
            if (tag === 'script' || tag === 'style' || tag === 'noscript') {
              return NodeFilter.FILTER_REJECT;
            }
            const style = window.getComputedStyle(node);
            if (style.display === 'none' || style.visibility === 'hidden') {
              return NodeFilter.FILTER_REJECT;
            }
          }
          return NodeFilter.FILTER_ACCEPT;
        }
      }
    );

    let currentNode = walker.currentNode;
    while (currentNode) {
      if (currentNode.nodeType === Node.TEXT_NODE) {
        text += currentNode.nodeValue + " ";
      } else if (currentNode.shadowRoot) {
        text += getVisibleText(currentNode.shadowRoot) + " ";
      }
      currentNode = walker.nextNode();
    }
    return text.replace(/\s+/g, ' ').trim();
  }

  const selection = window.getSelection ? window.getSelection().toString() : "";
  const text = document.body ? getVisibleText(document.body) : "";

  return {
    title: document.title || "",
    url: location.href || "",
    text: text.slice(0, maxText),
    selection: selection.slice(0, maxSelection),
  };
})();
