import re

# 1. Update protocol.ts
with open("frontend-v2/src/types/protocol.ts", "r") as f:
    content = f.read()

content = content.replace(
    "export interface UserMessageEvent {\n  type: 'user.message'\n  id: string",
    "export interface UserMessageEvent {\n  type: 'user.message'\n  correlation_id?: string\n  id: string"
)

content = content.replace(
    "export interface SecurityApprovalClientEvent {\n  type: 'security_approval'\n  approved: boolean\n}",
    "export interface SecurityApprovalClientEvent {\n  type: 'security_approval'\n  approved: boolean\n  correlation_id?: string\n}"
)

content = content.replace(
    "export interface AskUserResponseClientEvent {\n  type: 'ask_user_response'\n  answer: Record<string, unknown>\n}",
    "export interface AskUserResponseClientEvent {\n  type: 'ask_user_response'\n  answer: Record<string, unknown>\n  correlation_id?: string\n}"
)

content = content.replace(
    "export interface PlanReviewResponseClientEvent {\n  type: 'plan_review_response'\n  approved: boolean\n  feedback?: string\n}",
    "export interface PlanReviewResponseClientEvent {\n  type: 'plan_review_response'\n  approved: boolean\n  feedback?: string\n  correlation_id?: string\n}"
)

with open("frontend-v2/src/types/protocol.ts", "w") as f:
    f.write(content)

# 2. Fix useAppStore.ts duplication
with open("frontend-v2/src/state/useAppStore.ts", "r") as f:
    store = f.read()

store = store.replace(
    "  activePersonaId: 'default',\n  pendingCorrelationId: null,\n",
    "  activePersonaId: 'default',\n"
)

with open("frontend-v2/src/state/useAppStore.ts", "w") as f:
    f.write(store)

