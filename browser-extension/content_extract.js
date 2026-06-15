(function extractPageContext() {
  const maxText = 12000;
  const maxSelection = 4000;
  const selection = window.getSelection ? window.getSelection().toString() : "";
  const text = document.body ? document.body.innerText : "";
  return {
    title: document.title || "",
    url: location.href || "",
    text: text.slice(0, maxText),
    selection: selection.slice(0, maxSelection),
  };
})();
