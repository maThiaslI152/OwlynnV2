(function () {
  console.log("[Owlynn Google Scraper] Script injected. Page Title:", document.title);

  const RESULT_SELECTORS = [
    "#search h3",
    "#rso h3",
    "div#search a h3",
    "div.g h3",
  ];
  const READY_BUDGET_MS = 12000; // keep under backend extension timeout (15s)

  function getSnippet(el) {
    const snippetSelectors = [
      ".VwiC3b",
      "div[style*='-webkit-line-clamp']",
      ".yD0skd",
      ".MUFPAc",
    ];
    for (const sel of snippetSelectors) {
      const target = el.querySelector(sel);
      if (target) {
        return target.innerText.trim();
      }
    }

    const parent = el.closest(".g") || el.parentElement;
    if (parent) {
      const snippetEl =
        parent.querySelector(".VwiC3b") ||
        parent.querySelector("div[style*='-webkit-line-clamp']");
      if (snippetEl) return snippetEl.innerText.trim();
    }
    return "";
  }

  function isCaptchaPage() {
    const bodyText = (document.body?.innerText || "").toLowerCase();
    return (
      bodyText.includes("unusual traffic") ||
      bodyText.includes("verify you are human") ||
      bodyText.includes("captcha") ||
      document.title.includes("Sorry") ||
      !!document.querySelector("#captcha-form, form#captcha, #recaptcha")
    );
  }

  function hasResultMarkers() {
    for (const sel of RESULT_SELECTORS) {
      if (document.querySelector(sel)) return true;
    }
    return false;
  }

  function scrapePage() {
    // CAPTCHA → hard failure (empty hits) so web_search falls through to next tier
    if (isCaptchaPage()) {
      console.warn(
        "[Owlynn Google Scraper] CAPTCHA/bot page detected — reporting hard failure."
      );
      chrome.runtime.sendMessage({
        type: "SCRAPE_RESULTS",
        hits: [],
        error: "captcha",
      });
      return;
    }

    const hits = [];

    const aiOverviewSelectors = [
      "div[data-asoch-targets]",
      "div[class*='ai-overview']",
      "div[class*='sge']",
      "div.kp-blk",
      "div.ifM9O",
    ];

    for (const selector of aiOverviewSelectors) {
      const container = document.querySelector(selector);
      if (container) {
        const text = container.innerText.trim();
        if (text.length > 150) {
          hits.push({
            title: "⭐ Google AI Overview / Featured Snippet Summary",
            href: window.location.href,
            body: text.substring(0, 3000) + (text.length > 3000 ? "..." : ""),
          });
          break;
        }
      }
    }

    const merlinSelectors = [
      ".merlin-box",
      ".merlin-summary",
      "div[id*='merlin']",
      "div[class*='merlin']",
    ];
    for (const selector of merlinSelectors) {
      const container = document.querySelector(selector);
      if (container) {
        const text = container.innerText.trim();
        if (text.length > 100) {
          hits.push({
            title: "⭐ Merlin AI Sidebar Summary",
            href: window.location.href,
            body: text.substring(0, 2500),
          });
          break;
        }
      }
    }

    const headers = document.querySelectorAll("h3");
    let resultCount = 0;
    for (const h3 of headers) {
      const linkEl = h3.closest("a");
      if (!linkEl) continue;

      const href = linkEl.href;
      if (
        !href.startsWith("http") ||
        href.includes("google.com/search") ||
        href.includes("google.com/preferences")
      ) {
        continue;
      }

      const title = h3.innerText.trim();
      if (!title) continue;

      const body = getSnippet(h3) || "No snippet available.";

      if (!hits.some((h) => h.href === href)) {
        hits.push({ title, href, body });
        resultCount++;
      }

      if (hits.length >= 10) break;
    }

    console.log(
      `[Owlynn Google Scraper] Sending ${hits.length} hits (${resultCount} standard)...`
    );
    chrome.runtime.sendMessage({
      type: "SCRAPE_RESULTS",
      hits: hits,
    });
  }

  function waitForResultsThenScrape() {
    if (isCaptchaPage()) {
      scrapePage();
      return;
    }
    if (hasResultMarkers()) {
      scrapePage();
      return;
    }

    const started = Date.now();
    const observer = new MutationObserver(() => {
      if (isCaptchaPage() || hasResultMarkers() || Date.now() - started > READY_BUDGET_MS) {
        observer.disconnect();
        scrapePage();
      }
    });
    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
    });

    setTimeout(() => {
      observer.disconnect();
      scrapePage();
    }, READY_BUDGET_MS);
  }

  // Short initial delay, then observe until results or budget
  setTimeout(waitForResultsThenScrape, 200);
})();
