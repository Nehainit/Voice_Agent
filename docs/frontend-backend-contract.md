# Frontend Backend Contract

This contract defines the JSON messages between the Electron desktop app and the local FastAPI agent service.

The MVP is a floating desktop voice coding agent. The frontend captures selected code and audio/text input. The backend transcribes audio input when needed, decides whether to return an answer, a code replacement preview, a clarification, or an error, and optionally synthesizes the final response as speech.

## Principles

- Frontend owns UI state, recording, global shortcut, clipboard capture, and applying approved replacement text.
- Backend owns transcription, intent classification, answer generation, patch generation, diff generation, optional test execution, streaming progress, and optional TTS.
- Backend never directly edits files or controls the user's desktop in the MVP.
- Backend never runs tests unless the frontend sends an explicit approved test execution request.
- Code replacement always returns `uiState: "patch_preview"` first.
- Chat/text input is only shown by the frontend when the user chooses `modify` on a patch preview.
- Selected code, audio, transcripts, answers, and patches must not be logged by default.

## UI States

The backend can return these terminal UI states:

| uiState | Meaning | Frontend behavior |
| --- | --- | --- |
| `answer` | Agent produced an explanation/debug/review response. | Show answer panel. |
| `patch_preview` | Agent produced replacement code. | Show diff preview and patch actions. |
| `needs_project_root` | Agent needs user-approved project folder before a safer patch. | Show folder picker prompt. |
| `test_result` | Approved test command finished. | Show test summary and logs. |
| `needs_clarification` | Agent needs a short follow-up. | Show compact reply input. |
| `error` | Request failed. | Show error panel with retry/close actions. |

The frontend may also use local-only transient states:

| uiState | Meaning |
| --- | --- |
| `idle` | Floating pill is idle. |
| `capturing_selection` | Frontend is copying selected text. |
| `listening` | Microphone is recording. |
| `transcribing` | Audio was sent for transcription. |
| `thinking` | Backend is generating a response. |
| `running_tests` | Backend is streaming approved test output. |

## Intents

Backend returns one intent:

```txt
explain
debug
review
fix
refactor
replace
write_test
clarify
unknown
```

Intent routing:

| Intent | Expected uiState |
| --- | --- |
| `explain` | `answer` |
| `debug` | `answer` or `patch_preview` |
| `review` | `answer` |
| `fix` | `patch_preview` |
| `refactor` | `patch_preview` |
| `replace` | `patch_preview` |
| `write_test` | `patch_preview` |
| `clarify` | `needs_clarification` |
| `unknown` | `needs_clarification` or `answer` |

## Actions

Backend returns allowed frontend actions:

```txt
copy
speak_again
close
retry
reply
apply
modify
cancel
run_tests
choose_project_root
continue_selected_only
```

Action rules:

- `answer` may return `copy`, `speak_again`, `close`.
- `patch_preview` must return `apply`, `modify`, `copy`, `cancel`.
- `patch_preview` may return `run_tests` only after the frontend has applied the patch and has an approved test command.
- `needs_project_root` must return `choose_project_root`, `continue_selected_only`, `cancel`.
- `needs_clarification` must return `reply`, `close`.
- `error` may return `retry`, `close`.

## Main Agent Request

Endpoint:

```txt
POST /agent/respond
```

Request shape:

```json
{
  "requestId": "01HZY4W4DG9Q3Q9Z7T7Q9V2R4X",
  "inputType": "audio",
  "commandText": "",
  "audioBase64": "BASE64_AUDIO",
  "mimeType": "audio/webm",
  "context": {
    "source": "clipboard",
    "selectedText": "def add(a, b):\n    return a + b",
    "surroundingText": "",
    "languageId": "python",
    "fileName": "unknown.py",
    "filePath": "",
    "projectRoot": "",
    "projectRootApproved": false,
    "selectedOnly": false,
    "selectedRange": "",
    "activeApp": "Cursor",
    "windowTitle": "unknown.py - project"
  },
  "previousProposal": null,
  "execution": {
    "allowTestRun": false,
    "workingDirectory": "",
    "testCommand": [],
    "testIterations": 1
  },
  "settings": {
    "llmProvider": "ollama",
    "llmModel": "qwen2.5-coder:7b-instruct",
    "sttProvider": "faster-whisper",
    "sttModel": "small.en",
    "ttsProvider": "off",
    "ttsVoice": "af_heart",
    "numCtx": 4096,
    "patchIterations": 1
  }
}
```

