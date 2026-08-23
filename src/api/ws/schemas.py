from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

# ==========================================
# Client Events (Frontend -> Python Backend)
# ==========================================


class UserMessageEvent(BaseModel):
    type: Literal["user.message"] = "user.message"
    correlation_id: str | None = None
    id: str
    content: str
    message: str | None = None
    files: list[dict[str, str]] | None = None
    project_id: str | None = None
    persona_id: str | None = None
    source: Literal["text", "voice"] | None = None


class StopClientEvent(BaseModel):
    type: Literal["stop"] = "stop"


class SecurityApprovalClientEvent(BaseModel):
    type: Literal["security_approval"] = "security_approval"
    approved: bool
    correlation_id: str | None = None


class AskUserResponseClientEvent(BaseModel):
    type: Literal["ask_user_response"] = "ask_user_response"
    answer: dict[str, Any]
    correlation_id: str | None = None


class PlanReviewResponseClientEvent(BaseModel):
    type: Literal["plan_review_response"] = "plan_review_response"
    approved: bool
    feedback: str | None = None
    correlation_id: str | None = None


class PentestTerminalStartClientEvent(BaseModel):
    type: Literal["pentest.terminal_start"] = "pentest.terminal_start"


class PentestTerminalStopClientEvent(BaseModel):
    type: Literal["pentest.terminal_stop"] = "pentest.terminal_stop"


ClientEvent = Annotated[
    UserMessageEvent
    | StopClientEvent
    | SecurityApprovalClientEvent
    | AskUserResponseClientEvent
    | PlanReviewResponseClientEvent
    | PentestTerminalStartClientEvent
    | PentestTerminalStopClientEvent,
    Field(discriminator="type"),
]

ClientEventAdapter = TypeAdapter(ClientEvent)

# ==========================================
# Server Events (Python Backend -> Frontend)
# ==========================================


class AssistantMessagePayload(BaseModel):
    id: str | None = None
    type: str | None = None
    content: str | None = None
    tool_calls: list[Any] | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    model_used: str | None = None
    token_usage: dict[str, Any] | None = None


class AssistantMessageEvent(BaseModel):
    type: Literal["assistant.message"] = "assistant.message"
    id: str | None = None
    content: str | None = None
    message: AssistantMessagePayload | None = None


class ChunkEvent(BaseModel):
    type: Literal["chunk"] = "chunk"
    content: str


class StatusEvent(BaseModel):
    type: Literal["status"] = "status"
    content: str


class VoiceStateEvent(BaseModel):
    type: Literal["voice.state"] = "voice.state"
    state: Literal[
        "idle",
        "recording",
        "transcribing",
        "speaking",
        "interrupted",
        "approval_pending",
    ]


class VoiceTranscriptEvent(BaseModel):
    type: Literal["voice.transcript"] = "voice.transcript"
    text: str
    is_final: bool
    confidence: float | None = None


class VoiceWakeWordEvent(BaseModel):
    type: Literal["voice.wake_word"] = "voice.wake_word"
    phrase: str
    confidence: float | None = None


class VoiceErrorEvent(BaseModel):
    type: Literal["voice.error"] = "voice.error"
    message: str
    code: str | None = None


class VoiceTtsStateEvent(BaseModel):
    type: Literal["voice.tts_state"] = "voice.tts_state"
    speaking: bool
    utterance_id: str | None = None


class VoiceStartedEvent(BaseModel):
    type: Literal["voice.started"] = "voice.started"
    mode: Literal["wake_word", "ptt"]


class SafeModeChangedEvent(BaseModel):
    type: Literal["safe_mode.changed"] = "safe_mode.changed"
    mode: Literal["normal", "safe_readonly", "safe_confirmed_exec", "safe_isolated"]


class EcoModeChangedEvent(BaseModel):
    type: Literal["eco_mode_changed"] = "eco_mode_changed"
    isEcoMode: bool


class ScreenAssistStateEvent(BaseModel):
    type: Literal["screen_assist.state"] = "screen_assist.state"
    mode: Literal["off", "preview", "annotating"]
    source: Literal["screen", "window", "region"]
    preview_path: str | None = None


class ActionProposalPayload(BaseModel):
    id: str
    summary: str
    source: Literal["screen_assist", "voice", "system"]
    created_at: int
    status: Literal["pending", "approved", "rejected"]


class ActionProposalEvent(BaseModel):
    type: Literal["action.proposal"] = "action.proposal"
    proposal: ActionProposalPayload


class ActionProposalResultEvent(BaseModel):
    type: Literal["action.proposal.result"] = "action.proposal.result"
    id: str
    status: Literal["approved", "rejected"]


class InterruptPayload(BaseModel):
    type: str | None = None
    risk_label: str | None = None
    risk_confidence: float | None = None
    risk_rationale: str | None = None
    remediation_hint: str | None = None
    tool_name: str | None = None
    tool_args: str | None = None


