import { _electron as electron, test, expect } from '@playwright/test';

test.describe('Screen-Assist Feature', () => {
  let electronApp;
  let page;

  test.beforeAll(async () => {
    electronApp = await electron.launch({ args: ['.'] });
    page = await electronApp.firstWindow();
  });

  test.afterAll(async () => {
    await electronApp.close();
  });

  test('triggering screen-assist displays context prompt', async () => {
    // Open Screen Assist section first
    await page.getByText('Screen Assist', { exact: true }).click();

    // Locate the screen assist activation button
    const screenAssistBtn = page.locator('[data-testid="screen-assist-btn"]');
    
    // Ensure the feature exists and is accessible
    await expect(screenAssistBtn).toBeVisible();

    // Click to activate screen-assist
    await screenAssistBtn.click();

    // Verify system feedback (e.g. operator note)
    await expect(page.locator('.operator-note')).toContainText('Captured screen');
  });
});
