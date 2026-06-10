(function () {
  console.log("[Owlynn Google Scraper] Script injected. Page Title:", document.title);
  console.log("[Owlynn Google Scraper] Body text length:", document.body?.innerText?.length || 0);

  function getSnippet(el) {
    const snippetSelectors = [
      ".VwiC3b", 
      "div[style*='-webkit-line-clamp']",
      ".yD0skd",
      ".MUFPAc"
    ];
    for (const sel of snippetSelectors) {
      const target = el.querySelector(sel);
      if (target) {
        return target.innerText.trim();
      }
    }
    
    // Look for siblings or parent text as fallback
    const parent = el.closest(".g") || el.parentElement;
    if (parent) {
      const snippetEl = parent.querySelector(".VwiC3b") || parent.querySelector("div[style*='-webkit-line-clamp']");
      if (snippetEl) return snippetEl.innerText.trim();
    }
    return "";
  }

  function scrapePage() {
    const hits = [];

    // Check for CAPTCHA/bot block pages
    const bodyText = document.body?.innerText?.lower || document.body?.innerText || "";
    const isCaptcha = bodyText.includes("unusual traffic") || 
                      bodyText.includes("verify you are human") || 
                      bodyText.includes("captcha") || 
                      document.title.includes("Sorry");

    if (isCaptcha) {
      console.warn("[Owlynn Google Scraper] WARNING: CAPTCHA or Bot detection page detected!");
      hits.push({
        title: "⚠️ Bot Verification Block",
        href: window.location.href,
        body: "Google has displayed an interstitial 'unusual traffic' verification screen. Please solve it in the browser tab if it remains visible."
      });
    }

    // 1. Scrape Premium AI Overviews & Assistant Blocks
    const aiOverviewSelectors = [
      "div[data-asoch-targets]",
      "div[class*='ai-overview']",
      "div[class*='sge']",
      "div.kp-blk", 
      "div.ifM9O"
    ];

    for (const selector of aiOverviewSelectors) {
      const container = document.querySelector(selector);
      if (container) {
        const text = container.innerText.trim();
        if (text.length > 150) {
          console.log("[Owlynn Google Scraper] Found AI Overview/Snippet container");
          hits.push({
            title: "⭐ Google AI Overview / Featured Snippet Summary",
            href: window.location.href,
            body: text.substring(0, 3000) + (text.length > 3000 ? "..." : "")
          });
          break;
        }
      }
    }

    // 2. Scrape Merlin AI Sidebar Summaries
    const merlinSelectors = [
      ".merlin-box",
      ".merlin-summary",
      "div[id*='merlin']",
      "div[class*='merlin']"
    ];
    for (const selector of merlinSelectors) {
      const container = document.querySelector(selector);
      if (container) {
        const text = container.innerText.trim();
        if (text.length > 100) {
          console.log("[Owlynn Google Scraper] Found Merlin AI container");
          hits.push({
            title: "⭐ Merlin AI Sidebar Summary",
            href: window.location.href,
            body: text.substring(0, 2500)
          });
          break;
        }
      }
    }

    // 3. Scrape Standard Search Hits (Layout-agnostic selector)
    // Almost all Google results have an h3 header inside a link tag (a h3)
    const headers = document.querySelectorAll("h3");
    console.log(`[Owlynn Google Scraper] Found ${headers.length} h3 elements on page.`);

    let resultCount = 0;
    for (const h3 of headers) {
      const linkEl = h3.closest("a");
      if (!linkEl) continue;

      const href = linkEl.href;
      // Filter out internal Google links, sub-tabs, or map results
      if (!href.startsWith("http") || href.includes("google.com/search") || href.includes("google.com/preferences")) {
        continue;
      }

      const title = h3.innerText.trim();
      if (!title) continue;

      const body = getSnippet(h3) || "No snippet available.";
      
      if (!hits.some(h => h.href === href)) {
        hits.push({ title, href, body });
        resultCount++;
      }

      if (hits.length >= 10) break;
    }
    
    console.log(`[Owlynn Google Scraper] Standard search entries successfully mapped: ${resultCount}`);

    // 5. Send results to background.js
    console.log(`[Owlynn Google Scraper] Sending ${hits.length} total hits back to background...`);
    chrome.runtime.sendMessage({
      type: "SCRAPE_RESULTS",
      hits: hits
    });
  }

  // Google results can load dynamically, wait brief moment
  setTimeout(scrapePage, 800);
})();
