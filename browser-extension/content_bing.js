(function () {
  console.log("[Owlynn Bing Scraper] Script injected and scanning...");

  function scrapePage() {
    const hits = [];

    // Check for Bing's built-in AI chat/summary element (Bing Copilot inline)
    const copilotSelector = "div.b_oppecCard, div.b_chatContainer, div[class*='copilot']";
    const copilotContainer = document.querySelector(copilotSelector);
    if (copilotContainer) {
      const text = copilotContainer.innerText.trim();
      if (text.length > 150) {
        hits.push({
          title: "⭐ Bing Copilot AI Summary",
          href: window.location.href,
          body: text.substring(0, 2500)
        });
      }
    }

    const resultElements = document.querySelectorAll("li.b_algo");
    console.log(`[Owlynn Bing Scraper] Found ${resultElements.length} search entries.`);

    for (const el of resultElements) {
      const titleEl = el.querySelector("h2 a");
      if (!titleEl) continue;

      const title = titleEl.innerText.trim();
      const href = titleEl.href;

      if (!href.startsWith("http") || href.includes("bing.com/")) {
        continue;
      }

      // Try to find description snippet
      const captionP = el.querySelector(".b_caption p") || el.querySelector(".b_snippet") || el.querySelector("p");
      const body = captionP ? captionP.innerText.trim() : "No snippet available.";

      if (!hits.some(h => h.href === href)) {
        hits.push({ title, href, body });
      }

      if (hits.length >= 8) break;
    }

    console.log(`[Owlynn Bing Scraper] Sending ${hits.length} hits back to background...`);
    chrome.runtime.sendMessage({
      type: "SCRAPE_RESULTS",
      hits: hits
    });
  }

  const READY_BUDGET_MS = 12000;
  function waitThenScrape() {
    if (document.querySelector("li.b_algo")) {
      scrapePage();
      return;
    }
    const started = Date.now();
    const observer = new MutationObserver(() => {
      if (document.querySelector("li.b_algo") || Date.now() - started > READY_BUDGET_MS) {
        observer.disconnect();
        scrapePage();
      }
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
    setTimeout(() => {
      observer.disconnect();
      scrapePage();
    }, READY_BUDGET_MS);
  }

  setTimeout(waitThenScrape, 200);
})();
