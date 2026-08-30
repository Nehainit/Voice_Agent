const vscode = require("vscode");

let currentPanel;

function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand("codeDuck.openPanel", () => openPanel(context, "debug")),
    vscode.commands.registerCommand("codeDuck.explainSelection", () => openPanel(context, "explain", true)),
    vscode.commands.registerCommand("codeDuck.debugSelection", () => openPanel(context, "debug", true)),
    vscode.commands.registerCommand("codeDuck.reviewSelection", () => openPanel(context, "review", true))
  );
}

function deactivate() {}

function openPanel(context, mode = "debug", autoAsk = false) {
  if (currentPanel) {
    currentPanel.reveal(vscode.ViewColumn.Beside);
  } else {
    currentPanel = vscode.window.createWebviewPanel("codeDuck", "CodeDuck", vscode.ViewColumn.Beside, {
      enableScripts: true,
      retainContextWhenHidden: true
    });
    currentPanel.webview.html = getWebviewHtml(currentPanel.webview);
    currentPanel.onDidDispose(() => {
      currentPanel = undefined;
    });
    currentPanel.webview.onDidReceiveMessage((message) => handleMessage(message), undefined, context.subscriptions);
  }

  currentPanel.webview.postMessage({
    type: "hydrate",
    mode,
    context: getEditorContext(),
    autoAsk
  });
  syncSettingsToPanel();
}

async function handleMessage(message) {
  if (!message || !message.type) return;

  if (message.type === "refreshContext") {
    currentPanel?.webview.postMessage({ type: "context", context: getEditorContext() });
    return;
  }

  if (message.type === "getSettings") {
    await syncSettingsToPanel();
    return;
  }

  if (message.type === "saveSettings") {
    await saveSettings(message.settings || {});
    return;
  }

  if (message.type === "askAudio" || message.type === "askRecording") {
    await askLocalService(message);
  }
}

async function syncSettingsToPanel() {
  try {
    const settings = await getJson(`${getServiceUrl()}/settings`);
    currentPanel?.webview.postMessage({ type: "settings", settings });
  } catch (error) {
    currentPanel?.webview.postMessage({
      type: "error",
      message: `Settings unavailable: ${error.message}`
    });
  }
}

async function saveSettings(settings) {
  try {
    const saved = await postJson(`${getServiceUrl()}/settings`, settings);
    currentPanel?.webview.postMessage({ type: "settings", settings: saved });
    currentPanel?.webview.postMessage({ type: "notice", message: "Settings saved." });
  } catch (error) {
    currentPanel?.webview.postMessage({
      type: "error",
      message: `Could not save settings: ${error.message}`
    });
  }
}

async function askLocalService(message) {
  const endpoint = message.type === "askAudio" ? "/ask-audio" : "/ask-recording";
  const payload = {
    mode: message.mode || "debug",
    context: message.context || getEditorContext(),
    audioBase64: message.audioBase64,
    mimeType: message.mimeType,
    durationSeconds: message.durationSeconds,
    settings: message.settings
  };

  currentPanel?.webview.postMessage({ type: "status", status: endpoint === "/ask-recording" ? "Recording locally" : "Thinking" });

  try {
    const response = await postJson(`${getServiceUrl()}${endpoint}`, payload);
    currentPanel?.webview.postMessage({
      type: "answer",
      answer: response.answer || "",
      transcript: response.transcript || "",
      audioBase64: response.audioBase64 || "",
      audioMimeType: response.audioMimeType || "audio/wav",
      warnings: response.warnings || []
    });
  } catch (error) {
    currentPanel?.webview.postMessage({
      type: "error",
      message: `Local service error: ${error.message}`
    });
  } finally {
    currentPanel?.webview.postMessage({ type: "status", status: "Ready" });
  }
}

