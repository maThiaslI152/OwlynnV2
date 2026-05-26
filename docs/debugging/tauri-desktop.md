---
purpose: "Debugging guide for the Tauri desktop shell: window issues, TTS, screen capture, IPC bridge, and CSP/permission errors."
---

# Debugging: Tauri Desktop Shell

**Quick Reference:** Tauri v2.10 desktop shell for macOS. Handles window vibrancy, screen capture, TTS (`say`), and CSP enforcement. Key files: `src-tauri/src/main.rs`, `src-tauri/src/voice/mod.rs`, `src-tauri/Cargo.toml`, `src-tauri/tauri.conf.json`.

## Common Failure Modes

| Symptom | Likely Cause | Diagnostic | Fix |
|---------|-------------|-----------|-----|
| `.app` bundle won't launch | Code signing, quarantine, or missing resources | `open -a "path/to/app.app"`, check Console.app | Remove quarantine: `xattr -dr com.apple.quarantine <app>.app` |
| `cargo tauri dev` has no TCC permissions | Bare binary, no `.app` wrapper | macOS TCC requires Info.plist in `.app` bundle | Use debug `.app` bundle: `cargo tauri build --debug` then `open` |
| CSP violation errors in console | Inline scripts, external resources blocked | Browser DevTools Console | Update `tauri.conf.json` CSP or move inline code to files |
| Safe Mode dropdown error (BUG-5) | Tauri IPC unavailable in browser-only mode | Browser Console: `Cannot read properties of undefined (reading 'invoke')` | Use REST API fallback for browser mode: `PUT /api/unified-settings` |
| Screen capture fails | TCC permission not granted or Tauri IPC missing | Check macOS System Settings → Privacy → Screen Recording | Grant permission, restart app |
| TTS (`say`) not working | macOS `say` command not available or permission issue | `say "test"` in terminal | Check macOS Speech settings |
| Window vibrancy / transparency broken | `transparent: true` in tauri.conf.json | Check `src-tauri/tauri.conf.json` `transparent` field | Known fix: set to `true` (restored 2026-04-24) |
| Rust build fails | Missing macOS SDK, wrong Cargo deps, or Xcode CLI | `cargo build 2>&1` | Install Xcode CLI: `xcode-select --install` |
| `window.__TAURI__` undefined in browser | Running in browser, not inside Tauri webview | Check if `window.__TAURI__` exists in DevTools Console | Use REST API fallbacks for browser-only features |
| Tauri IPC `invoke` fails | Command not registered in Rust backend | Check `src-tauri/src/main.rs` for `#[tauri::command]` | Register the missing command |

## Diagnostic Commands

### App Bundle Verification

```bash
# Check if the debug .app bundle exists
ls -la src-tauri/target/debug/bundle/macos/*.app 2>/dev/null

# Check code signing status
codesign -dv --verbose=4 src-tauri/target/debug/bundle/macos/*.app 2>/dev/null

# Check quarantine attributes
xattr -l src-tauri/target/debug/bundle/macos/*.app 2>/dev/null

# Remove quarantine (if blocked by Gatekeeper)
xattr -dr com.apple.quarantine src-tauri/target/debug/bundle/macos/*.app

# Check security assessment
spctl --assess --verbose src-tauri/target/debug/bundle/macos/*.app 2>&1
```

### Rust Build

```bash
# Check Rust toolchain
rustc --version
cargo --version

# Check macOS SDK
xcrun --show-sdk-path

# Build Tauri app
cd src-tauri && cargo build 2>&1 | tail -20

# Build debug .app bundle
cargo tauri build --debug 2>&1 | tail -20

# Check for Rust dependency issues
cd src-tauri && cargo check 2>&1 | tail -20
```

### TCC / Permissions

