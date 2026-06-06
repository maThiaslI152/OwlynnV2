# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: safemode.spec.ts >> Safemode Feature >> toggle safemode changes UI state
- Location: e2e/safemode.spec.ts:17:3

# Error details

```
Test timeout of 30000ms exceeded.
```

```
TimeoutError: locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for getByText('Safe Mode', { exact: true })

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - complementary [ref=e4]:
    - generic [ref=e6]:
      - generic [ref=e7]:
        - heading "Workspace" [level=2] [ref=e8]
        - generic [ref=e9]:
          - button "+ New" [ref=e10] [cursor=pointer]
          - button "Refresh" [ref=e11] [cursor=pointer]
      - paragraph [ref=e12]:
        - text: "Active:"
        - strong [ref=e13]: General Workspace
      - paragraph [ref=e14]:
        - text: "Thread:"
        - code [ref=e15]: thread-3980675c-…
      - generic [ref=e17] [cursor=pointer]:
        - generic [ref=e18]: G
        - generic "General Workspace" [ref=e19]
    - generic [ref=e20]:
      - generic [ref=e21]:
        - heading "Chats" [level=2] [ref=e22]
        - button "+ New" [ref=e23] [cursor=pointer]
      - paragraph [ref=e25]: No chats yet. Start a new conversation.
    - generic [ref=e26]:
      - generic [ref=e27]:
        - heading "Knowledge" [level=3] [ref=e28]
        - button "Refresh" [ref=e29] [cursor=pointer]
      - paragraph [ref=e30]: Failed to load knowledge files
  - main [ref=e31]:
    - heading "Owlynn" [level=1] [ref=e34]: Owlynn
    - generic [ref=e38]:
      - generic [ref=e39]: 💬
      - paragraph [ref=e40]: Start a conversation with Owlynn
      - generic [ref=e41]:
        - button "What can you help me with?" [disabled] [ref=e42]
        - button "Explain how this workspace works" [disabled] [ref=e43]
        - button "Run a quick system check" [disabled] [ref=e44]
    - generic [ref=e45]:
      - button "🤖 Owlynn General Workspace Assistant ▼" [disabled] [ref=e47] [cursor=pointer]:
        - generic [ref=e48]: 🤖
        - generic [ref=e49]: Owlynn
        - generic [ref=e50]: General Workspace Assistant
        - generic [ref=e51]: ▼
      - generic [ref=e52]:
        - textbox "Ask Owlynn..." [disabled] [ref=e54]
        - button "↑" [disabled] [ref=e55]
  - complementary [ref=e56]:
    - generic [ref=e58]:
      - heading "Inspector" [level=2] [ref=e59]
      - generic [ref=e60]:
        - button "⊟" [ref=e61] [cursor=pointer]
        - generic [ref=e64]: disconnected
    - generic [ref=e65]:
      - generic [ref=e66] [cursor=pointer]:
        - heading "⚙ Orchestration" [level=3] [ref=e67]
        - generic [ref=e69]: ▶
      - paragraph [ref=e71]: No routing information yet.
    - generic [ref=e72]:
      - generic [ref=e73] [cursor=pointer]:
        - heading "🧠 Memory & Context" [level=3] [ref=e74]
        - generic [ref=e76]: ▶
      - generic [ref=e78]:
        - generic [ref=e79]:
          - paragraph [ref=e80]: Failed to load memory data. Is the backend running?
          - button "Retry" [ref=e81] [cursor=pointer]
        - generic [ref=e83]:
          - generic [ref=e84]: Long-Term Memories
          - button "Show" [ref=e85] [cursor=pointer]
        - generic [ref=e87]:
          - generic [ref=e88]: Prompt Context
          - button "Show" [ref=e89] [cursor=pointer]
    - generic [ref=e90]:
      - generic [ref=e91] [cursor=pointer]:
        - heading "🛡 Safe Mode" [level=3] [ref=e92]
        - generic [ref=e94]: ▶
      - generic [ref=e96]:
        - generic [ref=e97]:
          - text: Active mode
          - combobox "Active mode" [ref=e98]:
            - option "Normal" [selected]
            - option "Read-only"
            - option "Confirmed Exec"
            - option "Isolated"
        - generic [ref=e99]:
          - text: Execution policy
          - combobox "Execution policy" [ref=e100]:
            - option "Auto-approve" [selected]
            - option "Manual approval (HITL)"
        - paragraph [ref=e101]: All tools allowed
    - generic [ref=e102]:
      - generic [ref=e103] [cursor=pointer]:
        - heading "🖥 Screen Assist" [level=3] [ref=e104]
        - generic [ref=e106]: ▶
      - generic [ref=e108]:
        - generic [ref=e109]:
          - text: Source
          - combobox "Source" [ref=e110]:
            - option "Screen" [selected]
            - option "Window"
            - option "Region"
        - generic [ref=e111]:
          - button "Capture" [ref=e112] [cursor=pointer]
          - button "Preview" [ref=e113] [cursor=pointer]
          - button "Annotate" [ref=e114] [cursor=pointer]
          - button "Stop" [ref=e115] [cursor=pointer]
        - paragraph [ref=e116]: "Mode: Off · screen"
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
  11 |   });
  12 | 
  13 |   test.afterAll(async () => {
  14 |     await electronApp.close();
  15 |   });
  16 | 
  17 |   test('toggle safemode changes UI state', async () => {
  18 |     // Open Safe Mode section first
> 19 |     await page.getByText('Safe Mode', { exact: true }).click();
     |                                                        ^ TimeoutError: locator.click: Timeout 30000ms exceeded.
  20 | 
  21 |     // Locate the safemode toggle on the sidebar
  22 |     const safemodeToggle = page.locator('[data-testid="safemode-toggle"]');
  23 |     
  24 |     // Ensure it exists
  25 |     await expect(safemodeToggle).toBeVisible();
  26 | 
  27 |     // Initial state should be normal
  28 |     await expect(safemodeToggle).toHaveValue('normal');
  29 | 
  30 |     // Select safe mode
  31 |     await safemodeToggle.selectOption('safe_readonly');
  32 | 
  33 |     // Verify UI reflects safemode (e.g., operator note displays the change)
  34 |     await expect(page.locator('.operator-note')).toContainText('Safe Mode set to safe_readonly');
  35 | 
  36 |     // Revert to disable safemode
  37 |     await safemodeToggle.selectOption('normal');
  38 |   });
  39 | });
  40 | 
```