function getEditorContext() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    return {
      kind: "none",
      languageId: "",
      fileName: "",
      selectedText: "",
      surroundingText: "",
      screenSummary: "No active editor is visible to the extension."
    };
  }

  const document = editor.document;
  const selection = editor.selection;
  const selectedText = document.getText(selection);
  const activeLine = selection.active.line;
  const start = Math.max(0, activeLine - 80);
  const end = Math.min(document.lineCount - 1, activeLine + 80);
  const surroundingRange = new vscode.Range(start, 0, end, document.lineAt(end).text.length);
  const selectedRange = selection.isEmpty
    ? ""
    : `${selection.start.line + 1}:${selection.start.character + 1}-${selection.end.line + 1}:${selection.end.character + 1}`;

  return {
    kind: selectedText ? "highlighted_selection" : "active_editor_window",
    languageId: document.languageId,
    fileName: document.fileName,
    selectedText,
    surroundingText: document.getText(surroundingRange),
    selectedRange,
    screenSummary: selectedText
      ? `Highlighted ${selectedText.length} characters in ${document.fileName}.`
      : `No highlighted text. Using nearby visible editor context from ${document.fileName}.`
  };
}

function getServiceUrl() {
  return vscode.workspace.getConfiguration("codeDuck").get("serviceUrl") || "http://127.0.0.1:8765";
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${text}`);
  }
  return response.json();
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${text}`);
  }
  return response.json();
}

