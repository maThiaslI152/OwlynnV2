(function () {
  console.log("[Owlynn DDG Scraper] Script injected and scanning...");

  function scrapePage() {
    const hits = [];

    // Check for DuckDuckGo DuckAssist or AI Chat answers
    const assistantSelector = "div[class*='duckassist'], div[class*='module--assistant']";
    const assistant = document.querySelector(assistantSelector);
    if (assistant) {
      const text = assistant.innerText.trim();
      if (text.length > 100) {
        hits.push({
          title: "⭐ DuckDuckGo AI Answer / DuckAssist",
          href: window.location.href,
          body: text.substring(0, 2500)
        });
      }
    }

    // Standard entries (React / Dynamic layout)
    let entries = document.querySelectorAll("article[data-testid='result']");
    if (entries.length > 0) {
      for (const el of entries) {
        const titleA = el.querySelector("a[data-testid='result-title-a']");
        const snippetDiv = el.querySelector("div[data-testid='result-snippet']");
        if (!titleA) continue;

        const title = titleA.innerText.trim();
        const href = titleA.href;
        const body = snippetDiv ? snippetDiv.innerText.trim() : "No snippet available.";

        if (!hits.some(h => h.href === href)) {
          hits.push({ title, href, body });
        }
      }
    }

    // Classic / Static HTML layout (html.duckduckgo.com)
    if (hits.length === 0) {
      entries = document.querySelectorAll("div.result");
      for (const el of entries) {
        const titleA = el.querySelector("a.result__a");
        const snippetA = el.querySelector("a.result__snippet");
        if (!titleA) continue;

        const title = titleA.innerText.trim();
        const href = titleA.href;
        const body = snippetA ? snippetA.innerText.trim() : "No snippet available.";

        if (!hits.some(h => h.href === href)) {
          hits.push({ title, href, body });
        }
      }
    }

    // Lite layout (lite.duckduckgo.com)
    if (hits.length === 0) {
      const trs = document.querySelectorAll("table tr");
      for (const tr of trs) {
        const link = tr.querySelector("a[href^='http']");
        if (!link) continue;
        const title = link.innerText.trim();
        const href = link.href;
        
        // Find next snippet row or capture text around it
        const nextTr = tr.nextElementSibling;
        const body = nextTr ? nextTr.innerText.trim().substring(0, 300) : "No snippet.";

        if (!hits.some(h => h.href === href)) {
          hits.push({ title, href, body });
        }
      }
    }

    console.log(`[Owlynn DDG Scraper] Sending ${hits.length} hits back to background...`);
    chrome.runtime.sendMessage({
      type: "SCRAPE_RESULTS",
      hits: hits
    });
  }

  setTimeout(scrapePage, 800);
})();