```bash
# Check TCC database (requires Full Disk Access)
# Screen Recording permissions
sudo sqlite3 /Library/Application\ Support/com.apple.TCC/TCC.db \
  "SELECT service,client,auth_value FROM access WHERE service='kTCCServiceScreenCapture'" 2>/dev/null

# Check accessibility permissions
sudo sqlite3 /Library/Application\ Support/com.apple.TCC/TCC.db \
  "SELECT service,client,auth_value FROM access WHERE service='kTCCServiceAccessibility'" 2>/dev/null

# Check microphone permissions
sudo sqlite3 /Library/Application\ Support/com.apple.TCC/TCC.db \
  "SELECT service,client,auth_value FROM access WHERE service='kTCCServiceMicrophone'" 2>/dev/null
```

### TTS Test

```bash
# Test macOS TTS directly
say "Hello, this is a test"

# List available voices
say -v '?' | head -20

# Check if say is working
which say
```

### CSP / Console Errors

Open the app and check browser DevTools Console (if running in browser mode for dev) or `Console.app` (for Tauri webview).

```bash
# Monitor Console.app for app-specific logs
log stream --predicate 'process == "owlynn"' --level debug 2>/dev/null

# Or check Console.app manually:
# open Console.app → search for the app process name
```

### Configuration Check

```bash
# Check Tauri config
cat src-tauri/tauri.conf.json | python3 -m json.tool 2>/dev/null || echo "Invalid JSON"

# Key fields to verify:
# - transparent: should be true
# - CSP: should allow required origins
# - permissions: should include needed capabilities
```

## Log Interpretation

### Tauri Build

```
# Successful build
   Compiling owlynn v0.1.0
    Finished release [optimized] target(s) in 45.2s

# Missing macOS SDK
error: could not find native static library `iconv`

# Missing Xcode CLI
error: linker `cc` not found
→ Fix: xcode-select --install

# Rust version too old
error: package `tauri v2.10.0` requires rustc 1.77 or newer
→ Fix: rustup update
```

### App Launch

```
# Normal launch (via open)
$ open src-tauri/target/debug/bundle/macos/owlynn.app

# Quarantine blocked
$ open src-tauri/target/debug/bundle/macos/owlynn.app
LSOpenURLsWithRole() failed with error -10810
→ Fix: xattr -dr com.apple.quarantine <app>.app

# Code signing rejected
$ open src-tauri/target/debug/bundle/macos/owlynn.app
The application cannot be opened for an unexpected reason.
→ Fix: codesign --force --deep --sign - <app>.app (ad-hoc signing)
```

### CSP Violations

```
# Console.app or DevTools Console
[Error] Refused to load the script '...' because it violates the following
Content Security Policy directive: "script-src 'self'"

# Common violations:
- Inline <script> tags → move to .js/.ts files
- External CDN resources → add to CSP whitelist
- Inline styles → use CSS files or 'unsafe-inline' (not recommended)
```

### Tauri IPC Errors

```
# In DevTools Console (browser mode)
Uncaught TypeError: Cannot read properties of undefined (reading 'invoke')
→ window.__TAURI__ is undefined — running in browser, not Tauri webview

# Tauri command not found
Error: command 'set_safe_mode' not found
→ Register the command in src-tauri/src/main.rs with #[tauri::command]
```

## Step-by-Step Procedures

### Procedure 1: App Won't Launch

1. Check if the `.app` bundle exists:
   ```bash
   ls -la src-tauri/target/debug/bundle/macos/
   ```

2. If not, build it:
   ```bash
   cargo tauri build --debug
   ```

3. Check quarantine status:
   ```bash
   xattr -l src-tauri/target/debug/bundle/macos/*.app
   ```
   If `com.apple.quarantine` is present:
   ```bash
   xattr -dr com.apple.quarantine src-tauri/target/debug/bundle/macos/*.app
   ```

4. Check code signing:
   ```bash
   codesign -dv src-tauri/target/debug/bundle/macos/*.app
   ```
   If unsigned, ad-hoc sign:
   ```bash
   codesign --force --deep --sign - src-tauri/target/debug/bundle/macos/*.app
   ```

