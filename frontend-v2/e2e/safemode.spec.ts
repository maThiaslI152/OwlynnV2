import { _electron as electron, test, expect } from '@playwright/test';

test.describe('Safemode Feature', () => {
  let electronApp;
  let page;

  test.beforeAll(async () => {
    // Launch Electron app
    electronApp = await electron.launch({ args: ['.'] });
    page = await electronApp.firstWindow();
    
    // Mock the backend API fetch since page.route doesn't intercept file:// requests in Electron
    await page.addInitScript(() => {
      const originalFetch = window.fetch;
      window.fetch = async (url, options) => {
        if (typeof url === 'string' && url.includes('/api/advanced-settings')) {
          return new Response(JSON.stringify({ status: 'ok' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' }
          });
        }
        return originalFetch(url, options);
      };
    });
  });

  test.afterAll(async () => {
    await electronApp.close();
  });

  test('toggle safemode changes UI state', async () => {
    // Open Safe Mode popover by clicking the shield icon in topbar
    await page.getByTitle('Security & Safe Mode').click();

    // Locate the safemode toggle in the popover
    const safemodeToggle = page.locator('[data-testid="safemode-toggle"]');
    
    // Ensure it exists
    await expect(safemodeToggle).toBeVisible();

    // Initial state should be normal
    await expect(safemodeToggle).toHaveValue('normal');

    // Select safe mode
    await safemodeToggle.selectOption('safe_readonly');

    // Verify UI reflects safemode (e.g., operator note displays the change)
    await expect(page.locator('.operator-note')).toContainText('Safe Mode set to safe_readonly');

    // Revert to disable safemode
    await safemodeToggle.selectOption('normal');
  });
});
