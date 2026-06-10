# Owlynn Status (eval fixture)

### Architectural Concerns

| Concern | Impact | Status |
|---------|--------|--------|
| Electron IPC for Screen Assist / TTS | Screen Assist and TTS require Electron main process; no browser fallback | Open — by design for desktop-only features |
| Safe Mode in browser | REST fallback via electronBridge.ts when IPC unavailable | Mitigated (BUG-5 fixed) |
| Silent error handling | Some try/catch blocks swallow errors (profile updates, API calls) | Open — partial mitigation in BUG-3/BUG-4 |
| Memory/Orchestration loading UX | Panels could hang without feedback | Mitigated (BUG-2, BUG-3 fixed — error/empty states) |
| Tool panel stale data | Mock or stale execution entries after disconnect | Mitigated (BUG-6 fixed) |