5. Try launching:
   ```bash
   open src-tauri/target/debug/bundle/macos/*.app
   ```

6. If still fails, check Console.app for crash logs:
   - Open Console.app
   - Search for the app process name
   - Look for crash reports under "User Reports"

### Procedure 2: Tauri IPC Not Available (Browser Dev Mode)

When developing in browser-only mode (Vite dev server on port 5173), `window.__TAURI__` is not available.

1. Identify features that depend on Tauri IPC:
   - Safe Mode dropdown (BUG-5) — uses `tauriBridge.set_safe_mode()`
   - Screen Assist — uses `tauriBridge` for screen capture
   - TTS — uses Tauri runtime events
   - Window sizing — uses Tauri window API

2. For Safe Mode:
   - Use REST API fallback: `PUT /api/unified-settings` with `{"execution_policy": "auto_approve"}`
   - Or update `SafeModePanel.tsx` to detect browser mode and use REST API

3. For other features:
   - Screen capture, TTS, window sizing are Tauri-only and will not work in browser dev mode
   - These features must be tested via the `.app` bundle

### Procedure 3: CSP Violations

1. Check the CSP in `src-tauri/tauri.conf.json`:
   ```bash
   python3 -c "
   import json
   with open('src-tauri/tauri.conf.json') as f:
       conf = json.load(f)
   csp = conf.get('app',{}).get('security',{}).get('csp','NOT SET')
   print(csp)
   "
   ```

2. Common CSP fixes:
   - For loading external fonts/images: add the domain to `font-src`/`img-src`
   - For WebSocket connections: add `ws://127.0.0.1:8000` to `connect-src`
   - For inline scripts: refactor to `.ts` files instead of using `unsafe-inline`

3. Test CSP changes:
   ```bash
   # Rebuild frontend
   cd frontend-v2 && npm run build
   # Rebuild Tauri
   cd ../src-tauri && cargo tauri build --debug
   ```

### Procedure 4: Rust Build Fails

1. Verify Rust toolchain:
   ```bash
   rustc --version  # Should be >= 1.77
   rustup show
   ```

2. Verify macOS SDK:
   ```bash
   xcrun --show-sdk-path
   xcode-select -p
   ```
   If missing: `xcode-select --install`

3. Try a clean build:
   ```bash
   cd src-tauri
   cargo clean
   cargo build 2>&1 | tail -30
   ```

4. Common dependency issues:
   - `tauri v2.10.0` → check Cargo.toml for exact version
   - `cocoa` → macOS-specific crate, requires macOS SDK
   - `serde` → serialization, usually auto-resolved
   - `crossbeam` → concurrency, usually auto-resolved

## Known Fixes

- **`transparent: true` restored**: Set back to `true` in `tauri.conf.json` on 2026-04-24. The frosted-glass CSS provides a solid dark background while the window chrome is transparent. See [STATUS.md](../STATUS.md).
- **`.app` bundle required for TCC**: `cargo tauri dev` runs the binary directly without `.app` wrapper, so TCC cannot read `Info.plist`. Use `cargo tauri build --debug` and `open` the `.app` bundle instead. See [STATUS.md](../STATUS.md).
- **Obsolete Live Talk artifacts**: All wake-word, STT, and Swift helper infrastructure removed on 2026-04-29. Only `speak_text` (TTS via macOS `say`) remains. See [`../LIVE_TALK_DEFERRED.md`](../LIVE_TALK_DEFERRED.md).
- **Safe Mode browser fallback (BUG-5)**: Known issue. See [BUG-ANALYSIS.md](../BUG-ANALYSIS.md) and [frontend.md](frontend.md).
- See also: [`../TAURI_CSP_PERMISSION_AUDIT_CHECKLIST.md`](../TAURI_CSP_PERMISSION_AUDIT_CHECKLIST.md).
