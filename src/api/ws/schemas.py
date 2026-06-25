from typing import Any, Dict, List, Literal, Optional, Union, Annotated
from pydantic import BaseModel, Field, TypeAdapter

# ==========================================
# Client Events (Frontend -> Python Backend)
# ==========================================


class UserMessageEvent(BaseModel):
    type: Literal["user.message"] = "user.message"
    correlation_id: Optional[str] = None
    id: str
    content: str
    message: Optional[str] = None
    files: Optional[List[Dict[str, str]]] = None
    project_id: Optional[str] = None
    persona_id: Optional[str] = None
    source: Optional[Literal["text", "voice"]] = None


class StopClientEvent(BaseModel):
    type: Literal["stop"] = "stop"


class SecurityApprovalClientEvent(BaseModel):
    type: Literal["security_approval"] = "security_approval"
    approved: bool
    correlation_id: Optional[str] = None


class AskUserResponseClientEvent(BaseModel):
    type: Literal["ask_user_response"] = "ask_user_response"
    answer: Dict[str, Any]
    correlation_id: Optional[str] = None


class PlanReviewResponseClientEvent(BaseModel):
    type: Literal["plan_review_response"] = "plan_review_response"
    approved: bool
    feedback: Optional[str] = None
    correlation_id: Optional[str] = None


ClientEvent = Annotated[
    Union[
        UserMessageEvent,
        StopClientEvent,
        SecurityApprovalClientEvent,
        AskUserResponseClientEvent,
        PlanReviewResponseClientEvent,
    ],
    Field(discriminator="type"),
]

ClientEventAdapter = TypeAdapter(ClientEvent)

# ==========================================
# Server Events (Python Backend -> Frontend)
# ==========================================


class AssistantMessagePayload(BaseModel):
    id: Optional[str] = None
    type: Optional[str] = None
    content: Optional[str] = None
    tool_calls: Optional[List[Any]] = None
    tool_name: Optional[str] = None
    tool_call_id: Optional[str] = None
    model_used: Optional[str] = None
    token_usage: Optional[Dict[str, Any]] = None


class AssistantMessageEvent(BaseModel):
    type: Literal["assistant.message"] = "assistant.message"
    id: Optional[str] = None
    content: Optional[str] = None
    message: Optional[AssistantMessagePayload] = None


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
    confidence: Optional[float] = None


class VoiceWakeWordEvent(BaseModel):
    type: Literal["voice.wake_word"] = "voice.wake_word"
    phrase: str
    confidence: Optional[float] = None


class VoiceErrorEvent(BaseModel):
    type: Literal["voice.error"] = "voice.error"
    message: str
    code: Optional[str] = None


class VoiceTtsStateEvent(BaseModel):
    type: Literal["voice.tts_state"] = "voice.tts_state"
    speaking: bool
    utterance_id: Optional[str] = None


class VoiceStartedEvent(BaseModel):
    type: Literal["voice.started"] = "voice.started"
    mode: Literal["wake_word", "ptt"]


class SafeModeChangedEvent(BaseModel):
    type: Literal["safe_mode.changed"] = "safe_mode.changed"
    mode: Literal["normal", "safe_readonly", "safe_confirmed_exec", "safe_isolated"]


class ScreenAssistStateEvent(BaseModel):
    type: Literal["screen_assist.state"] = "screen_assist.state"
    mode: Literal["off", "preview", "annotating"]
    source: Literal["screen", "window", "region"]
    preview_path: Optional[str] = None


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
    type: Optional[str] = None
    risk_label: Optional[str] = None
    risk_confidence: Optional[float] = None
    risk_rationale: Optional[str] = None
    remediation_hint: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[str] = None


class InterruptEvent(BaseModel):
    type: Literal["interrupt"] = "interrupt"
    interrupts: List[Union[InterruptPayload, Dict[str, Any], Any]]


class ChartArtifact(BaseModel):
    filename: str
    url: str
    kind: Literal["interactive", "static"]
    mime_type: str