function getWebviewHtml(webview) {
  const nonce = getNonce();

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}'; media-src ${webview.cspSource} data: blob:;">
  <title>CodeDuck</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #101114;
      --panel: #191d22;
      --panel-2: #20252c;
      --text: #eef2f5;
      --muted: #97a3ae;
      --line: #343b45;
      --accent: #43c585;
      --cyan: #39b7e6;
      --danger: #f07575;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 13px/1.45 var(--vscode-font-family, ui-sans-serif, system-ui);
    }
    button, select, input { font: inherit; }
    button { cursor: pointer; }
    .shell {
      display: grid;
      grid-template-rows: auto auto auto 1fr auto;
      height: 100vh;
      min-width: 300px;
    }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 12px;
      border-bottom: 1px solid var(--line);
      background: #14171b;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 8px;
      font-weight: 700;
      min-width: 0;
    }
    .orb-sm {
      width: 14px;
      height: 14px;
      border-radius: 999px;
      background: radial-gradient(circle, #c8fff0 0, var(--accent) 42%, #126943 100%);
      box-shadow: 0 0 14px rgba(67, 197, 133, 0.55);
      flex: 0 0 auto;
    }
    .toolbar {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
    }
    .icon {
      width: 34px;
      height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--text);
      background: var(--panel-2);
    }
    .modes {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 6px;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
    }
    .mode {
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--muted);
      background: var(--panel);
      padding: 8px;
    }
    .mode.active {
      border-color: rgba(67, 197, 133, 0.7);
      color: var(--text);
      background: rgba(67, 197, 133, 0.12);
    }
    .context {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      align-items: center;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      color: var(--muted);
      background: #14171b;
    }
    .context-text {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .voice {
      display: grid;
      place-items: center;
      gap: 12px;
      padding: 14px 12px;
      border-bottom: 1px solid var(--line);
    }
    .orb {
      position: relative;
      width: min(210px, 56vw);
      aspect-ratio: 1;
      border-radius: 999px;
      border: 1px solid rgba(57, 183, 230, 0.45);
      background:
        radial-gradient(circle at 50% 50%, rgba(67, 197, 133, 0.95) 0 9%, transparent 10%),
        radial-gradient(circle at 42% 45%, rgba(57, 183, 230, 0.95) 0 3%, transparent 4%),
        radial-gradient(circle at 62% 58%, rgba(57, 183, 230, 0.7) 0 4%, transparent 5%),
        radial-gradient(circle at 50% 50%, rgba(57, 183, 230, 0.22) 0 34%, transparent 35%),
        repeating-radial-gradient(circle at 50% 50%, rgba(57, 183, 230, 0.7) 0 1px, transparent 2px 7px);
      box-shadow: inset 0 0 44px rgba(57, 183, 230, 0.25), 0 0 36px rgba(57, 183, 230, 0.2);
    }
    .orb::before {
      content: "";
      position: absolute;
      inset: 15%;
      border-radius: 999px;
      border: 1px dashed rgba(238, 242, 245, 0.2);
      animation: spin 10s linear infinite;
    }
    .orb.listening {
      animation: breathe 1.25s ease-in-out infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    @keyframes breathe {
      0%, 100% { transform: scale(1); filter: brightness(1); }
      50% { transform: scale(1.04); filter: brightness(1.35); }
    }
    .mic {
      min-width: 168px;
      height: 42px;
      border: 1px solid rgba(67, 197, 133, 0.65);
      border-radius: 6px;
      color: #05140d;
      background: var(--accent);
      font-weight: 800;
    }
    .mic.recording {
      border-color: rgba(240, 117, 117, 0.8);
      background: var(--danger);
      color: #220506;
    }
    .messages {
      overflow: auto;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .message {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px;
      background: var(--panel);
    }
    .message.user { border-color: rgba(67, 197, 133, 0.4); }
    .message.warning {
      border-color: rgba(240, 117, 117, 0.5);
      color: #ffd6d6;
      background: rgba(240, 117, 117, 0.08);
    }
    .message.hint {
      border-color: rgba(57, 183, 230, 0.45);
      color: #c9efff;
      background: rgba(57, 183, 230, 0.08);
    }
    .label {
      margin-bottom: 5px;
      color: var(--muted);
      font-size: 12px;
    }
    .text {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    .settings {
      display: none;
      border-top: 1px solid var(--line);
      background: #14171b;
      padding: 12px;
      max-height: 46vh;
      overflow: auto;
    }
    .settings.open { display: block; }
    .settings-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    .field {
      display: grid;
      gap: 4px;
      min-width: 0;
    }
    .field label {
      color: var(--muted);
      font-size: 12px;
    }
    select, input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--text);
      background: var(--panel);
      padding: 7px;
      outline: none;
    }
    .save {
      margin-top: 10px;
      width: 100%;
      height: 36px;
      border: 1px solid var(--accent);
      border-radius: 6px;
      color: #06150e;
      background: var(--accent);
      font-weight: 800;
    }
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div class="brand"><span class="orb-sm"></span><span>CodeDuck Voice</span></div>
      <div class="toolbar"><span id="status">Ready</span><button id="settingsToggle" class="icon" title="Models and providers">⚙</button></div>
    </header>
    <nav class="modes">
      <button class="mode active" data-mode="explain">Explain</button>
      <button class="mode" data-mode="debug">Debug</button>
      <button class="mode" data-mode="review">Review</button>
    </nav>
    <section class="context">
      <div id="context" class="context-text">Context: none</div>
      <button id="refresh" class="icon" title="Refresh highlighted context">↻</button>
    </section>
    <section class="voice">
      <div id="orb" class="orb" aria-hidden="true"></div>
      <button id="mic" class="mic" title="Hold to talk">Hold to Talk</button>
    </section>
    <main id="messages" class="messages">
      <div class="message hint">
        <div class="label">Agent</div>
        <div class="text">Highlight code or keep the target file visible, then use voice. Typed chat has been removed.</div>
      </div>
    </main>
    <section id="settings" class="settings">
      <div class="settings-grid">
        <div class="field"><label>LLM Provider</label><select id="llmProvider"><option>ollama</option><option>openai</option><option>anthropic</option><option>google</option></select></div>
        <div class="field"><label>LLM Model</label><input id="llmModel" list="llmModels"></div>
        <div class="field"><label>STT Provider</label><select id="sttProvider"><option>faster-whisper</option><option>openai</option><option>deepgram</option></select></div>
        <div class="field"><label>STT Model</label><input id="sttModel" list="sttModels"></div>
        <div class="field"><label>TTS Provider</label><select id="ttsProvider"><option>off</option><option>kokoro</option><option>openai</option><option>elevenlabs</option></select></div>
        <div class="field"><label>TTS Voice</label><input id="ttsVoice" list="ttsVoices"></div>
        <div class="field"><label>Recording Seconds</label><input id="recordingSeconds" type="number" min="2" max="20" step="1"></div>
        <div class="field"><label>Context Tokens</label><input id="numCtx" type="number" min="1024" max="8192" step="1024"></div>
      </div>
      <button id="saveSettings" class="save">Save Providers</button>
      <datalist id="llmModels"><option value="qwen2.5-coder:7b-instruct"><option value="llama3.2"><option value="qwen2.5-coder:3b"></datalist>
      <datalist id="sttModels"><option value="base.en"><option value="small.en"><option value="medium.en"></datalist>
      <datalist id="ttsVoices"><option value="af_heart"><option value="af_bella"><option value="am_adam"><option value="am_michael"></datalist>
    </section>
  </div>
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    let mode = "explain";
    let editorContext = {};
    let settings = {};
    let mediaRecorder;
    let chunks = [];

    const messages = document.getElementById("messages");
    const statusEl = document.getElementById("status");
    const contextEl = document.getElementById("context");
    const orb = document.getElementById("orb");
    const mic = document.getElementById("mic");
    const settingsPanel = document.getElementById("settings");

    const fields = ["llmProvider", "llmModel", "sttProvider", "sttModel", "ttsProvider", "ttsVoice", "recordingSeconds", "numCtx"];

    document.querySelectorAll(".mode").forEach((button) => {
      button.addEventListener("click", () => setMode(button.dataset.mode));
    });
    document.getElementById("refresh").addEventListener("click", () => vscode.postMessage({ type: "refreshContext" }));
    document.getElementById("settingsToggle").addEventListener("click", () => settingsPanel.classList.toggle("open"));
    document.getElementById("saveSettings").addEventListener("click", saveSettings);

    mic.addEventListener("mousedown", startRecording);
    mic.addEventListener("mouseup", stopRecording);
    mic.addEventListener("mouseleave", stopRecording);
    mic.addEventListener("touchstart", (event) => { event.preventDefault(); startRecording(); });
    mic.addEventListener("touchend", (event) => { event.preventDefault(); stopRecording(); });

    window.addEventListener("message", (event) => {
      const message = event.data;
      if (message.type === "hydrate") {
        setMode(message.mode || "debug");
        setContext(message.context);
        if (message.autoAsk) {
          addMessage("Prompt", defaultQuestionForMode(mode), "hint");
        }
      }
      if (message.type === "context") setContext(message.context);
      if (message.type === "settings") setSettings(message.settings || {});
      if (message.type === "status") setStatus(message.status);
      if (message.type === "notice") addMessage("System", message.message, "hint");
      if (message.type === "answer") {
        if (message.transcript) addMessage("You said", message.transcript, "user");
        if (message.answer) addMessage("Agent", message.answer, "agent");
        (message.warnings || []).forEach((warning) => addMessage("Warning", warning, "warning"));
        if (message.audioBase64) playAudio(message.audioBase64, message.audioMimeType);
      }
      if (message.type === "error") addMessage("Error", message.message, "warning");
    });

    vscode.postMessage({ type: "getSettings" });

    function setMode(nextMode) {
      mode = nextMode;
      document.querySelectorAll(".mode").forEach((button) => {
        button.classList.toggle("active", button.dataset.mode === mode);
      });
    }

    function setContext(nextContext) {
      editorContext = nextContext || {};
      const kind = editorContext.kind || "none";
      const language = editorContext.languageId ? " · " + editorContext.languageId : "";
      const file = editorContext.fileName ? " · " + editorContext.fileName.split(/[\\\\/]/).pop() : "";
      const range = editorContext.selectedRange ? " · " + editorContext.selectedRange : "";
      contextEl.textContent = "Context: " + kind + language + file + range;
    }

    function setSettings(nextSettings) {
      settings = nextSettings;
      fields.forEach((field) => {
        const node = document.getElementById(field);
        if (node && settings[field] !== undefined) node.value = settings[field];
      });
    }

    function saveSettings() {
      const next = {};
      fields.forEach((field) => {
        const node = document.getElementById(field);
        if (!node) return;
        next[field] = node.type === "number" ? Number(node.value) : node.value;
      });
      settings = next;
      vscode.postMessage({ type: "saveSettings", settings });
    }

    async function startRecording() {
      vscode.postMessage({ type: "refreshContext" });
      if (mediaRecorder && mediaRecorder.state === "recording") return;
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        chunks = [];
        mediaRecorder = new MediaRecorder(stream);
        mediaRecorder.addEventListener("dataavailable", (event) => {
          if (event.data.size > 0) chunks.push(event.data);
        });
        mediaRecorder.addEventListener("stop", async () => {
          stream.getTracks().forEach((track) => track.stop());
          const blob = new Blob(chunks, { type: mediaRecorder.mimeType || "audio/webm" });
          const audioBase64 = await blobToBase64(blob);
          vscode.postMessage({
            type: "askAudio",
            mode,
            context: editorContext,
            audioBase64,
            mimeType: blob.type,
            settings
          });
        });
        mediaRecorder.start();
        mic.classList.add("recording");
        orb.classList.add("listening");
        mic.textContent = "Release to Send";
        setStatus("Listening");
      } catch (error) {
        addMessage("Microphone", microphoneHelp(error), "warning");
        addMessage("Fallback", "Starting a local backend recording. Speak now.", "hint");
        setStatus("Recording locally");
        vscode.postMessage({
          type: "askRecording",
          mode,
          context: editorContext,
          durationSeconds: Number(settings.recordingSeconds || 8),
          settings
        });
      }
    }

    function stopRecording() {
      if (mediaRecorder && mediaRecorder.state === "recording") {
        mediaRecorder.stop();
        mic.classList.remove("recording");
        orb.classList.remove("listening");
        mic.textContent = "Hold to Talk";
        setStatus("Transcribing");
      }
    }

    function blobToBase64(blob) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve(String(reader.result).split(",")[1]);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
      });
    }

    function addMessage(label, text, kind) {
      const node = document.createElement("div");
      node.className = "message " + (kind || "");
      node.innerHTML = '<div class="label"></div><div class="text"></div>';
      node.querySelector(".label").textContent = label;
      node.querySelector(".text").textContent = text;
      messages.appendChild(node);
      messages.scrollTop = messages.scrollHeight;
    }

    function setStatus(status) {
      statusEl.textContent = status || "Ready";
    }

    function playAudio(audioBase64, mimeType) {
      const audio = new Audio("data:" + (mimeType || "audio/wav") + ";base64," + audioBase64);
      audio.play().catch((error) => addMessage("Audio", "Playback blocked: " + error.message, "warning"));
    }

    function microphoneHelp(error) {
      const reason = error && error.message ? error.message : "permission was denied";
      return "Microphone unavailable: " + reason + ". The backend recording fallback will be used.";
    }

    function defaultQuestionForMode(activeMode) {
      if (activeMode === "review") return "Review the highlighted code.";
      if (activeMode === "explain") return "Explain the highlighted code.";
      return "Help debug the highlighted code.";
    }
  </script>
</body>
</html>`;
}

function getNonce() {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  let text = "";
  for (let i = 0; i < 32; i += 1) {
    text += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return text;
}

module.exports = {
  activate,
  deactivate
};