### Request Fields

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `requestId` | string | yes | Frontend-generated ID for tracing one request. |
| `inputType` | `audio` or `text` | yes | Determines whether backend transcribes audio. |
| `commandText` | string | no | Used for typed commands or modify flow. |
| `audioBase64` | string | no | Required when `inputType` is `audio`. |
| `mimeType` | string | no | Example: `audio/webm`, `audio/wav`. |
| `context` | object | yes | Selected-code context from frontend. |
| `previousProposal` | object or null | no | Used when user modifies a proposed patch. |
| `execution` | object | no | Optional approved test execution request. |
| `settings` | object | no | Runtime model/provider overrides. |

## Audio Input Flow

When `inputType` is `audio`:

```txt
audioBase64
 -> temporary audio file
 -> faster-whisper STT
 -> transcript
 -> intent classification
 -> answer/patch/clarification/test flow
```

The backend returns the final transcript in `transcript`.

If transcription fails, the backend returns:

```json
{
  "ok": false,
  "uiState": "error",
  "error": {
    "code": "stt_failed",
    "message": "Speech-to-text failed: ..."
  }
}
```

## Speech Output Flow

When TTS is enabled in settings:

```txt
final answer text
 -> Kokoro TTS
 -> audioBase64
```

The backend only synthesizes the short user-facing `answer`, not proposed code or full test logs.

## Execution Object

Tests are opt-in and must be approved by the user in the frontend before the backend runs anything.

```json
{
  "allowTestRun": true,
  "workingDirectory": "/Users/user/project",
  "testCommand": ["npm", "test"],
  "testIterations": 1
}
```

Rules:

- `allowTestRun` must be true.
- `testCommand` must be a command array, not a shell string.
- Backend must not use `shell=True`.
- Backend may reject commands outside an allowlist such as `npm test`, `pytest`, `python -m pytest`, `pnpm test`, or `yarn test`.
- Frontend should only send test execution after the user clicks/says `Run tests`.
- `testIterations` defaults to `1` locally. Users with stronger machines can set it to `2` or more; the backend caps it at `5`.

## Context Object

