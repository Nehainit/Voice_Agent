# Project Root Context Feature Prompt

```txt
I am building:
CodeDuck - a local-first desktop voice coding agent

My goal:
The user should be able to highlight code in any editor, click/trigger a small Electron pill, speak a command like "explain this" or "fix this", and get a useful answer or safe code replacement preview.

For simple questions, the agent should answer about the highlighted code.

For fix/refactor/replace commands, the agent should propose a patch, show a diff, and only apply after user approval.

If project context is needed for a safer fix, the agent should ask the user to choose the project folder through a native folder picker. The user should not have to speak or type the full path.

My current stage:
Backend started.

Already implemented:
- FastAPI backend
- frontend/backend contract
- Pydantic request/response models
- /agent/respond endpoint
- /agent/respond/stream endpoint
- STT for audio input using faster-whisper
- optional TTS using Kokoro
- LangGraph-style node functions
- input_node
- classify_intent_node
- llm_orchestrator_node
- answer_node
- patch_node
- run_tests_node
- ChatOllama integration for Qwen through Ollama
- test execution is approved-only and allowlisted
- streaming test logs

Frontend is not started yet. The frontend will be an Electron floating pill, not a VS Code extension.

My tech stack:
- Electron desktop app
- React or simple HTML/CSS for pill UI
- FastAPI backend
- Pydantic models
- LangGraph-style architecture, StateGraph wiring later
- LangChain ChatOllama
- Ollama with qwen2.5-coder
- faster-whisper for STT
- Kokoro for TTS
- Python backend tools for project context
- Server-Sent Events for streaming

Feature I want to build now:
Add project-root request flow for patch/fix commands.

When user asks to fix/refactor/replace code and backend does not have projectRoot, backend should return a special state asking frontend to get project root from the user.

Frontend should then show a small prompt:
"Choose project folder for better fix"
with buttons:
- Choose Folder
- Use Selection Only
- Cancel

If user clicks Choose Folder, Electron should open native folder picker using dialog.showOpenDialog({ properties: ["openDirectory"] }).

Then frontend should resend the same request with:
- context.projectRoot
- context.projectRootApproved = true

If user clicks Use Selection Only, frontend should resend with:
- context.selectedOnly = true

User flow:
1. User highlights code in Cursor, VS Code, PyCharm, or any editor.
2. User triggers Electron pill with shortcut or click.
3. Electron captures selected code using temporary clipboard copy.
4. Electron records voice.
5. Electron sends audioBase64 and selectedText to FastAPI /agent/respond.
6. Backend transcribes audio with faster-whisper.
7. Backend classifies intent.
8. If intent is explain/debug/review:
   - backend returns uiState = answer.
9. If intent is fix/refactor/replace/write_test:
   - backend checks whether projectRoot is available.
10. If projectRoot is missing and selectedOnly is false:
   - backend returns uiState = needs_project_root.
11. Electron shows folder prompt.
12. User chooses folder.
13. Electron resends same command and selected code with projectRoot.
14. Backend safely validates projectRoot.
15. Backend enriches context from projectRoot later.
16. Backend generates patch preview.
17. Frontend shows diff with Apply / Modify / Cancel.
18. Apply only happens after explicit user action.

Expected input:
Frontend sends this to backend:

{
  "requestId": "req_123",
  "inputType": "audio",
  "audioBase64": "BASE64_AUDIO",
  "mimeType": "audio/webm",
  "commandText": "",
  "context": {
    "source": "clipboard",
    "selectedText": "def div(a, b):\n    return a / b",
    "surroundingText": "",
    "languageId": "python",
    "fileName": "utils.py",
    "filePath": "",
    "projectRoot": "",
    "projectRootApproved": false,
    "selectedOnly": false,
    "activeApp": "Cursor",
    "windowTitle": "utils.py - my-project"
  },
  "execution": {
    "allowTestRun": false,
    "workingDirectory": "",
    "testCommand": [],
    "testIterations": 1
  },
  "settings": {
    "llmProvider": "ollama",
    "llmModel": "qwen2.5-coder:3b",
    "sttProvider": "faster-whisper",
    "sttModel": "small.en",
    "ttsProvider": "off",
    "ttsVoice": "af_heart",
    "numCtx": 2048,
    "patchIterations": 1,
    "testIterations": 1
  }
}

Expected output:
If project root is needed:

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

If user chooses selection-only:

{
  "ok": true,
  "uiState": "patch_preview",
  "intent": "fix",
  "answer": "I prepared a selected-code replacement preview. Review the diff before applying it.",
  "proposal": {
    "proposalId": "prop_req_123",
    "title": "Fix selected code",
    "originalCode": "def div(a, b):\n    return a / b",
    "proposedCode": "def div(a, b):\n    if b == 0:\n        return None\n    return a / b",
    "diff": "...",
    "languageId": "python"
  },
  "actions": ["apply", "modify", "copy", "cancel"]
}

Happy path:
- User says "fix this".
- Backend sees patch intent.
- Backend sees no projectRoot.
- Backend returns needs_project_root.
- Electron opens native folder picker.
- User selects folder.
- Electron resends request with projectRoot and projectRootApproved true.
- Backend validates projectRoot exists and is directory.
- Backend generates project-aware patch preview.
- Frontend shows diff.
- User clicks Apply.
- Frontend applies replacement.
- User can then approve Run Tests separately.

Failure cases:
- No selected code:
  Backend returns needs_clarification asking user to highlight code.
- User says unclear command:
  Backend returns needs_clarification.
- Patch intent but projectRoot missing:
  Backend returns needs_project_root.
- User cancels folder picker:
  Frontend sends cancel or closes prompt.
- User chooses selection-only:
  Backend continues with selected-only patch.
- Invalid projectRoot:
  Backend returns error or asks to choose again.
- projectRoot is too broad, like home directory:
  Backend should warn or ask confirmation.
- filePath is outside projectRoot:
  Backend rejects it.
- Ollama unavailable:
  Backend returns error for patch generation, not a fake patch.
- STT fails:
  Backend returns stt_failed error.
- TTS fails:
  Backend keeps text response and adds warning.
- Test command is not allowlisted:
  Backend rejects it.

Constraints:
- Do not over-engineer.
- MVP first.
- Electron pill only, no big chatbot UI.
- No VS Code extension.
- No MCP for now.
- No RAG for now.
- No automatic file edits from backend.
- No test execution without explicit approval.
- No shell=True.
- No broad filesystem scanning.
- Backend should only inspect inside user-approved projectRoot.
- Project root should be chosen by native folder picker, not dictated by voice.
- Keep selected-only fallback available.
- Use local Ollama model.
- Use qwen2.5-coder:3b for local dev if 7B is slow.
- LangGraph StateGraph wiring can come later; first create clean nodes.

What I have already decided:
- Frontend is Electron floating pill.
- User highlights code manually.
- Electron captures selected text using clipboard copy.
- Electron records voice.
- Backend handles STT, intent, answer, patch, TTS, tests.
- Project root is requested only when patch/fix needs it.
- User grants project root through native folder picker.
- Backend returns needs_project_root state.
- Frontend resends request with projectRoot.
- Patch preview always comes before apply.
- Tests are approved-only and streamed.
- Patch iterations default to 1 locally.
- Test iterations default to 1 locally, can be increased later.

What I am confused about:
- What exact fields should be added to AgentContext?
- Should project root validation be a separate node?
- Should needs_project_root be handled before patch_node or inside patch_node?
- How should Electron preserve and restore clipboard safely?
- Should frontend remember recently selected project roots or ask every time?
- How much project context should backend read for MVP?
- How should backend infer filePath from windowTitle and selectedText?
- What is the cleanest way to avoid overbuilding while keeping this portfolio-grade?

What I want from you:
1. Review my design.
2. Tell me what is missing.
3. Suggest the cleanest implementation plan.
4. Explain the backend node structure before code.
5. Explain the Electron context-capture structure before code.
6. Add validation and error handling.
7. Add sample request/response payloads.
8. Add test cases for the backend.
9. Tell me how to verify it works locally.
10. Do not add MCP or RAG unless truly necessary.

Important:
Do not over-engineer.
Do not add extra tools unless necessary.
Explain tradeoffs simply.
Assume I am building this as a real portfolio/client-grade MVP.
```