class ToolExecutionEvent(BaseModel):
    type: Literal["tool_execution"] = "tool_execution"
    status: Literal["running", "success", "error"]
    tool_name: str
    tool_call_id: Optional[str] = None
    input: Optional[str] = None
    output: Optional[str] = None
    error: Optional[str] = None
    risk_label: Optional[str] = None
    risk_confidence: Optional[float] = None
    risk_rationale: Optional[str] = None
    remediation_hint: Optional[str] = None
    duration: Optional[float] = None
    chart_artifact: Optional[ChartArtifact] = None


class RouterInfoEvent(BaseModel):
    type: Literal["router_info"] = "router_info"
    metadata: Dict[str, Any]


class FallbackChainItem(BaseModel):
    model: str
    status: str
    reason: str
    duration_ms: int


class ModelInfoEvent(BaseModel):
    type: Literal["model_info"] = "model_info"
    model: str
    model_used: Optional[str] = None
    swapping: Optional[bool] = None
    token_usage: Optional[Dict[str, Any]] = None
    fallback_chain: Optional[List[FallbackChainItem]] = None


class CloudUsageEvent(BaseModel):
    type: Literal["cloud_usage"] = "cloud_usage"
    turn: Optional[Dict[str, Any]] = None
    session: Optional[Dict[str, Any]] = None
    budget: Optional[Dict[str, Any]] = None
    warning_thresholds: Optional[List[float]] = None


class CloudBudgetWarningEvent(BaseModel):
    type: Literal["cloud_budget_warning"] = "cloud_budget_warning"
    threshold: float
    used_pct: float
    used_tokens: int
    daily_token_limit: int
    estimated_cost_usd: Optional[float] = None


class ContextSummarizedEvent(BaseModel):
    type: Literal["context_summarized"] = "context_summarized"
    summary: str
    takeaways: List[str]
    messages_compressed: int
    tokens_freed: int


class MemoryUpdatedEvent(BaseModel):
    type: Literal["memory_updated"] = "memory_updated"
    thread_id: Optional[str] = None


class FileStatusEvent(BaseModel):
    type: Literal["file_status"] = "file_status"
    name: Optional[str] = None
    status: Optional[str] = None
    chunks: Optional[int] = None
    error: Optional[str] = None


class BrowserPageContextEvent(BaseModel):
    type: Literal["browser.page_context"] = "browser.page_context"
    url: Optional[str] = None
    title: Optional[str] = None
    text: Optional[str] = None
    selection: Optional[str] = None
    intent: Optional[str] = None


class CoherenceRetryStartedEvent(BaseModel):
    type: Literal["coherence_retry_started"] = "coherence_retry_started"
    attempt: Optional[int] = None
    original_confidence: Optional[float] = None


class CoherenceRetryCompletedEvent(BaseModel):
    type: Literal["coherence_retry_completed"] = "coherence_retry_completed"


class ResponseCoherenceEvent(BaseModel):
    type: Literal["response_coherence"] = "response_coherence"
    coherent: bool
    confidence: float
    duration_ms: int
    reason: Optional[str] = None
    correlation_id: Optional[str] = None


ServerEvent = Annotated[
    Union[
        AssistantMessageEvent,
        ChunkEvent,
        StatusEvent,
        VoiceStateEvent,
        VoiceTranscriptEvent,
        VoiceWakeWordEvent,
        VoiceErrorEvent,
        VoiceTtsStateEvent,
        VoiceStartedEvent,
        SafeModeChangedEvent,
        ScreenAssistStateEvent,
        ActionProposalEvent,
        ActionProposalResultEvent,
        InterruptEvent,
        ToolExecutionEvent,
        RouterInfoEvent,
        ModelInfoEvent,
        CloudUsageEvent,
        CloudBudgetWarningEvent,
        ContextSummarizedEvent,
        MemoryUpdatedEvent,
        FileStatusEvent,
        BrowserPageContextEvent,
        CoherenceRetryStartedEvent,
        CoherenceRetryCompletedEvent,
        ResponseCoherenceEvent,
    ],
    Field(discriminator="type"),
]

ServerEventAdapter = TypeAdapter(ServerEvent)
