# Mode System

Owlynn has three operational modes that change the UI, tools, and system prompt behavior.

## Overview

| Mode | Response Style | Scenario | Sidebar | Right Panel |
|------|---------------|----------|---------|-------------|
| **Normal** | User choice | Auto-detected | Standard projects/chats | Orchestration, cloud usage |
| **Study** | `learning` (forced) | `study` (forced) | Courses, exam countdown, study progress | Study progress, weak areas |
| **Pentest** | `concise` (forced) | `pentest` (forced) | Scope & constraints panel | Pentest tools, Kali VM status |

## Architecture

### Frontend

| File | Role |
|------|------|
| `frontend-v2/src/state/useAppStore.ts` | `activeMode` state + `setActiveMode` setter |
| `frontend-v2/src/components/ModeSwitcher.tsx` | Segmented toggle (Normal / Study / Pentest) |
| `frontend-v2/src/components/AppShell.tsx` | Conditional sidebar sections per mode |
| `frontend-v2/src/components/MacMenuBar.tsx` | Conditional right panel content per mode |
| `frontend-v2/src/App.tsx` | Mode → WS payload (`scenario_id` mapping) |

### Backend

| File | Role |
|------|------|
| `src/api/ws/handler.py` | Accepts `scenario_id` from WS payload, maps to response_style |
| `src/agent/routing/router.py` | Detects scenario from keywords or forced `scenario_id` |
| `src/memory/project.py` | Stores `mode` field per project in `projects.json` |

### Mode Persistence

Mode is persisted per-project in `projects.json`:

```json
{
  "id": "default",
  "name": "General Workspace",
  "mode": "study",
  ...
}
```

When switching projects, the mode auto-switches. When changing mode, it's persisted via `PUT /api/projects/{id}`.

### Mode → Backend Flow

```
User clicks "Pentest" in ModeSwitcher
  → setActiveMode('pentest') in Zustand store
  → PUT /api/projects/{id} { mode: 'pentest' }
  → handleModeChange() in App.tsx
    → POST /api/pentest/vm/start (auto-starts Kali VM)
  → Next WS message includes scenario_id: 'pentest'
  → Backend sets response_style='concise', scenario_id='pentest'
  → Router forces pentest scenario (bypasses keyword detection)
```

## Mode-Specific Behavior

### Normal Mode

- Standard project/chat management
- Router uses keyword-based scenario detection
- User chooses response style via Composer toggle
- All toolboxes available based on router classification

### Study Mode

- Auto-sets `response_style: learning`
- Forces `scenario_id: study`
- Sidebar shows: Courses, exam countdown, Study Progress panel
- Right panel shows: Study progress, weak areas, streak
- Memory uses study-specific extraction (misconception/mastery atoms)
- Router auto-adds `study` toolbox

### Pentest Mode

- Auto-sets `response_style: concise`
- Forces `scenario_id: pentest`
- Sidebar shows: Scope & Constraints panel
- Right panel shows: Pentest Tools panel (MCP servers, Kali VM, findings)
- **Always uses local model** (cloud APIs refuse security content)
- Router auto-adds `mcp` and `screen_assist` toolboxes
- Kali VM auto-starts when mode activated, auto-stops when deactivated

## Configuration

### Mode Switcher Location

The mode switcher is in the left sidebar top, rendered by `AppShell.tsx`:

```tsx
{onModeChange && (
  <div style={{ padding: '8px 10px 4px' }}>
    <ModeSwitcher activeMode={activeMode} onModeChange={onModeChange} />
  </div>
)}
```

### Mode-Specific Sidebar Sections

```tsx
{activeMode === 'study' && (
  <details className="sidebar-accordion" open>
    <summary>Study Progress</summary>
    <StudyProgressPanel />
  </details>
)}

{activeMode === 'pentest' && (
  <details className="sidebar-accordion" open>
    <summary>Scope & Constraints</summary>
    <PentestScopePanel />
  </details>
)}
```

### Mode-Specific Right Panel (MacMenuBar)

```tsx
{activeMode === 'study' && <><h4>Study Progress</h4><StudyProgressPanel /><hr /></>}
{activeMode === 'pentest' && <><h4>Pentest Tools</h4><PentestToolsPanel /><hr /></>}
```

## Adding a New Mode

1. Add mode type to `useAppStore.ts` `activeMode` union
2. Add mode to `ModeSwitcher.tsx` `modes` array
3. Add sidebar section in `AppShell.tsx`
4. Add right panel section in `MacMenuBar.tsx`
5. Add scenario mapping in `ws/handler.py`
6. Add mode-specific response_style in `App.tsx` `handleModeChange`
