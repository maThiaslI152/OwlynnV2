(async function interactWithDOM() {
  const args = window.__owlynn_interact_args;
  if (!args) return { success: false, error: "No arguments provided." };

  const { action, selector, wait_for_selector, text, y, element_id, element_ids } = args;

  try {
    if (action === "inject_hints") {
      if (!window.__owlynn_dom_map) return { success: false, error: "DOM map not found. Extract context first." };
      window.__owlynn_hints = [];
      window.__owlynn_dom_map.forEach((el, id) => {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0 || rect.top < 0 || rect.left < 0 || rect.bottom > window.innerHeight || rect.right > window.innerWidth) return;
        const hint = document.createElement('div');
        hint.textContent = `[${id}]`;
        hint.style.cssText = `position: absolute; top: ${rect.top + window.scrollY}px; left: ${rect.left + window.scrollX}px; background: yellow; color: black; font-size: 12px; font-weight: bold; border: 1px solid black; z-index: 2147483647; padding: 2px; pointer-events: none;`;
        document.body.appendChild(hint);
        window.__owlynn_hints.push(hint);
      });
      return { success: true, result: `Injected ${window.__owlynn_hints.length} hints.` };
    }

    if (action === "remove_hints") {
      if (window.__owlynn_hints) {
        window.__owlynn_hints.forEach(hint => hint.remove());
        window.__owlynn_hints = [];
      }
      return { success: true, result: "Hints removed." };
    }

    // ── Phase 1: Navigation Actions ──────────────────────────────────────

    if (action === "wait_for_navigation") {
      return { success: true, result: "wait_for_navigation handled by background script." };
    }

    if (action === "scroll_to_element") {
      let els = [];
      if (element_ids && element_ids.length > 0 && window.__owlynn_dom_map) {
        element_ids.forEach(id => {
          const el = window.__owlynn_dom_map.get(id);
          if (el) els.push(el);
        });
      } else if (element_id !== undefined && element_id !== -1 && window.__owlynn_dom_map) {
        const el = window.__owlynn_dom_map.get(element_id);
        if (el) els = [el];
      } else if (selector) {
        els = Array.from(document.querySelectorAll(selector));
      }
      if (els.length === 0) return { success: false, error: "No element found for scroll_to_element." };
      els.forEach(el => el.scrollIntoView({ behavior: 'smooth', block: 'center' }));
      return { success: true, result: `Scrolled to ${els.length} elements.` };
    }

    if (action === "select_option") {
      let els = [];
      if (element_ids && element_ids.length > 0 && window.__owlynn_dom_map) {
        element_ids.forEach(id => {
          const el = window.__owlynn_dom_map.get(id);
          if (el) els.push(el);
        });
      } else if (element_id !== undefined && element_id !== -1 && window.__owlynn_dom_map) {
        const el = window.__owlynn_dom_map.get(element_id);
        if (el) els = [el];
      } else if (selector) {
        els = Array.from(document.querySelectorAll(selector));
      }
      if (els.length === 0) return { success: false, error: "No element found for select_option." };
      const optionValue = args.value || args.option_text || text;
      els.forEach(el => {
        if (el.tagName.toLowerCase() === 'select') {
          // Find option by value or text
          const options = Array.from(el.options);
          const match = options.find(o => o.value === optionValue || o.text === optionValue);
          if (match) {
            el.value = match.value;
            el.dispatchEvent(new Event('change', { bubbles: true }));
          }
        }
      });
      return { success: true, result: `Selected option in ${els.length} elements.` };
    }

    if (action === "submit_form") {
      let els = [];
      if (element_ids && element_ids.length > 0 && window.__owlynn_dom_map) {
        element_ids.forEach(id => {
          const el = window.__owlynn_dom_map.get(id);
          if (el) els.push(el);
        });
      } else if (element_id !== undefined && element_id !== -1 && window.__owlynn_dom_map) {
        const el = window.__owlynn_dom_map.get(element_id);
        if (el) els = [el];
      } else if (selector) {
        els = Array.from(document.querySelectorAll(selector));
      }
      if (els.length === 0) return { success: false, error: "No element found for submit_form." };
      let submitted = 0;
      els.forEach(el => {
        const form = el.closest('form');
        if (form) {
          if (form.requestSubmit) {
            form.requestSubmit();
          } else {
            form.submit();
          }
          submitted++;
        }
      });
      return { success: true, result: `Submitted ${submitted} forms.` };
    }

    if (action === "focus") {
      let els = [];
      if (element_ids && element_ids.length > 0 && window.__owlynn_dom_map) {
        element_ids.forEach(id => {
          const el = window.__owlynn_dom_map.get(id);
          if (el) els.push(el);
        });
      } else if (element_id !== undefined && element_id !== -1 && window.__owlynn_dom_map) {
        const el = window.__owlynn_dom_map.get(element_id);
        if (el) els = [el];
      } else if (selector) {
        els = Array.from(document.querySelectorAll(selector));
      }
      if (els.length === 0) return { success: false, error: "No element found for focus." };
      els.forEach(el => el.focus());
      return { success: true, result: `Focused ${els.length} elements.` };
    }

    // ── Phase 2: Batch Selection Actions ─────────────────────────────────

    if (action === "select_checkboxes") {
      const checked = args.checked !== undefined ? args.checked : true;
      let els = [];
      if (element_ids && element_ids.length > 0 && window.__owlynn_dom_map) {
        element_ids.forEach(id => {
          const el = window.__owlynn_dom_map.get(id);
          if (el && (el.type === 'checkbox' || el.tagName.toLowerCase() === 'input')) els.push(el);
        });
      } else if (selector) {
        els = Array.from(document.querySelectorAll(selector)).filter(el => el.type === 'checkbox');
      }
      if (els.length === 0) return { success: false, error: "No checkboxes found." };
      els.forEach(el => {
        el.checked = checked;
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('input', { bubbles: true }));
      });
      return { success: true, result: `${checked ? 'Checked' : 'Unchecked'} ${els.length} checkboxes.` };
    }

    if (action === "select_radio") {
      let els = [];
      if (element_id !== undefined && element_id !== -1 && window.__owlynn_dom_map) {
        const el = window.__owlynn_dom_map.get(element_id);
        if (el) els = [el];
      } else if (selector) {
        els = Array.from(document.querySelectorAll(selector));
      }
      if (els.length === 0) return { success: false, error: "No radio button found." };
      els.forEach(el => {
        el.checked = true;
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('input', { bubbles: true }));
      });
      return { success: true, result: `Selected ${els.length} radio buttons.` };
    }

    if (action === "type_into_sequence") {
      // Type into multiple fields sequentially with Tab between
      const texts = args.texts || [];
      if (!element_ids || element_ids.length === 0) return { success: false, error: "element_ids required for type_into_sequence." };
      if (texts.length === 0) return { success: false, error: "texts array required for type_into_sequence." };

      const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      const nativeTextAreaValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;

      let typed = 0;
      for (let i = 0; i < element_ids.length; i++) {
        const el = window.__owlynn_dom_map.get(element_ids[i]);
        if (!el) continue;
        const t = texts[i] || texts[texts.length - 1] || "";

        el.focus();
        if (el.tagName.toLowerCase() === 'textarea' && nativeTextAreaValueSetter) {
          nativeTextAreaValueSetter.call(el, t);
        } else if (nativeInputValueSetter) {
          nativeInputValueSetter.call(el, t);
        } else {
          el.value = t;
        }
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        typed++;

        // Press Tab between fields (not after last)
        if (i < element_ids.length - 1) {
          el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', code: 'Tab', keyCode: 9, bubbles: true }));
          el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Tab', code: 'Tab', keyCode: 9, bubbles: true }));
        }
      }
      return { success: true, result: `Typed into ${typed} fields with Tab between.` };
    }

    // ── Element Resolution ───────────────────────────────────────────────

    let els = [];
    if (element_ids && element_ids.length > 0 && window.__owlynn_dom_map) {
      element_ids.forEach(id => {
        const el = window.__owlynn_dom_map.get(id);
        if (el) els.push(el);
      });
      if (els.length === 0 && action !== "scroll") return { success: false, error: "None of the provided Element IDs were found." };
    } else if (element_id !== undefined && element_id !== -1 && window.__owlynn_dom_map) {
      const el = window.__owlynn_dom_map.get(element_id);
      if (el) els = [el];
      else if (action !== "scroll") return { success: false, error: "Element ID " + element_id + " not found in DOM map." };
    } else if (selector) {
      // Validate selector — block dangerous URI schemes
      if (/^(javascript|data|vbscript):/i.test(selector.trim())) {
        return { success: false, error: "Blocked dangerous selector scheme." };
      }
      els = Array.from(document.querySelectorAll(selector));
    }
    
    if (action === "scroll") {
      if (els.length > 0) {
        els.forEach(el => {
          if (el.scrollBy) el.scrollBy(0, y || el.clientHeight / 2);
          else el.scrollTop += (y || 200);
        });
        return { success: true, result: `Scrolled ${els.length} elements.` };
      } else {
        window.scrollBy(0, y || window.innerHeight / 2);
        return { success: true, result: "Scrolled window." };
      }
    }

    if (els.length === 0) return { success: false, error: "Element not found for action: " + action };

    if (action === "get_html") {
      const htmls = Array.from(els).map(el => {
        // Clone to avoid mutating the live DOM
        const clone = el.cloneNode(true);
        
        // Remove sensitive elements from clone
        clone.querySelectorAll('input[type="password"], input[type="hidden"]').forEach(e => e.remove());
        // Remove elements with names suggesting secrets
        clone.querySelectorAll('input[name*="token"], input[name*="csrf"], input[name*="secret"], input[name*="api_key"]').forEach(e => e.remove());
        
        // Sync input/textarea values to attributes for outerHTML serialization
        const inputs = el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' ? [el] : Array.from(el.querySelectorAll('input, textarea, select'));
        const cloneInputs = clone.tagName === 'INPUT' || clone.tagName === 'TEXTAREA' || clone.tagName === 'SELECT' ? [clone] : Array.from(clone.querySelectorAll('input, textarea, select'));
        
        for (let i = 0; i < inputs.length; i++) {
          const original = inputs[i];
          const clonedInput = cloneInputs[i];
          // Skip sensitive fields
          if (original.type === 'password' || original.type === 'hidden') continue;
          if (/token|csrf|secret|api_key/i.test(original.name || '')) continue;
          if (original.tagName === 'INPUT' && (original.type === 'checkbox' || original.type === 'radio')) {
            if (original.checked) clonedInput.setAttribute('checked', 'checked');
            else clonedInput.removeAttribute('checked');
          } else if (original.tagName === 'SELECT') {
            const originalOptions = Array.from(original.options);
            const clonedOptions = Array.from(clonedInput.options);
            for (let j = 0; j < originalOptions.length; j++) {
              if (originalOptions[j].selected) clonedOptions[j].setAttribute('selected', 'selected');
              else clonedOptions[j].removeAttribute('selected');
            }
          } else {
            clonedInput.setAttribute('value', original.value);
            if (original.tagName === 'TEXTAREA') clonedInput.textContent = original.value;
          }
        }
        return clone.outerHTML;
      });
      return { success: true, result: htmls.join("\n\n") };
    }

    function dispatchMouse(el, type) {
      const rect = el.getBoundingClientRect();
      const x = rect.left + rect.width / 2;
      const y = rect.top + rect.height / 2;
      const ev = new MouseEvent(type, {
        view: window, bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0, buttons: type.includes('down') ? 1 : 0
      });
      el.dispatchEvent(ev);
    }

    function dispatchPointer(el, type) {
      const rect = el.getBoundingClientRect();
      const x = rect.left + rect.width / 2;
      const y = rect.top + rect.height / 2;
      const ev = new PointerEvent(type, {
        view: window, bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0, buttons: type.includes('down') ? 1 : 0, pointerId: 1, pointerType: 'mouse', isPrimary: true
      });
      el.dispatchEvent(ev);
    }

    function simulateHoverSequence(el) {
      dispatchPointer(el, 'pointerover'); dispatchMouse(el, 'mouseover');
      dispatchPointer(el, 'pointerenter'); dispatchMouse(el, 'mouseenter');
      dispatchPointer(el, 'pointermove'); dispatchMouse(el, 'mousemove');
    }

    function simulateClickSequence(el) {
      simulateHoverSequence(el);
      dispatchPointer(el, 'pointerdown'); dispatchMouse(el, 'mousedown');
      el.focus();
      dispatchPointer(el, 'pointerup'); dispatchMouse(el, 'mouseup');
      el.click();
    }

    if (action === "hover") {
      els.forEach(el => simulateHoverSequence(el));
      return { success: true, result: `Hovered over ${els.length} elements.` };
    }

    if (action === "click") {
      els.forEach(el => {
        if (el.tagName.toLowerCase() === 'option') {
          el.selected = true;
          if (el.parentElement) el.parentElement.dispatchEvent(new Event('change', { bubbles: true }));
        } else {
          simulateClickSequence(el);
        }
      });
      
      if (wait_for_selector) {
        return new Promise((resolve) => {
          if (document.querySelector(wait_for_selector)) {
            resolve({ success: true, result: `Clicked ${els.length} elements. Target appeared.` });
            return;
          }
          const observer = new MutationObserver((mutations, obs) => {
            if (document.querySelector(wait_for_selector)) {
              obs.disconnect();
              resolve({ success: true, result: `Clicked ${els.length} elements. Target appeared.` });
            }
          });
          observer.observe(document.body, { childList: true, subtree: true });
          setTimeout(() => {
            observer.disconnect();
            resolve({ success: true, result: `Clicked ${els.length} elements, but ${wait_for_selector} did not appear within 5000ms.` });
          }, 5000);
        });
      }
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
      
      if (wait_for_selector) {
        return new Promise((resolve) => {
          if (document.querySelector(wait_for_selector)) {
            resolve({ success: true, result: `Typed into ${els.length} elements. Target appeared.` });
            return;
          }
          const observer = new MutationObserver((mutations, obs) => {
            if (document.querySelector(wait_for_selector)) {
              obs.disconnect();
              resolve({ success: true, result: `Typed into ${els.length} elements. Target appeared.` });
            }
          });
          observer.observe(document.body, { childList: true, subtree: true });
          setTimeout(() => {
            observer.disconnect();
            resolve({ success: true, result: `Typed into ${els.length} elements, but ${wait_for_selector} did not appear within 5000ms.` });
          }, 5000);
        });
      }
      return { success: true, result: `Typed into ${els.length} elements.` };
    }

    return { success: false, error: "Unknown action: " + action };
  } catch (err) {
    return { success: false, error: String(err) };
  }
})();
