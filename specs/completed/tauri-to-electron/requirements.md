# Requirements: Tauri to Electron Migration

> **Purpose:** Define what the change must do. Written in Plan mode before design. Must be approved via AskQuestion `requirements-review` popup before proceeding to design.

## User Stories

| ID | As a ... | I want to ... | So that ... |
|----|----------|---------------|-------------|
| US-1 | User | run the OwlynnV2 application as a standalone desktop app | I can interact with the AI without needing a separate browser window |
| US-2 | Developer | build and package the app using `electron-builder` and `vite-plugin-electron` | the unified TypeScript/Node.js ecosystem speeds up development |
| US-3 | User | hear the AI speak using native browser Web Speech API | there is no reliance on macOS-specific `say` commands and the app can be more easily ported to other OSs |
| US-4 | User | have the AI take screen previews for Screen Assist | the agent can see my screen context |
| US-5 | Developer | maintain the exact frontend IPC bridge signature | React components don't need to be rewritten |

## Acceptance Criteria (EARS format)

> EARS = Easy Approach to Requirements Syntax: "When {condition}, the system shall {behavior}".

| ID | Criterion |
|----|-----------|
| AC-1 | When the application is launched, the system shall spawn an Electron window rendering the Vite React frontend. |
| AC-2 | When a React component calls `electronBridge.speakText()`, the system shall invoke the native Chromium Web Speech API to synthesize the text. |
| AC-3 | When a React component calls `electronBridge.startScreenPreview()`, the system shall use an Electron-native mechanism or Node.js `child_process` to capture a screenshot and return the path. |
| AC-4 | When a React component calls `electronBridge.setWindowSize()`, the system shall resize the Electron main window bounds accordingly. |
| AC-5 | When the application is packaged, the system shall use `electron-builder` to generate a valid macOS `.app` bundle. |

## Non-Functional Requirements

| ID | Category | Requirement |
|----|----------|-------------|
| NFR-1 | Compatibility | The frontend IPC bridge (`tauriBridge.ts` -> `electronBridge.ts`) must maintain 100% type compatibility with the existing `BridgeResult<T>` signature. |
| NFR-2 | Performance | The Electron app must cleanly start and connect to the Python backend without timing out. |

## Edge Cases and Error States

- What happens when Screen Capture fails? The `BridgeResult` must return `ok: false` with the error string, identical to the Tauri implementation.
- What happens when TTS is not supported? The `electronBridge` should gracefully return an error if `window.speechSynthesis` fails.

## Out of Scope

- Removing the Python backend (server.py)
- Changing the React UI components

## Dependencies

- Node.js > 18
- `electron`, `electron-builder`, `vite-plugin-electron`

## References

- Implementation Plan (Tauri -> Electron Migration)

## Approval

- `requirements-review` AskQuestion: approved
