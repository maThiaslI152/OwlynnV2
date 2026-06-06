# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: screen-assist.spec.ts >> Screen-Assist Feature >> triggering screen-assist displays context prompt
- Location: e2e/screen-assist.spec.ts:16:3

# Error details

```
Test timeout of 30000ms exceeded.
```

```
TimeoutError: locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for getByText('Screen Assist', { exact: true })

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
        - code [ref=e15]: thread-296896df-…
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
  3  | test.describe('Screen-Assist Feature', () => {
  4  |   let electronApp;
  5  |   let page;
  6  | 
  7  |   test.beforeAll(async () => {
  8  |     electronApp = await electron.launch({ args: ['.'] });
  9  |     page = await electronApp.firstWindow();
  10 |   });
  11 | 
  12 |   test.afterAll(async () => {
  13 |     await electronApp.close();
  14 |   });
  15 | 
  16 |   test('triggering screen-assist displays context prompt', async () => {
  17 |     // Open Screen Assist section first
> 18 |     await page.getByText('Screen Assist', { exact: true }).click();
     |                                                            ^ TimeoutError: locator.click: Timeout 30000ms exceeded.
  19 | 
  20 |     // Locate the screen assist activation button
  21 |     const screenAssistBtn = page.locator('[data-testid="screen-assist-btn"]');
  22 |     
  23 |     // Ensure the feature exists and is accessible
  24 |     await expect(screenAssistBtn).toBeVisible();
  25 | 
  26 |     // Click to activate screen-assist
  27 |     await screenAssistBtn.click();
  28 | 
  29 |     // Verify system feedback (e.g. operator note)
  30 |     await expect(page.locator('.operator-note')).toContainText('Captured screen');
  31 |   });
  32 | });
  33 | 
```