(function interactWithDOM() {
  const args = window.__owlynn_interact_args;
  if (!args) return { success: false, error: "No arguments provided." };

  const { action, selector, text, y, element_id } = args;

  try {
    if (action === "scroll") {
      window.scrollBy(0, y || window.innerHeight / 2);
      return { success: true };
    }

    let els = [];
    if (element_id !== undefined && element_id !== -1 && window.__owlynn_dom_map) {
      const el = window.__owlynn_dom_map.get(element_id);
      if (el) els = [el];
      else return { success: false, error: "Element ID " + element_id + " not found in DOM map." };
    } else {
      if (!selector) return { success: false, error: "Selector or element_id is required for action: " + action };
      els = Array.from(document.querySelectorAll(selector));
    }
    
    if (els.length === 0) return { success: false, error: "Element not found" };

    if (action === "get_html") {
      const htmls = Array.from(els).map(el => el.outerHTML);
      return { success: true, result: htmls.join("\n\n") };
    }

    if (action === "click") {
      els.forEach(el => el.click());
      return { success: true, result: `Clicked ${els.length} elements.` };
    } else if (action === "type") {
      els.forEach(el => {
        el.focus();
        // Emulate setting value and triggering events for React/Vue
      const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      const nativeTextAreaValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
      
      if (el.tagName.toLowerCase() === 'textarea' && nativeTextAreaValueSetter) {
        nativeTextAreaValueSetter.call(el, text || "");
      } else if (nativeInputValueSetter) {
        nativeInputValueSetter.call(el, text || "");
      } else {
        el.value = text || "";
      }
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      });
      return { success: true, result: `Typed into ${els.length} elements.` };
    }

    return { success: false, error: "Unknown action: " + action };
  } catch (err) {
    return { success: false, error: String(err) };
  }
})();
