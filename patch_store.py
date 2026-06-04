import re

with open("frontend-v2/src/state/useAppStore.ts", "r") as f:
    content = f.read()

# Add pendingCorrelationId to AppState interface
content = content.replace(
    "activePersonaId: string",
    "activePersonaId: string\n  pendingCorrelationId: string | null"
)
content = content.replace(
    "setActivePersonaId: (id: string) => void",
    "setActivePersonaId: (id: string) => void\n  setPendingCorrelationId: (id: string | null) => void"
)

# Add to initial state
content = content.replace(
    "activePersonaId: 'default',",
    "activePersonaId: 'default',\n  pendingCorrelationId: null,"
)

# Add setter
content = content.replace(
    "setActivePersonaId: (activePersonaId) => set({ activePersonaId }),",
    "setActivePersonaId: (activePersonaId) => set({ activePersonaId }),\n  setPendingCorrelationId: (pendingCorrelationId) => set({ pendingCorrelationId }),"
)

# Reset in clearSession
content = content.replace(
    "inlineSecurityPrompt: null,",
    "inlineSecurityPrompt: null,\n      pendingCorrelationId: null,"
)

with open("frontend-v2/src/state/useAppStore.ts", "w") as f:
    f.write(content)
