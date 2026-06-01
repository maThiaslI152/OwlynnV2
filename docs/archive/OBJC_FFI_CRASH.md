---
status: archived
category: archive
last_updated: 2026-05-31
owner: human
---

# ObjC FFI Non-Null-Terminated C String Crash Analysis

## Date of incident
2026-04-24

## Versions affected
First real Live Talk commit that replaced the simulation placeholder with ObjC FFI calls.

## Symptom

After granting microphone and speech recognition permissions in System Settings, enabling the
wake-word or push-to-talk button caused a **deterministic crash** of the Tauri app process
within ~1–3 seconds. The crash report (`.ips` file in `~/Library/Logs/DiagnosticReports/`)
contained:

- **Exception type:** `EXC_BAD_ACCESS (SIGBUS)` — not a typical null pointer; this is a
  **bus error** on an invalid address.
- **Crash address:** `0x53552d6e80` — a fixed GPU carveout address in the kernel
  (`KERN_PROTECTION_FAILURE`).
- **Crashing library:** `com.apple.WebKit` → `WKContentWorld` → `_CFRelease` → `_xzm_free`.
- **Thread:** com.apple.WebKit:com.apple.WebKit.GPU (com.apple.CoreAnimation`CA::Render::`).

This pointed to a WebKit GPU compositing crash in CoreAnimation's memory allocator
(`_xzm_free`), where it was trying to `CFRelease` an object at a GPU-protected address.
The crash was **deterministic** — same address (`0x53552d6e80`) every time — and occurred
when WebKit tried to re-render the UI after a button click.

## Root cause

Four call sites in `src-tauri/src/voice/mod.rs` were unsafe. Two of them used
`NSString::stringWithUTF8String:` with raw Rust string pointers, and one passed a raw C string
to an API that expects an Objective-C `NSString *`.

### Call site 1 (line ~288): NSLocale identifier
```rust
let locale: *mut Object = msg_send![class!(NSLocale), localeWithLocaleIdentifier:
    "en-US\0".as_ptr() as *const i8];
```

This call is **not safe**, even though `"en-US\0"` is null-terminated. The issue is type
mismatch: `localeWithLocaleIdentifier:` expects an `NSString *`, but the code passes a
`const char *`. At runtime, Foundation bridges this argument as an Objective-C object and
attempts `objc_retain` on bytes that are not an ObjC object, causing the deterministic
`SIGBUS` crash at `0x53552d6e80`.

### Call site 2 (line ~340): Wake-phrase constrained string
```rust
let ns_phrase: *mut Object = msg_send![class!(NSString), stringWithUTF8String:
    wake_phrase.as_ptr() as *const i8];
```

`wake_phrase` is a Rust `&str` — a fat pointer `(pointer, length)`. The `as_ptr()` returns
the raw `*const u8` pointer to the slice data, but **Rust `&str` is NOT guaranteed to be
null-terminated**. If the wake phrase was provided from a `String` whose internal buffer
does not have a trailing `\0` past its length, or from a substring slice, `stringWithUTF8String:`
would read past the valid memory into adjacent heap data looking for a `\0` byte.

### Call site 3 (line ~665): TTS text
```rust
let ns_string: *mut Object = msg_send![class!(NSString), stringWithUTF8String:
    text.as_ptr() as *const i8];
```

`text` is a `&str` — same problem as site 2.

### How the corruption works

`NSString::stringWithUTF8String:` expects a **null-terminated C string** (`const char *`).
It scans forward byte-by-byte until it finds `\0`, then allocates an `NSString` from that
data. When given a pointer into a Rust `&str` that is not null-terminated:

1. The method reads past the logical end of the string into adjacent heap memory.
2. If that adjacent memory contains other ObjC object data (class pointers, isa pointers,
   string interning tables), the scan reads corrupted/mixed data.
3. The resulting `NSString` wraps an incorrect length or garbage bytes.
4. When that `NSString` is later processed (e.g. by `SFSpeechRecognizer` or `NSSpeechSynthesizer`),
   the ObjC runtime encounters an invalid object and behaves unpredictably.
5. In this specific case, the corruption hit Cocoa's internal string cache/table, which
   shares memory with CoreFoundation's `CFRelease` path, ultimately walking into a
   GPU-protected page mapped by WebKit's `WKContentWorld`.

