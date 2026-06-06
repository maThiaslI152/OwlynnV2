import { _electron as electron, test, expect } from '@playwright/test';

test.describe('Safemode Feature', () => {
  let electronApp;
  let page;

  test.beforeAll(async () => {
    // Launch Electron app
    electronApp = await electron.launch({ args: ['.'] });
    page = await electronApp.firstWindow();
  });

  test.afterAll(async () => {
    await electronApp.close();
  });

  test('toggle safemode changes UI state', async () => {
    // Open Safe Mode section first
    await page.getByText('Safe Mode', { exact: true }).click();

    // Locate the safemode toggle on the sidebar
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
