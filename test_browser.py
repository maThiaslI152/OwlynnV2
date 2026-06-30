from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.on("console", lambda msg: print(f"BROWSER_LOG: {msg.text}"))
    page.on("pageerror", lambda err: print(f"BROWSER_ERROR: {err}"))
    try:
        page.goto("http://localhost:5173", wait_until="networkidle")
    except Exception as e:
        print(f"Exception: {e}")
    browser.close()
