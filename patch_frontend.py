import re

with open("frontend-v2/src/App.tsx", "r") as f:
    content = f.read()

# 1. Update onEvent logic
on_event_orig = "      onEvent: (event: ServerEvent) => {"
on_event_new = """      onEvent: (event: ServerEvent) => {
        const storeState = useAppStore.getState()
        const pendingId = storeState.pendingCorrelationId
        const eventId = (event as any).correlation_id

        if (eventId && pendingId && eventId !== pendingId) {
            console.debug("Ignoring mismatched correlation id", eventId)
            return
        }

        if (event.type === 'status' && (event as any).content === 'idle') {
            if (pendingId && eventId === pendingId) {
                useAppStore.setState({ pendingCorrelationId: null })
            }
        }
"""
content = content.replace(on_event_orig, on_event_new)

# 2. Add setPendingCorrelationId to useAppStore hook
content = content.replace(
    "const addMessage = useAppStore((s) => s.addMessage)",
    "const addMessage = useAppStore((s) => s.addMessage)\n  const setPendingCorrelationId = useAppStore((s) => s.setPendingCorrelationId)"
)

# 3. Add to dependencies of useEffect for wsClient
content = content.replace(
    "setConnection, setLatestToolExecution",
    "setConnection, setLatestToolExecution, setPendingCorrelationId"
)

# 4. In onClose, clear pendingCorrelationId
content = content.replace(
    "setLatestToolExecution(null)\n      },",
    "setLatestToolExecution(null)\n        setPendingCorrelationId(null)\n      },"
)

# 5. handleSend
content = content.replace(
    "addMessage(message)\n    wsClientRef.current?.send({",
    "addMessage(message)\n    setPendingCorrelationId(message.id)\n    wsClientRef.current?.send({\n      correlation_id: message.id,"
)

# 6. handleHitlApprove
content = content.replace(
    "wsClientRef.current?.send({ type: 'security_approval', approved: true })",
    "const corrId = crypto.randomUUID()\n      setPendingCorrelationId(corrId)\n      wsClientRef.current?.send({ type: 'security_approval', approved: true, correlation_id: corrId })"
)
content = content.replace(
    "wsClientRef.current?.send({ type: 'plan_review_response', approved: true })",
    "const corrId = crypto.randomUUID()\n      setPendingCorrelationId(corrId)\n      wsClientRef.current?.send({ type: 'plan_review_response', approved: true, correlation_id: corrId })"
)
content = content.replace(
    "wsClientRef.current?.send({\n        type: 'ask_user_response',\n        answer: answers || { skipped: false },\n      })",
    "const corrId = crypto.randomUUID()\n      setPendingCorrelationId(corrId)\n      wsClientRef.current?.send({\n        type: 'ask_user_response',\n        answer: answers || { skipped: false },\n        correlation_id: corrId,\n      })"
)

# 7. handleHitlDecline
content = content.replace(
    "wsClientRef.current?.send({ type: 'security_approval', approved: false })",
    "const corrId = crypto.randomUUID()\n    setPendingCorrelationId(corrId)\n    wsClientRef.current?.send({ type: 'security_approval', approved: false, correlation_id: corrId })"
)

# 8. handleHitlSelectChoice
content = content.replace(
    "wsClientRef.current?.send({\n      type: 'ask_user_response',\n      answer: answer,\n    })",
    "const corrId = crypto.randomUUID()\n    setPendingCorrelationId(corrId)\n    wsClientRef.current?.send({\n      type: 'ask_user_response',\n      answer: answer,\n      correlation_id: corrId,\n    })"
)

# 9. handleHitlSkip
content = content.replace(
    "wsClientRef.current?.send({\n      type: 'ask_user_response',\n      answer: { skipped: true },\n    })",
    "const corrId = crypto.randomUUID()\n    setPendingCorrelationId(corrId)\n    wsClientRef.current?.send({\n      type: 'ask_user_response',\n      answer: { skipped: true },\n      correlation_id: corrId,\n    })"
)

with open("frontend-v2/src/App.tsx", "w") as f:
    f.write(content)

# AppShell.tsx update
with open("frontend-v2/src/components/AppShell.tsx", "r") as f:
    appshell = f.read()

appshell = appshell.replace(
    "const connectionState = useAppStore((s) => s.connectionState)",
    "const connectionState = useAppStore((s) => s.connectionState)\n  const pendingCorrelationId = useAppStore((s) => s.pendingCorrelationId)"
)
appshell = appshell.replace(
    "<Composer onSend={onSend} disabled={connectionState !== 'connected'} hitlBlocked={hasPendingHitl} compact={isCompact} />",
    "<Composer onSend={onSend} disabled={connectionState !== 'connected' || !!pendingCorrelationId} hitlBlocked={hasPendingHitl} compact={isCompact} />"
)

with open("frontend-v2/src/components/AppShell.tsx", "w") as f:
    f.write(appshell)