```json
{
  "source": "clipboard",
  "selectedText": "selected code",
  "surroundingText": "",
  "languageId": "python",
  "fileName": "unknown.py",
  "filePath": "",
  "projectRoot": "",
  "projectRootApproved": false,
  "selectedOnly": false,
  "selectedRange": "",
  "activeApp": "Cursor",
  "windowTitle": "unknown.py - project"
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `source` | string | `clipboard`, `manual`, `unknown`. |
| `selectedText` | string | Main code context. |
| `surroundingText` | string | Optional future context. |
| `languageId` | string | Best-effort language identifier. |
| `fileName` | string | Best-effort file name. |
| `filePath` | string | Optional active file path if frontend can determine it. |
| `projectRoot` | string | User-selected project folder path. |
| `projectRootApproved` | boolean | True only after user explicitly chose/approved the folder. |
| `selectedOnly` | boolean | True when user chooses to continue without project folder. |
| `selectedRange` | string | Optional line/range text. |
| `activeApp` | string | Best-effort active application name. |
| `windowTitle` | string | Active window title for later file/project inference. |

## Project Root Request Flow

For patch intents (`fix`, `refactor`, `replace`, `write_test`), backend checks project context before generating a patch.

If `projectRoot` is missing and `selectedOnly` is false, backend returns:

```json
{
  "ok": true,
  "requestId": "req_123",
  "uiState": "needs_project_root",
  "intent": "fix",
  "transcript": "fix this",
  "answer": "Choose the project folder so I can inspect related files before proposing a safer fix.",
  "proposal": null,
  "testResult": null,
  "audioBase64": "",
  "audioMimeType": "audio/wav",
  "actions": ["choose_project_root", "continue_selected_only", "cancel"],
  "warnings": [],
  "error": null
}
```

Frontend behavior:

1. Show compact prompt: `Choose project folder for better fix`.
2. `Choose Folder` opens native folder picker.
3. Resend the same request with `context.projectRoot` and `context.projectRootApproved: true`.
4. `Use Selection Only` resends with `context.selectedOnly: true`.
5. `Cancel` closes the prompt.

Backend safety rules:

- Reject missing or invalid project roots.
- Reject project root `/` and the user's home folder as too broad.
- Treat `filePath` outside `projectRoot` as unsafe and ignore it.
- Continue selected-only patching only when `selectedOnly` is true.

## Previous Proposal Object

Used only when the user clicks `Modify` on a patch preview.

```json
{
  "proposalId": "prop_01HZY4X7RE8EAERFZE4SJ4A4RT",
  "intent": "fix",
  "originalCode": "def div(a, b):\n    return a / b",
  "proposedCode": "def div(a, b):\n    if b == 0:\n        return None\n    return a / b",
  "diff": "--- selected\n+++ proposed\n..."
}
```

## Main Agent Response

Response shape:

```json
{
  "ok": true,
  "requestId": "01HZY4W4DG9Q3Q9Z7T7Q9V2R4X",
  "uiState": "answer",
  "intent": "explain",
  "transcript": "explain this",
  "answer": "This function adds two values and returns the result.",
  "proposal": null,
  "testResult": null,
  "audioBase64": "",
  "audioMimeType": "audio/wav",
  "actions": ["copy", "speak_again", "close"],
  "warnings": [],
  "error": null
}
```

### Response Fields

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `ok` | boolean | yes | False only for failed requests. |
| `requestId` | string | yes | Echo from request. |
| `uiState` | string | yes | One terminal UI state. |
| `intent` | string | yes | Classified intent. |
| `transcript` | string | yes | Empty for failed audio transcription. |
| `answer` | string | yes | User-facing text. |
| `proposal` | object or null | yes | Present only for `patch_preview`. |
| `testResult` | object or null | yes | Present for `test_result` or attached to final streamed response after approved tests. |
| `audioBase64` | string | yes | Empty when TTS disabled/skipped. |
| `audioMimeType` | string | yes | Defaults to `audio/wav`. |
| `actions` | string[] | yes | Allowed frontend actions. |
| `warnings` | string[] | yes | Non-fatal issues. |
| `error` | object or null | yes | Present only when `ok` is false. |

## Answer Response Example

```json
{
  "ok": true,
  "requestId": "req_1",
  "uiState": "answer",
  "intent": "explain",
  "transcript": "explain this",
  "answer": "This function adds two values and returns the result.",
  "proposal": null,
  "testResult": null,
  "audioBase64": "",
  "audioMimeType": "audio/wav",
  "actions": ["copy", "speak_again", "close"],
  "warnings": [],
  "error": null
}
```

## Patch Preview Response Example

```json
{
  "ok": true,
  "requestId": "req_2",
  "uiState": "patch_preview",
  "intent": "fix",
  "transcript": "fix this",
  "answer": "I suggest handling division by zero before returning the result.",
  "proposal": {
    "proposalId": "prop_1",
    "title": "Add zero-division guard",
    "originalCode": "def div(a, b):\n    return a / b",
    "proposedCode": "def div(a, b):\n    if b == 0:\n        return None\n    return a / b",
    "diff": "--- selected\n+++ proposed\n@@\n def div(a, b):\n+    if b == 0:\n+        return None\n     return a / b",
    "languageId": "python"
  },
  "testResult": null,
  "audioBase64": "",
  "audioMimeType": "audio/wav",
  "actions": ["apply", "modify", "copy", "cancel"],
  "warnings": [],
  "error": null
}
```

## Clarification Response Example

```json
{
  "ok": true,
  "requestId": "req_3",
  "uiState": "needs_clarification",
  "intent": "clarify",
  "transcript": "do it",
  "answer": "Do you want me to explain the selected code or change it?",
  "proposal": null,
  "testResult": null,
  "audioBase64": "",
  "audioMimeType": "audio/wav",
  "actions": ["reply", "close"],
  "warnings": [],
  "error": null
}
```

## Error Response Example

```json
{
  "ok": false,
  "requestId": "req_4",
  "uiState": "error",
  "intent": "unknown",
  "transcript": "",
  "answer": "",
  "proposal": null,
  "testResult": null,
  "audioBase64": "",
  "audioMimeType": "audio/wav",
  "actions": ["retry", "close"],
  "warnings": [],
  "error": {
    "code": "stt_failed",
    "message": "Speech could not be transcribed."
  }
}
```

## Test Result Example

```json
{
  "ok": true,
  "requestId": "req_5",
  "uiState": "test_result",
  "intent": "fix",
  "transcript": "run tests",
  "answer": "Tests failed. Review the log before continuing.",
  "proposal": null,
  "testResult": {
    "status": "failed",
    "command": ["npm", "test"],
    "workingDirectory": "/Users/user/project",
    "iterations": 1,
    "exitCode": 1,
    "output": "test output...",
    "durationSeconds": 3.42
  },
  "audioBase64": "",
  "audioMimeType": "audio/wav",
  "actions": ["copy", "close"],
  "warnings": [],
  "error": null
}
```

## Patch Generation Loop

Patch generation is designed as a loop:

```txt
patch_node
 -> generate replacement code
 -> validate model output
 -> optionally revise
 -> return patch_preview
