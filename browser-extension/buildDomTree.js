/**
 * Owlynn Bridge Extension - DOM Distillation
 * Inspired by browser-use. Builds a token-efficient representation of the page
 * and maintains a map of interactive elements for reliable execution.
 */

(function() {
    // Reset the map on every extraction
    window.__owlynn_dom_map = new Map();
    let elementIndex = 0;
    
    function isVisible(el) {
        if (!el || !el.getBoundingClientRect) return false;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return false;
        
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        
        return true;
    }
    
    function isInteractive(el) {
        const tagName = el.tagName.toLowerCase();
        const interactiveTags = ['a', 'button', 'input', 'select', 'textarea'];
        if (interactiveTags.includes(tagName)) return true;
        
        if (el.hasAttribute('onclick')) return true;
        if (el.getAttribute('role') === 'button' || el.getAttribute('role') === 'link') return true;
        
        // Content editable
        if (el.getAttribute('contenteditable') === 'true') return true;
        
        return false;
    }
    
    function extractText(el) {
        // Simple text extraction for the label
        let text = el.innerText || el.value || el.getAttribute('placeholder') || el.getAttribute('aria-label') || '';
        return text.trim().replace(/\n/g, ' ').substring(0, 50);
    }
    
    function traverse(node, depth = 0) {
        if (!node) return '';
        if (node.nodeType === Node.TEXT_NODE) return ''; // We handle text inside elements
        if (node.nodeType !== Node.ELEMENT_NODE) return '';
        
        if (!isVisible(node)) return '';
        
        const tagName = node.tagName.toLowerCase();
        if (['script', 'style', 'noscript', 'svg', 'canvas', 'video', 'audio'].includes(tagName)) return '';
        
        let output = '';
        
        if (isInteractive(node)) {
            const currentId = elementIndex++;
            window.__owlynn_dom_map.set(currentId, node);
            
            const label = extractText(node);
            const type = tagName;
            
            output += `[@${currentId}] ${type}: ${label ? '"' + label + '"' : 'unlabeled'}\n`;
        }
        
        // Traverse children
        for (let i = 0; i < node.childNodes.length; i++) {
            output += traverse(node.childNodes[i], depth + 1);
        }
        
        return output;
    }
    
    const pageTitle = document.title;
    const pageUrl = window.location.href;
    
    let result = `# Page: ${pageTitle}\n# URL: ${pageUrl}\n\n## Interactive Elements:\n`;
    result += traverse(document.body);
    
    return result;
})();