### Why the crash appeared in WebKit, not in the audio code

This is the most confusing aspect of the bug. Because `stringWithUTF8String:` reads past
the buffer boundary **at call time**, the heap corruption is planted early (during FFI setup).
The crash surfaces later (during the next UI re-render) when WebKit touches the corrupted
heap area. The corrupt data at `0x53552d6e80` is a GPU carveout — WebKit's compositing
layer maps it, `_xzm_free` tries to release what it thinks is a valid CF object, but the
address falls in a kernel-protected GPU memory region.

This is why the initial debugging focused on `transparent: true` window settings (another
WebKit GPU compositing trigger) — the crash **looked** like a WebKit rendering bug, but
was actually a delayed consequence of ObjC heap corruption planted by the FFI calls earlier
in the session.

## Fix

The voice module was refactored to use `cocoa::foundation` typed APIs for Objective-C strings
and arrays:

- `NSString::alloc(nil).init_str(...)` for Rust -> NSString conversion (length-bounded, no
  C-string scanning).
- `NSArray::arrayWithObject(nil, ...)` for constrained phrase arrays.
- `localeWithLocaleIdentifier:` now receives a real `NSString *`, not a `const char *`.

### Before (bad type for NSLocale)
```rust
let locale: *mut Object = msg_send![class!(NSLocale), localeWithLocaleIdentifier:
    "en-US\0".as_ptr() as *const i8];
```

### After (correct NSString object)
```rust
let locale_id: id = NSString::alloc(nil).init_str("en-US");
let locale: *mut Object = msg_send![class!(NSLocale), localeWithLocaleIdentifier: locale_id];
```

## Files changed

- `src-tauri/src/voice/mod.rs` — NSLocale identifier conversion, wake phrase conversion,
  and TTS text conversion.

## Verification

1. `cargo build` passes with no warnings about the change.
2. `tauri build --debug` produces an `.app` bundle.
3. After granting permissions and enabling wake-word, the app no longer crashes.
4. Wake-word and push-to-talk both function correctly (real `SFSpeechRecognizer` transcription).

## Prevention

For any future Rust -> ObjC FFI code that passes text:

| API | Safe pattern |
|-----|-------------|
| `stringWithUTF8String:` | Prefer `NSString::alloc(nil).init_str(...)` to avoid C-string scanning |
| `localeWithLocaleIdentifier:` | Always pass an `NSString *` (e.g. `NSString::alloc(nil).init_str(...)`) |
| `performSelector:withObject:` | No C string involved (uses ObjC selector + id) |
| `objc_setAssociatedObject` | No C string involved |
| `NSSelectorFromString` | Pass via `NSString` created with `init_str(...)` |

**Rule of thumb:** If an ObjC API signature takes `NSString *`, `NSArray *`, or
`NSDictionary *`, never pass raw C pointers (`*const i8`) even if they are null-terminated.
Convert to ObjC objects first.

## Second incident (2026-04-24)

After the first fix, repeated wake-word toggles still crashed immediately after permissions
were granted. Crash reports confirmed the fault moved to the NSLocale callsite:

- `objc_retain`
- `String._unconditionallyBridgeFromObjectiveC(_:)`
- `+[NSLocale localeWithLocaleIdentifier:]`

This incident confirmed the remaining bug was argument type mismatch (`const char *` passed to
an API expecting `NSString *`), not null termination.

## Related issues

- **`transparent: true` window crash:** On macOS Sequoia 26.4, `transparent: true` +
  `titleBarStyle: "Overlay"` + `hiddenTitle: true` triggers a separate WebKit GPU compositing
  crash. This is a distinct bug with the same crash address (`0x53552d6e80`), suggesting
  both issues stress the same GPU carveout path in CoreAnimation. The workaround is to use
  `transparent: false` with `decorations: true` and a solid dark CSS background.
- **TCC permission reset on dev builds:** `cargo tauri dev` runs the binary directly
  without an `.app` wrapper, so macOS TCC cannot find `Info.plist`. Permissions must be
  re-granted each time the binary hash changes. Workaround: build a debug `.app` bundle
  via `tauri build --debug` and launch via `open` — permissions persist across launches
  of the same bundle.

## Last updated

2026-05-31 — `docs-standards-timeline` added frontmatter