class InterruptEvent(BaseModel):
    type: Literal["interrupt"] = "interrupt"
    interrupts: list[InterruptPayload | dict[str, Any] | Any]


class ChartArtifact(BaseModel):
    filename: str
    url: str
    kind: Literal["interactive", "static"]
    mime_type: str


class ToolExecutionEvent(BaseModel):
    type: Literal["tool_execution"] = "tool_execution"
    status: Literal["running", "success", "error"]
    tool_name: str
    tool_call_id: str | None = None
    input: str | None = None
    output: str | None = None
    error: str | None = None
    risk_label: str | None = None
    risk_confidence: float | None = None
    risk_rationale: str | None = None
    remediation_hint: str | None = None
    duration: float | None = None
    chart_artifact: ChartArtifact | None = None


class RouterInfoEvent(BaseModel):
    type: Literal["router_info"] = "router_info"
    metadata: dict[str, Any]


class FallbackChainItem(BaseModel):
    model: str
    status: str
    reason: str | None = None
    duration_ms: int | None = None


class ModelInfoEvent(BaseModel):
    type: Literal["model_info"] = "model_info"
    model: str
    model_used: str | None = None
    swapping: bool | None = None
    token_usage: dict[str, Any] | None = None
    fallback_chain: list[FallbackChainItem] | None = None


class CloudUsageEvent(BaseModel):
    type: Literal["cloud_usage"] = "cloud_usage"
    turn: dict[str, Any] | None = None
    session: dict[str, Any] | None = None
    budget: dict[str, Any] | None = None
    warning_thresholds: list[float] | None = None


class CloudBudgetWarningEvent(BaseModel):
    type: Literal["cloud_budget_warning"] = "cloud_budget_warning"
    threshold: float
    used_pct: float
    used_tokens: int
    daily_token_limit: int
    estimated_cost_usd: float | None = None


class ContextSummarizedEvent(BaseModel):
    type: Literal["context_summarized"] = "context_summarized"
    summary: str
    takeaways: list[str]
    messages_compressed: int
    tokens_freed: int


class MemoryUpdatedEvent(BaseModel):
    type: Literal["memory_updated"] = "memory_updated"
    thread_id: str | None = None


class FileStatusEvent(BaseModel):
    type: Literal["file_status"] = "file_status"
    name: str | None = None
    status: str | None = None
    chunks: int | None = None
    error: str | None = None


class BrowserPageContextEvent(BaseModel):
    type: Literal["browser.page_context"] = "browser.page_context"
    url: str | None = None
    title: str | None = None
    text: str | None = None
    selection: str | None = None
    intent: str | None = None


class CoherenceRetryStartedEvent(BaseModel):
    type: Literal["coherence_retry_started"] = "coherence_retry_started"
    attempt: int | None = None
    original_confidence: float | None = None


class CoherenceRetryCompletedEvent(BaseModel):
    type: Literal["coherence_retry_completed"] = "coherence_retry_completed"


class ResponseCoherenceEvent(BaseModel):
    type: Literal["response_coherence"] = "response_coherence"
    coherent: bool
    confidence: float
    duration_ms: int
    reason: str | None = None
    correlation_id: str | None = None


class CloudFallbackEvent(BaseModel):
    type: Literal["cloud_fallback"] = "cloud_fallback"
    reason: str
    fallback_model: str
    can_retry: bool = True
    correlation_id: str | None = None


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    content: str
    correlation_id: str | None = None


class PentestTerminalChunkEvent(BaseModel):
    type: Literal["pentest.terminal"] = "pentest.terminal"
    data: str
    snapshot: str | None = None
    window: str = "main"


class PentestTerminalStatusEvent(BaseModel):
    type: Literal["pentest.terminal_status"] = "pentest.terminal_status"
    connected: bool
    host: str = ""
    session: str = ""


ServerEvent = Annotated[
    AssistantMessageEvent
    | ChunkEvent
    | StatusEvent
    | VoiceStateEvent
    | VoiceTranscriptEvent
    | VoiceWakeWordEvent
    | VoiceErrorEvent
    | VoiceTtsStateEvent
    | VoiceStartedEvent
    | SafeModeChangedEvent
    | EcoModeChangedEvent
    | ScreenAssistStateEvent
    | ActionProposalEvent
    | ActionProposalResultEvent
    | InterruptEvent
    | ToolExecutionEvent
    | RouterInfoEvent
    | ModelInfoEvent
    | CloudUsageEvent
    | CloudBudgetWarningEvent
    | ContextSummarizedEvent
    | MemoryUpdatedEvent
    | FileStatusEvent
    | BrowserPageContextEvent
    | CoherenceRetryStartedEvent
    | CoherenceRetryCompletedEvent
    | ResponseCoherenceEvent
    | CloudFallbackEvent
    | ErrorEvent
    | PentestTerminalChunkEvent
    | PentestTerminalStatusEvent,
    Field(discriminator="type"),
]

ServerEventAdapter = TypeAdapter(ServerEvent)
