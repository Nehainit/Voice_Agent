from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .settings import RuntimeSettings


InputType = Literal["audio", "text"]
MindState = Literal[
    "NO_TASK",
    "TASK_ACTIVE",
    "EXPLAINING",
    "DEBUGGING",
    "WAITING_FOR_USER_RESULT",
    "SIDE_CONVERSATION",
    "RESOLVED",
]
UiState = Literal[
    "answer",
    "patch_preview",
    "draft_preview",
    "dictation_result",
    "meeting_summary",
    "needs_project_root",
    "needs_clarification",
    "test_result",
    "error",
]
Intent = Literal[
    "chat",
    "explain",
    "debug",
    "review",
    "fix",
    "refactor",
    "replace",
    "write_test",
    "clarify",
    "unknown",
]
Action = Literal[
    "copy",
    "paste_to_focused_app",
    "copy_to_clipboard",
    "speak_response",
    "show_patch_preview",
    "create_email_draft",
    "save_note",
    "open_url",
    "start_meeting_transcription",
    "stop_meeting_transcription",
    "summarize_meeting",
    "speak_again",
    "close",
    "retry",
    "reply",
    "apply",
    "modify",
    "cancel",
    "run_tests",
    "choose_project_root",
    "continue_selected_only",
    "sleep",
    "quit_app",
]
TestStatus = Literal["skipped", "passed", "failed", "error"]
StreamEventType = Literal[
    "status",
    "transcript",
    "intent",
    "answer_delta",
    "patch_delta",
    "test_log",
    "final",
    "error",
]


class AgentContext(BaseModel):
    source: str = "unknown"
    selectedText: str = ""
    surroundingText: str = ""
    languageId: str = ""
    fileName: str = ""
    filePath: str = ""
    projectRoot: str = ""
    projectRootApproved: bool = False
    selectedOnly: bool = False
    selectedRange: str = ""
    activeApp: str = ""
    windowTitle: str = ""
    focusedInputType: str = ""
    meetingDetected: bool = False


class PreviousProposal(BaseModel):
    proposalId: str = ""
    intent: Intent = "unknown"
    originalCode: str = ""
    proposedCode: str = ""
    diff: str = ""


class ExecutionOptions(BaseModel):
    allowTestRun: bool = False
    workingDirectory: str = ""
    testCommand: list[str] = Field(default_factory=list)
    testIterations: int = 1


class PatchProposal(BaseModel):
    proposalId: str
    title: str = ""
    originalCode: str
    proposedCode: str
    diff: str
    languageId: str = ""


class TestResult(BaseModel):
    status: TestStatus = "skipped"
    command: list[str] = Field(default_factory=list)
    workingDirectory: str = ""
    iterations: int = 1
    exitCode: int | None = None
    output: str = ""
    durationSeconds: float = 0.0


class TaskSnapshot(BaseModel):
    taskId: str = ""
    agentId: str = ""
    status: MindState = "NO_TASK"
    intent: str = ""
    title: str = ""
    problemStatement: str = ""
    selectedCodeSummary: str = ""
    selectedCodeHash: str = ""
    fileName: str = ""
    filePath: str = ""
    projectRoot: str = ""
    attempts: list[dict[str, Any]] = Field(default_factory=list)
    lastAssistantStep: str = ""
    waitingFor: str = ""
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    createdAt: str = ""
    updatedAt: str = ""
    resolvedAt: str | None = None


class AgentAction(BaseModel):
    type: str
    requiresApproval: bool = True
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentError(BaseModel):
    code: str
    message: str


class AgentRespondRequest(BaseModel):
    requestId: str
    sessionId: str = "default"
    activeAgentId: str = "general_assistant"
    inputMode: str = "agent"
    preferredResponseLanguage: str = "Auto"
    transcriptionLanguage: str = "Auto"
    explicitTrigger: bool = True
    inputType: InputType = "text"
    commandText: str = ""
    audioBase64: str = ""
    mimeType: str = ""
    audioDurationMs: int | None = None
    audioSizeBytes: int | None = None
    context: AgentContext = Field(default_factory=AgentContext)
    previousProposal: PreviousProposal | None = None
    execution: ExecutionOptions = Field(default_factory=ExecutionOptions)
    settings: RuntimeSettings | None = None

    @model_validator(mode="after")
    def validate_input_payload(self) -> AgentRespondRequest:
        if self.inputType == "audio" and not self.audioBase64:
            raise ValueError("audioBase64 is required when inputType is 'audio'.")
        if self.inputType == "text" and not self.commandText.strip():
            raise ValueError("commandText is required when inputType is 'text'.")
        return self


class AgentRespondResponse(BaseModel):
    ok: bool = True
    requestId: str
    inputMode: str = "agent"
    activeAgentId: str = "general_assistant"
    uiState: UiState
    intent: Intent
    mindState: MindState = "NO_TASK"
    shouldListenAgain: bool = False
    transcript: str = ""
    answer: str = ""
    spokenAnswer: str = ""
    draftText: str = ""
    proposal: PatchProposal | None = None
    task: TaskSnapshot | None = None
    testResult: TestResult | None = None
    audioBase64: str = ""
    audioMimeType: str = "audio/wav"
    sleepMs: int | None = None
    actions: list[Action] = Field(default_factory=list)
    actionPlans: list[AgentAction] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: AgentError | None = None

    @model_validator(mode="after")
    def validate_response_contract(self) -> AgentRespondResponse:
        if self.uiState == "patch_preview" and self.proposal is None:
            raise ValueError("proposal is required when uiState is 'patch_preview'.")
        if self.uiState != "patch_preview" and self.proposal is not None:
            raise ValueError("proposal must be null unless uiState is 'patch_preview'.")
        if self.uiState == "test_result" and self.testResult is None:
            raise ValueError("testResult is required when uiState is 'test_result'.")
        if not self.ok and self.uiState != "error":
            raise ValueError("uiState must be 'error' when ok is false.")
        if not self.ok and self.error is None:
            raise ValueError("error is required when ok is false.")
        if self.ok and self.error is not None:
            raise ValueError("error must be null when ok is true.")
        return self


class AgentStreamEvent(BaseModel):
    requestId: str
    event: StreamEventType
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