```

The loop count is controlled by settings:

```json
{
  "patchIterations": 1
}
```

Recommended defaults:

- Local development: `1`
- Stronger machine or cloud/LAN Ollama: `2`
- Upper backend cap: `5`

Important safety rule:

```txt
generate -> run tests -> revise
```

requires an approved workspace/apply/sandbox flow. The backend must not silently apply generated code or run tests against the user's project without explicit approval.

## Streaming Endpoint

Endpoint:

```txt
POST /agent/respond/stream
```

The streaming endpoint uses Server-Sent Events. Each event is one JSON object.

Event shape:

```json
{
  "requestId": "req_1",
  "event": "status",
  "message": "Classifying intent",
  "data": {}
}
```

Event types:

| event | Meaning |
| --- | --- |
| `status` | Current backend step. |
| `transcript` | Final transcript after STT. |
| `intent` | Classified intent and route. |
| `answer_delta` | Incremental answer text, when supported. |
| `patch_delta` | Incremental patch text, when supported. |
| `test_log` | A chunk of test stdout/stderr. |
| `final` | Final `AgentRespondResponse`. |
| `error` | Streaming failure. |

Frontend behavior:

- Show status updates in the floating panel.
- For audio input, expect `status: Transcribing audio`, then a `transcript` event.
- Append `answer_delta` or `patch_delta` when available.
- Stream `test_log` into a compact terminal/log view.
- If TTS is enabled, the final response may include `audioBase64`; play it after receiving `final`.
- Treat `final` as the canonical final response.

## Frontend Apply Flow

The backend does not apply code changes in the MVP.

When the user clicks `Apply`:

1. Frontend verifies `uiState` is `patch_preview`.
2. Frontend copies `proposal.proposedCode` to clipboard.
3. Frontend focuses the original app.
4. Frontend pastes into the active selection.
5. Frontend restores the previous clipboard when possible.
6. Frontend shows a local success/failure status.

## Validation Rules

- If `inputType` is `audio`, `audioBase64` must be present.
- If `inputType` is `text`, `commandText` must be present.
- If `uiState` is `patch_preview`, `proposal` must be present.
- If `uiState` is not `patch_preview`, `proposal` must be null.
- If `uiState` is `test_result`, `testResult` must be present.
- If `ok` is false, `uiState` must be `error` and `error` must be present.
- If `ok` is true, `error` must be null.
- `selectedText` may be empty, but backend should then return `needs_clarification` if context is required.

## MVP Endpoint Summary

```txt
GET  /health
GET  /settings
POST /settings
POST /agent/respond
POST /agent/respond/stream
```

Existing endpoints may remain temporarily:

```txt
POST /ask-text
POST /ask-audio
POST /ask-recording
```

The Electron MVP should target `/agent/respond`.
