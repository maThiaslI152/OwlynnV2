# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: safemode.spec.ts >> Safemode Feature >> toggle safemode changes UI state
- Location: e2e/safemode.spec.ts:31:3

# Error details

```
Error: expect(locator).toContainText(expected) failed

Locator: locator('.operator-note')
Expected substring: "Safe Mode set to safe_readonly"
Received string:    "ⓘ Safe Mode error: Failed to fetch"
Timeout: 5000ms

Call log:
  - Expect "toContainText" with timeout 5000ms
  - waiting for locator('.operator-note')
    14 × locator resolved to <p class="operator-note">ⓘ Safe Mode error: Failed to fetch</p>
       - unexpected value "ⓘ Safe Mode error: Failed to fetch"

```

```yaml
- paragraph: "ⓘ Safe Mode error: Failed to fetch"
```

# Test source

```ts
  1  | import { _electron as electron, test, expect } from '@playwright/test';
  2  | 
  3  | test.describe('Safemode Feature', () => {
  4  |   let electronApp;
  5  |   let page;
  6  | 
  7  |   test.beforeAll(async () => {
  8  |     // Launch Electron app
  9  |     electronApp = await electron.launch({ args: ['.'] });
  10 |     page = await electronApp.firstWindow();
  11 |     
  12 |     // Mock the backend API fetch since page.route doesn't intercept file:// requests in Electron
  13 |     await page.addInitScript(() => {
  14 |       const originalFetch = window.fetch;
  15 |       window.fetch = async (url, options) => {
  16 |         if (typeof url === 'string' && url.includes('/api/advanced-settings')) {
  17 |           return new Response(JSON.stringify({ status: 'ok' }), {
  18 |             status: 200,
  19 |             headers: { 'Content-Type': 'application/json' }
  20 |           });
  21 |         }
  22 |         return originalFetch(url, options);
  23 |       };
  24 |     });
  25 |   });
  26 | 
  27 |   test.afterAll(async () => {
  28 |     await electronApp.close();
  29 |   });
  30 | 
  31 |   test('toggle safemode changes UI state', async () => {
  32 |     // Open Safe Mode popover by clicking the shield icon in topbar
  33 |     await page.getByTitle('Security & Safe Mode').click();
  34 | 
  35 |     // Locate the safemode toggle in the popover
  36 |     const safemodeToggle = page.locator('[data-testid="safemode-toggle"]');
  37 |     
  38 |     // Ensure it exists
  39 |     await expect(safemodeToggle).toBeVisible();
  40 | 
  41 |     // Initial state should be normal
  42 |     await expect(safemodeToggle).toHaveValue('normal');
  43 | 
  44 |     // Select safe mode
  45 |     await safemodeToggle.selectOption('safe_readonly');
  46 | 
  47 |     // Verify UI reflects safemode (e.g., operator note displays the change)
> 48 |     await expect(page.locator('.operator-note')).toContainText('Safe Mode set to safe_readonly');
     |                                                  ^ Error: expect(locator).toContainText(expected) failed
  49 | 
  50 |     // Revert to disable safemode
  51 |     await safemodeToggle.selectOption('normal');
  52 |   });
  53 | });
  54 | 
```