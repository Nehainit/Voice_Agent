const appEl = document.getElementById("app");
const micButton = document.getElementById("micButton");
const closeButton = document.getElementById("closeButton");
const statusEl = document.getElementById("status");
const contextEl = document.getElementById("context");
const messagesEl = document.getElementById("messages");
const projectRootPrompt = document.getElementById("projectRootPrompt");
const projectRootMessage = document.getElementById("projectRootMessage");
const chooseRootButton = document.getElementById("chooseRootButton");
const selectedOnlyButton = document.getElementById("selectedOnlyButton");
const cancelRootButton = document.getElementById("cancelRootButton");
const patchPanel = document.getElementById("patchPanel");
const diffView = document.getElementById("diffView");
const applyButton = document.getElementById("applyButton");
const modifyButton = document.getElementById("modifyButton");
const copyPatchButton = document.getElementById("copyPatchButton");
const cancelPatchButton = document.getElementById("cancelPatchButton");
const modifyBox = document.getElementById("modifyBox");
const modifyText = document.getElementById("modifyText");
const sendModifyButton = document.getElementById("sendModifyButton");
const settingsButton = document.getElementById("settingsButton");
const settingsPanel = document.getElementById("settingsPanel");
const closeSettingsButton = document.getElementById("closeSettingsButton");
const modeSelect = document.getElementById("modeSelect");
const agentSelect = document.getElementById("agentSelect");
const languageSelect = document.getElementById("languageSelect");
const musicButton = document.getElementById("musicButton");
const sceneActivity = document.getElementById("sceneActivity");
const sceneHint = document.getElementById("sceneHint");

const SLEEP_MS = 120000;
const RECORDING_MAX_MS = 20000;
const INITIAL_SILENCE_MS = 10000;
const END_SILENCE_MS = 1600;
const MIN_RECORDING_MS = 900;
const SPEECH_RMS_THRESHOLD = 0.01;
const MIN_AUDIO_BYTES = 3000;
const AUDIO_STATE = {
  IDLE: "IDLE",
  LISTENING: "LISTENING",
  RECORDING: "RECORDING",
  PROCESSING: "PROCESSING",
  RESPONDING: "RESPONDING",
};

const state = {
  config: null,
  platformConfig: null,
  activeAgentId: "code_assistant",
  inputMode: "agent",
  preferredResponseLanguage: "Hinglish",
  transcriptionLanguage: "Auto",
  mediaRecorder: null,
  chunks: [],
  selectedContext: null,
  lastRequest: null,
  lastResponse: null,
  lastProposal: null,
  audioState: AUDIO_STATE.IDLE,
  sleepTimer: null,
  sleepUntil: 0,
  recordingStopTimer: null,
  silenceTimer: null,
  recordingStartedAt: 0,
  lastSpeechAt: 0,
  hasDetectedSpeech: false,
  audioContext: null,
  activeAudio: null,
  localSpeechVoice: null,
  responsePlaybackToken: 0,
  handledResponseIds: new Set(),
  music: {
    enabled: true,
    started: false,
    context: null,
    masterGain: null,
    delay: null,
    feedback: null,
    filter: null,
    timers: [],
  },
};

init();

async function init() {
  state.config = await window.codeDuck.getConfig();
  await loadPlatformConfig();
  state.localSpeechVoice = await getPreferredSpeechVoice();
  setAudioState(AUDIO_STATE.IDLE);
  window.codeDuck.onShortcut((context) => startVoiceFlow(context));
  micButton.addEventListener("click", () => startVoiceFlow());
  closeButton.addEventListener("click", closeConversation);
  chooseRootButton.addEventListener("click", chooseProjectRootAndRetry);
  selectedOnlyButton.addEventListener("click", continueSelectedOnly);
  cancelRootButton.addEventListener("click", cancelProjectRootPrompt);
  applyButton.addEventListener("click", applyPatch);
  modifyButton.addEventListener("click", () => modifyBox.classList.toggle("hidden"));
  copyPatchButton.addEventListener("click", copyPatch);
  cancelPatchButton.addEventListener("click", cancelPatchPanel);
  sendModifyButton.addEventListener("click", sendModifyRequest);
  settingsButton.addEventListener("click", () => settingsPanel.classList.remove("hidden"));
  closeSettingsButton.addEventListener("click", () => settingsPanel.classList.add("hidden"));
  modeSelect.addEventListener("change", () => updatePlatformPreference({ inputMode: modeSelect.value }));
  agentSelect.addEventListener("change", () => updatePlatformPreference({ activeAgentId: agentSelect.value }));
  languageSelect.addEventListener("change", () => updatePlatformPreference({
    language: { preferredResponseLanguage: languageSelect.value },
  }));
  musicButton.addEventListener("click", toggleFocusMusic);
  document.addEventListener("pointerdown", startFocusMusicOnce, { once: true });
  document.addEventListener("keydown", startFocusMusicOnce, { once: true });
  initParticleSphere();
  await resizeApp();
}

async function loadPlatformConfig() {
  try {
    const response = await fetch(`${state.config.serviceUrl}/platform/config`);
    if (!response.ok) throw new Error(`Config request failed: ${response.status}`);
    state.platformConfig = await response.json();
  } catch (error) {
    addMessage("Settings", error.message || String(error), "warning");
    state.platformConfig = {
      app: {
        activeAgentId: "code_assistant",
        inputMode: "agent",
        language: {
          preferredResponseLanguage: "Hinglish",
          transcriptionLanguage: "Auto",
          keepTechnicalTermsEnglish: true,
        },
      },
      agents: { agents: [] },
    };
  }

  const appConfig = state.platformConfig.app || {};
  state.activeAgentId = appConfig.activeAgentId || "code_assistant";
  state.inputMode = appConfig.inputMode || "agent";
  state.preferredResponseLanguage = appConfig.language?.preferredResponseLanguage || "Hinglish";
  state.transcriptionLanguage = appConfig.language?.transcriptionLanguage || "Auto";
  populatePlatformControls();
}

function populatePlatformControls() {
  if (modeSelect) modeSelect.value = state.inputMode;
  if (languageSelect) languageSelect.value = state.preferredResponseLanguage;
  if (!agentSelect) return;
  agentSelect.innerHTML = "";
  const agents = state.platformConfig?.agents?.agents || [];
  for (const agent of agents) {
    const option = document.createElement("option");
    option.value = agent.agentId;
    option.textContent = `${agent.name} · ${agent.type}`;
    agentSelect.appendChild(option);
  }
  if (!agents.some((agent) => agent.agentId === state.activeAgentId)) {
    const fallback = document.createElement("option");
    fallback.value = state.activeAgentId;
    fallback.textContent = activeAgentName();
    agentSelect.appendChild(fallback);
  }
  agentSelect.value = state.activeAgentId;
}

async function updatePlatformPreference(update) {
  if (update.activeAgentId) state.activeAgentId = update.activeAgentId;
  if (update.inputMode) state.inputMode = update.inputMode;
  if (update.language?.preferredResponseLanguage) {
    state.preferredResponseLanguage = update.language.preferredResponseLanguage;
  }
  try {
    const response = await fetch(`${state.config.serviceUrl}/platform/config/app`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    });
    if (response.ok) {
      const appConfig = await response.json();
      state.platformConfig = {
        ...(state.platformConfig || {}),
        app: appConfig,
      };
    }
  } catch (error) {
    addMessage("Settings", error.message || String(error), "warning");
  }
  setAudioState(AUDIO_STATE.IDLE);
}

async function startVoiceFlow(preCapturedContext) {
  if (state.audioState !== AUDIO_STATE.IDLE) {
    if (state.audioState === AUDIO_STATE.RESPONDING) {
      stopCurrentSpeech();
    } else {
      return;
    }
  }

  startFocusMusicOnce();
  stopCurrentSpeech();
  wakeFromSleep();
  clearPanels();
  setExpanded(false);
  setAudioState(AUDIO_STATE.LISTENING, "Capturing context");
  try {
    state.selectedContext = preCapturedContext || await window.codeDuck.captureSelection();
    const selectedText = state.selectedContext.selectedText || "";
    contextEl.textContent = selectedText
      ? `Selected ${selectedText.split(/\r?\n/).length} line(s)${labelSuffix(state.selectedContext)}`
      : "No selected text captured";
  } catch (error) {
    addMessage("Selection", error.message || String(error), "warning");
    state.selectedContext = {};
  }

  await startRecording({ explicitTrigger: true });
}

async function startRecording(options = {}) {
  if (state.mediaRecorder && state.mediaRecorder.state === "recording") return;
  stopCurrentSpeech();
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: audioCaptureConstraints() });
    state.chunks = [];
    state.recordingStartedAt = Date.now();
    state.lastSpeechAt = state.recordingStartedAt;
    state.hasDetectedSpeech = false;
    state.mediaRecorder = new MediaRecorder(stream);
    state.mediaRecorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) state.chunks.push(event.data);
    });
    state.mediaRecorder.addEventListener("stop", async () => {
      const hadSpeech = state.hasDetectedSpeech;
      clearRecordingTimers();
      closeAudioContext();
      stream.getTracks().forEach((track) => track.stop());
      if (!hadSpeech) {
        handleNoSpeechDetected();
        return;
      }
      await sendAudioRequest();
    });
    state.mediaRecorder.start(250);
    appEl.classList.add("recording");
    setAudioState(AUDIO_STATE.RECORDING, options.explicitTrigger ? "Speak now" : "");
    await resizeApp();
    state.recordingStopTimer = setTimeout(() => stopRecording(), RECORDING_MAX_MS);
    startSilenceDetection(stream);
  } catch (error) {
    addMessage("Microphone", error.message || String(error), "error");
    setAudioState(AUDIO_STATE.IDLE, "Microphone unavailable");
    setExpanded(true);
    await resizeApp();
  }
}

function stopRecording() {
  if (state.mediaRecorder && state.mediaRecorder.state === "recording") {
    const hadSpeech = state.hasDetectedSpeech;
    state.mediaRecorder.stop();
    appEl.classList.remove("recording");
    if (hadSpeech) {
      setAudioState(AUDIO_STATE.PROCESSING, "Transcribing");
    } else {
      setAudioState(AUDIO_STATE.IDLE, `Shortcut: ${state.config.shortcut}`);
    }
  }
}

function handleNoSpeechDetected() {
  state.chunks = [];
  appEl.classList.remove("recording");
  clearRecordingTimers();
  setAudioState(AUDIO_STATE.IDLE, "No speech detected. Press mic to try again.");
}

async function speakLocal(text) {
  try {
    const response = await fetch(`${state.config.serviceUrl}/tts/synthesize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (response.ok) {
      const payload = await response.json();
      if (payload.audioBase64) {
        await playAudioAsync(payload.audioBase64, payload.audioMimeType);
        return;
      }
    }
  } catch {
    // Fall back to the OS voice below.
  }

  return new Promise((resolve) => {
    if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) {
      resolve();
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    if (state.localSpeechVoice) {
      utterance.voice = state.localSpeechVoice;
      utterance.lang = state.localSpeechVoice.lang || "en-US";
    }
    utterance.rate = 1;
    utterance.pitch = 1.08;
    utterance.volume = 1;
    utterance.onend = () => { resolve(); };
    utterance.onerror = () => { resolve(); };
    window.speechSynthesis.speak(utterance);
  });
}


function startFocusMusicOnce() {
  if (!state.music.enabled || state.music.started) return;
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return;

  const context = new AudioContextClass();
  const masterGain = context.createGain();
  const filter = context.createBiquadFilter();
  const delay = context.createDelay(6);
  const feedback = context.createGain();

  masterGain.gain.value = 0.018;
  filter.type = "lowpass";
  filter.frequency.value = 1250;
  filter.Q.value = 0.45;
  delay.delayTime.value = 0.42;
  feedback.gain.value = 0.22;

  filter.connect(delay);
  delay.connect(feedback);
  feedback.connect(delay);
  filter.connect(masterGain);
  delay.connect(masterGain);
  masterGain.connect(context.destination);

  state.music.context = context;
  state.music.masterGain = masterGain;
  state.music.filter = filter;
  state.music.delay = delay;
  state.music.feedback = feedback;
  state.music.started = true;

  context.resume().catch(() => {});
  scheduleFocusMusicLoop();
}

function scheduleFocusMusicLoop() {
  if (!state.music.enabled || !state.music.context) return;
  const chord = chooseFocusChord();
  const now = state.music.context.currentTime;
  chord.forEach((frequency, index) => playSoftTone(frequency, now + index * 0.08, 7.5 + index * 0.8));
  const timer = setTimeout(scheduleFocusMusicLoop, 6200 + Math.random() * 1800);
  state.music.timers.push(timer);
}

function chooseFocusChord() {
  const chords = [
    [220.0, 277.18, 329.63],
    [196.0, 246.94, 293.66],
    [174.61, 220.0, 261.63],
    [246.94, 293.66, 369.99],
  ];
  return chords[Math.floor(Math.random() * chords.length)];
}

function playSoftTone(frequency, startAt, duration) {
  const context = state.music.context;
  if (!context || !state.music.filter) return;

  const oscillator = context.createOscillator();
  const gain = context.createGain();
  const pan = context.createStereoPanner ? context.createStereoPanner() : null;

  oscillator.type = "sine";
  oscillator.frequency.setValueAtTime(frequency, startAt);
  oscillator.frequency.linearRampToValueAtTime(frequency * (1.002 + Math.random() * 0.003), startAt + duration);

  gain.gain.setValueAtTime(0.0001, startAt);
  gain.gain.exponentialRampToValueAtTime(0.105, startAt + 1.4);
  gain.gain.exponentialRampToValueAtTime(0.0001, startAt + duration);

  if (pan) {
    pan.pan.setValueAtTime(-0.28 + Math.random() * 0.56, startAt);
    oscillator.connect(gain);
    gain.connect(pan);
    pan.connect(state.music.filter);
  } else {
    oscillator.connect(gain);
    gain.connect(state.music.filter);
  }

  oscillator.start(startAt);
  oscillator.stop(startAt + duration + 0.2);
}

function toggleFocusMusic() {
  state.music.enabled = !state.music.enabled;
  musicButton.classList.toggle("music-off", !state.music.enabled);
  musicButton.classList.toggle("music-on", state.music.enabled);
  musicButton.title = state.music.enabled ? "Focus music on" : "Focus music off";

  if (state.music.enabled) {
    if (state.music.masterGain) {
      state.music.masterGain.gain.setTargetAtTime(0.018, state.music.context.currentTime, 0.35);
    }
    startFocusMusicOnce();
    return;
  }

  for (const timer of state.music.timers) clearTimeout(timer);
  state.music.timers = [];
  if (state.music.masterGain && state.music.context) {
    state.music.masterGain.gain.setTargetAtTime(0.0001, state.music.context.currentTime, 0.25);
  }
}

function getPreferredSpeechVoice() {
  return new Promise((resolve) => {
    if (!("speechSynthesis" in window)) {
      resolve(null);
      return;
    }

    const choose = () => {
      const voices = window.speechSynthesis.getVoices();
      if (!voices.length) return null;
      const preferredNames = [
        "Samantha",
        "Ava",
        "Victoria",
        "Susan",
        "Allison",
        "Karen",
        "Tessa",
        "Moira",
        "Fiona",
        "Zoe",
        "Serena",
      ];
      const preferred = voices.find((voice) =>
        preferredNames.some((name) => voice.name.toLowerCase().includes(name.toLowerCase())),
      );
      if (preferred) return preferred;
      return voices.find((voice) => /^en[-_]/i.test(voice.lang)) || voices[0];
    };

    const voice = choose();
    if (voice) {
      resolve(voice);
      return;
    }

    const timer = setTimeout(() => resolve(choose()), 1000);
    window.speechSynthesis.onvoiceschanged = () => {
      clearTimeout(timer);
      resolve(choose());
    };
  });
}

function startSilenceDetection(stream) {
  if (!("AudioContext" in window || "webkitAudioContext" in window)) return;
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  state.audioContext = new AudioContextClass();
  const source = state.audioContext.createMediaStreamSource(stream);
  const analyser = state.audioContext.createAnalyser();
  analyser.fftSize = 2048;
  source.connect(analyser);
  const samples = new Float32Array(analyser.fftSize);

  const check = () => {
    if (!state.mediaRecorder || state.mediaRecorder.state !== "recording") return;
    analyser.getFloatTimeDomainData(samples);
    const rms = calculateRms(samples);
    const now = Date.now();
    if (rms >= SPEECH_RMS_THRESHOLD) {
      state.hasDetectedSpeech = true;
      state.lastSpeechAt = now;
    }

    const recordingAge = now - state.recordingStartedAt;
    const quietAfterSpeech = state.hasDetectedSpeech && now - state.lastSpeechAt >= END_SILENCE_MS && recordingAge >= MIN_RECORDING_MS;
    const noSpeechYet = !state.hasDetectedSpeech && recordingAge >= INITIAL_SILENCE_MS;
    if (quietAfterSpeech || noSpeechYet) {
      stopRecording();
      return;
    }
    state.silenceTimer = setTimeout(check, 120);
  };

  state.silenceTimer = setTimeout(check, 120);
}

function calculateRms(samples) {
  let sum = 0;
  for (const sample of samples) {
    sum += sample * sample;
  }
  return Math.sqrt(sum / samples.length);
}

function clearRecordingTimers() {
  if (state.recordingStopTimer) {
    clearTimeout(state.recordingStopTimer);
    state.recordingStopTimer = null;
  }
  if (state.silenceTimer) {
    clearTimeout(state.silenceTimer);
    state.silenceTimer = null;
  }
}

function closeAudioContext() {
  if (!state.audioContext) return;
  state.audioContext.close().catch(() => {});
  state.audioContext = null;
}

async function sendAudioRequest() {
  const blob = new Blob(state.chunks, { type: state.mediaRecorder.mimeType || "audio/webm" });
  if (blob.size < MIN_AUDIO_BYTES) {
    state.chunks = [];
    setAudioState(AUDIO_STATE.IDLE, "No usable speech detected.");
    return;
  }
  const audioBase64 = await blobToBase64(blob);
  const request = createRequest({
    inputType: "audio",
    audioBase64,
    mimeType: blob.type,
    audioDurationMs: Date.now() - state.recordingStartedAt,
    audioSizeBytes: blob.size,
  });
  await streamRequest(request);
}

async function streamRequest(request) {
  state.lastRequest = request;
  state.handledResponseIds.delete(request.requestId);
  setAudioState(AUDIO_STATE.PROCESSING, "Processing...");
  try {
    const response = await fetch(`${state.config.serviceUrl}/agent/respond/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    if (!response.ok || !response.body) {
      throw new Error(`Backend returned ${response.status}`);
    }
    await readSseStream(response.body);
  } catch (error) {
    addMessage("Backend", error.message || String(error), "error");
    setAudioState(AUDIO_STATE.IDLE);
    setExpanded(true);
    await resizeApp();
  }
}

async function readSseStream(body) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const line = part.split("\n").find((item) => item.startsWith("data: "));
      if (!line) continue;
      handleStreamEvent(JSON.parse(line.slice(6)));
    }
  }
}

function handleStreamEvent(event) {
  if (event.event === "status") {
    setStatus(event.message || "Working");
    return;
  }
  if (event.event === "transcript") {
    const transcript = event.data.transcript || event.message || "";
    if (isLikelySilenceTranscript(transcript)) {
      return;
    }
    addMessage("You", transcript);
    if (isImmediateQuitCommand(transcript)) {
      stopCurrentSpeech();
      setStatus("Closing", "Stopping Neha");
      setTimeout(() => window.codeDuck.quitApp(), 150);
      return;
    }
    setExpanded(true);
    resizeApp();
    return;
  }
  if (event.event === "test_log") {
    addMessage("Test", event.data.chunk || event.message || "");
    setExpanded(true);
    resizeApp();
    return;
  }
  if (event.event === "error") {
    const response = event.data && event.data.response;
    if (response) handleFinalResponse(response);
    else addMessage("Error", event.message || "Request failed", "error");
    return;
  }
  if (event.event === "final") {
    handleFinalResponse(event.data.response);
  }
}

function handleFinalResponse(response) {
  if (!response || state.handledResponseIds.has(response.requestId)) return;
  state.handledResponseIds.add(response.requestId);
  state.lastResponse = response;
  if (isEmptyTranscriptResponse(response)) {
    setAudioState(AUDIO_STATE.IDLE, "No speech detected. Press mic to try again.");
    setExpanded(true);
    resizeApp();
    return;
  }
  if (shouldIgnoreUnaddressedSpeech(response)) {
    addMessage(
      state.config.agentName,
      "I heard that.",
      "warning",
    );
    setAudioState(AUDIO_STATE.IDLE);
    setExpanded(true);
    resizeApp();
    return;
  }
  setStatus(labelForState(response.uiState));
  if (response.transcript) addMessage("Transcript", response.transcript);
  if (response.warnings && response.warnings.length) {
    addMessage("Warnings", response.warnings.join("\n"), "warning");
  }
  if (!response.ok) {
    addMessage("Error", response.error ? response.error.message : "Request failed", "error");
    setAudioState(AUDIO_STATE.IDLE);
    setExpanded(true);
    resizeApp();
    return;
  }
  const quitResponse = isQuitResponse(response);
  if (quitResponse) {
    addMessage(state.config.agentName, response.answer || "Okay, I am shutting myself down.");
    setStatus("Shutting down", "Neha is closing");
    setExpanded(true);
    resizeApp();
    const finishQuit = () => {
      playShutdownTone().finally(() => window.codeDuck.quitApp());
    };
    if (response.audioBase64) {
      setScene({ state: "paused", activity: "Shutting down", hint: response.answer || "Neha is closing." });
      window.codeDuck.updatePresence({ state: "paused", status: "Shutting down", context: response.answer || "" }).catch(() => {});
      playAudio(response.audioBase64, response.audioMimeType, finishQuit);
    } else {
      speakLocal(response.answer || "Okay, I am shutting myself down.").then(finishQuit);
    }
    return;
  }
  if (isStopResponse(response)) {
    enterSleep(0, "Sleeping", "Press the shortcut to wake me");
  } else if (isSleepResponse(response)) {
    const sleepMs = Number(response.sleepMs) || SLEEP_MS;
    enterSleep(sleepMs, "Paused", `I’ll stay quiet for ${formatSleepDuration(sleepMs)}, or press the shortcut to wake me`);
  }
  if (response.uiState === "needs_project_root") {
    showProjectRootPrompt(response);
  } else if (response.uiState === "patch_preview") {
    showPatch(response);
  } else if (response.uiState === "dictation_result") {
    addMessage("Dictation", response.draftText || response.answer || "");
    runApprovedActions(response);
  } else if (response.uiState === "draft_preview") {
    addMessage(activeAgentName(response.activeAgentId), response.draftText || response.answer || "");
  } else if (response.uiState === "test_result") {
    addMessage("Tests", response.answer || "Tests finished");
  } else {
    addMessage(activeAgentName(response.activeAgentId), response.answer || "");
  }
  if (response.audioBase64) {
    setAudioState(AUDIO_STATE.RESPONDING, response.answer || "Responding...");
    setScene({ state: "speaking", activity: "Painting the answer", hint: response.answer || "Neha is speaking." });
    window.codeDuck.updatePresence({ state: "speaking", status: "Speaking", context: response.answer || "" }).catch(() => {});
    playAudio(response.audioBase64, response.audioMimeType, () => {
      setAudioState(AUDIO_STATE.IDLE);
    });
  } else {
    setAudioState(AUDIO_STATE.IDLE);
  }
  setExpanded(true);
  resizeApp();
}

function createRequest(overrides = {}) {
  const context = {
    source: "clipboard",
    selectedText: state.selectedContext?.selectedText || "",
    surroundingText: "",
    languageId: state.selectedContext?.languageId || "",
    fileName: state.selectedContext?.fileName || "",
    filePath: state.selectedContext?.filePath || "",
    projectRoot: state.selectedContext?.projectRoot || "",
    projectRootApproved: Boolean(state.selectedContext?.projectRootApproved),
    selectedOnly: Boolean(state.selectedContext?.selectedOnly),
    selectedRange: "",
    activeApp: state.selectedContext?.activeApp || "",
    windowTitle: state.selectedContext?.windowTitle || "",
    focusedInputType: state.selectedContext?.focusedInputType || "",
    meetingDetected: Boolean(state.selectedContext?.meetingDetected),
  };
  return {
    requestId: crypto.randomUUID(),
    sessionId: "default",
    activeAgentId: state.activeAgentId,
    inputMode: state.inputMode,
    preferredResponseLanguage: state.preferredResponseLanguage,
    transcriptionLanguage: state.transcriptionLanguage,
    explicitTrigger: true,
    inputType: "text",
    commandText: "",
    audioBase64: "",
    mimeType: "",
    context,
    previousProposal: state.lastProposal
      ? {
          proposalId: state.lastProposal.proposalId,
          intent: state.lastResponse?.intent || "unknown",
          originalCode: state.lastProposal.originalCode,
          proposedCode: state.lastProposal.proposedCode,
          diff: state.lastProposal.diff,
        }
      : null,
    execution: {
      allowTestRun: false,
      workingDirectory: "",
      testCommand: [],
      testIterations: 1,
    },
    ...overrides,
    context: { ...context, ...(overrides.context || {}) },
  };
}

async function runApprovedActions(response) {
  const actions = response.actionPlans || [];
  for (const action of actions) {
    if (action.requiresApproval) continue;
    if (action.type === "paste_to_focused_app") {
      const text = action.payload?.text || response.draftText || response.answer || "";
      if (text && window.codeDuck.pasteText) {
        const result = await window.codeDuck.pasteText(text);
        addMessage("Action", result.message || "Text pasted.", result.ok ? "" : "error");
      }
    }
  }
}

function showProjectRootPrompt(response) {
  projectRootMessage.textContent = response.answer || "Choose the project folder for better fixes.";
  projectRootPrompt.classList.remove("hidden");
}

function hideProjectRootPrompt() {
  projectRootPrompt.classList.add("hidden");
  resizeApp();
}

function cancelProjectRootPrompt() {
  hideProjectRootPrompt();
  addMessage(state.config.agentName, "Okay, I will not open the folder.");
  setAudioState(AUDIO_STATE.IDLE);
}

async function chooseProjectRootAndRetry() {
  const result = await window.codeDuck.chooseProjectRoot();
  if (result.canceled) return;
  state.selectedContext = {
    ...(state.selectedContext || {}),
    projectRoot: result.projectRoot,
    projectRootApproved: true,
    selectedOnly: false,
  };
  hideProjectRootPrompt();
  const request = createRequest({
    inputType: "text",
    commandText: state.lastResponse?.transcript || state.lastRequest?.commandText || "",
  });
  await streamRequest(request);
}

async function continueSelectedOnly() {
  state.selectedContext = {
    ...(state.selectedContext || {}),
    selectedOnly: true,
    projectRoot: "",
    projectRootApproved: false,
  };
  hideProjectRootPrompt();
  const request = createRequest({
    inputType: "text",
    commandText: state.lastResponse?.transcript || state.lastRequest?.commandText || "",
  });
  await streamRequest(request);
}

function showPatch(response) {
  state.lastProposal = response.proposal;
  addMessage(state.config.agentName, response.answer || "Review the proposed replacement.");
  diffView.textContent = response.proposal?.diff || "";
  patchPanel.classList.remove("hidden");
  modifyBox.classList.add("hidden");
}

function hidePatchPanel() {
  patchPanel.classList.add("hidden");
  resizeApp();
}

function cancelPatchPanel() {
  hidePatchPanel();
  addMessage(state.config.agentName, "Okay, I cancelled that change.");
  setAudioState(AUDIO_STATE.IDLE);
}

async function applyPatch() {
  if (!state.lastProposal) return;
  const result = await window.codeDuck.applyReplacement(state.lastProposal.proposedCode);
  addMessage("Apply", result.message, result.ok ? "" : "error");
  setExpanded(true);
  resizeApp();
}

async function copyPatch() {
  if (!state.lastProposal) return;
  await window.codeDuck.writeClipboardText(state.lastProposal.proposedCode);
  addMessage("Patch", "Replacement copied.");
}

async function sendModifyRequest() {
  const commandText = modifyText.value.trim();
  if (!commandText) return;
  const request = createRequest({
    inputType: "text",
    commandText,
  });
  modifyText.value = "";
  modifyBox.classList.add("hidden");
  await streamRequest(request);
}

function addMessage(label, text, kind = "") {
  if (!text) return;
  const node = document.createElement("div");
  node.className = `message ${kind}`;
  node.innerHTML = '<div class="label"></div><div class="text"></div>';
  node.querySelector(".label").textContent = label;
  node.querySelector(".text").textContent = text;
  messagesEl.appendChild(node);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function clearPanels() {
  messagesEl.innerHTML = "";
  projectRootPrompt.classList.add("hidden");
  patchPanel.classList.add("hidden");
}

function setStatus(status, context) {
  statusEl.textContent = status;
  if (context) contextEl.textContent = context;
  const presence = sceneForStatus(status, context);
  setScene(presence);
  window.codeDuck.updatePresence({
    state: presence.state,
    status,
    context: contextEl.textContent,
  }).catch(() => {});
}

function setAudioState(next, context = "") {
  state.audioState = next;

  if (next === AUDIO_STATE.IDLE) {
    setStatus("Ready", context || readyContext());
  }

  if (next === AUDIO_STATE.LISTENING) {
    setStatus("Listening", context || "Listening...");
  }

  if (next === AUDIO_STATE.RECORDING) {
    setStatus("Listening", context || "Speak now");
  }

  if (next === AUDIO_STATE.PROCESSING) {
    setStatus("Thinking", context || "Processing...");
  }

  if (next === AUDIO_STATE.RESPONDING) {
    setStatus("Answer ready", context || "Responding...");
  }
}

function readyContext() {
  const mode = state.inputMode === "dictation" ? "Dictation" : state.inputMode === "meeting" ? "Meeting" : activeAgentName();
  return `${mode} · ${state.preferredResponseLanguage} · Shortcut: ${state.config.shortcut}`;
}

function activeAgentName(agentId = state.activeAgentId) {
  const agents = state.platformConfig?.agents?.agents || [];
  return agents.find((agent) => agent.agentId === agentId)?.name || state.config.agentName || "Neha";
}

function setScene(presence) {
  const sceneClasses = ["scene-idle", "scene-listening", "scene-thinking", "scene-speaking", "scene-working", "scene-sleeping", "scene-paused"];
  appEl.classList.remove(...sceneClasses);
  appEl.classList.add(`scene-${presence.state}`);
  if (sceneActivity) sceneActivity.textContent = presence.activity;
  if (sceneHint) sceneHint.textContent = presence.hint;
}

function sceneForStatus(status, context) {
  const value = String(status || "").toLowerCase();
  if (value.includes("listen") || value.includes("awake")) {
    return {
      state: "listening",
      activity: "Listening with a soft touch",
      hint: context || "Speak naturally. Neha will keep the conversation open.",
    };
  }
  if (value.includes("think") || value.includes("transcrib") || value.includes("generating")) {
    return {
      state: "thinking",
      activity: "Knitting the thought together",
      hint: context || "Neha is shaping the next response.",
    };
  }
  if (value.includes("test") || value.includes("capturing") || value.includes("working")) {
    return {
      state: "working",
      activity: "Hands quietly making progress",
      hint: context || "Neha is working through the request.",
    };
  }
  if (value.includes("sleep")) {
    return {
      state: "sleeping",
      activity: "Resting until you call",
      hint: context || "Use the bubble or shortcut to wake Neha.",
    };
  }
  if (value.includes("paused")) {
    return {
      state: "paused",
      activity: "Paused and staying quiet",
      hint: context || "Neha will wait for the requested time.",
    };
  }
  if (value.includes("conversation active") || value.includes("answer")) {
    return {
      state: "speaking",
      activity: "Painting the answer",
      hint: context || "You can continue the conversation.",
    };
  }
  return {
    state: "idle",
    activity: "Waiting gently",
    hint: context || "The bubble stays available on your desktop.",
  };
}

function setExpanded(expanded) {
  appEl.classList.toggle("expanded", expanded);
}

async function resizeApp() {
  await window.codeDuck.resizeWindow({ width: 1120, height: 760 });
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(String(reader.result).split(",")[1] || "");
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

function playAudioAsync(audioBase64, mimeType) {
  return new Promise((resolve) => playAudio(audioBase64, mimeType, resolve));
}

function playAudio(audioBase64, mimeType, onEnded) {
  const playbackToken = ++state.responsePlaybackToken;
  const audio = new Audio(`data:${mimeType || "audio/wav"};base64,${audioBase64}`);
  state.activeAudio = audio;
  let finished = false;
  const finish = () => {
    if (finished) return;
    if (playbackToken !== state.responsePlaybackToken) return;
    finished = true;
    if (state.activeAudio === audio) state.activeAudio = null;
    clearTimeout(fallbackTimer);
    if (typeof onEnded === "function") onEnded();
  };
  const fallbackTimer = setTimeout(finish, 45000);
  audio.addEventListener("ended", finish, { once: true });
  audio.play().catch((error) => {
    addMessage("Audio", error.message, "warning");
    finish();
  });
}

function playShutdownTone() {
  stopFocusMusicForShutdown();
  return new Promise((resolve) => {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) {
      setTimeout(resolve, 250);
      return;
    }

    const context = new AudioContextClass();
    const now = context.currentTime;
    const master = context.createGain();
    master.gain.setValueAtTime(0.0001, now);
    master.gain.exponentialRampToValueAtTime(0.11, now + 0.04);
    master.gain.exponentialRampToValueAtTime(0.0001, now + 1.05);
    master.connect(context.destination);

    [659.25, 523.25, 392.0].forEach((frequency, index) => {
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      const startAt = now + index * 0.18;
      oscillator.type = "sine";
      oscillator.frequency.setValueAtTime(frequency, startAt);
      gain.gain.setValueAtTime(0.0001, startAt);
      gain.gain.exponentialRampToValueAtTime(0.75, startAt + 0.04);
      gain.gain.exponentialRampToValueAtTime(0.0001, startAt + 0.42);
      oscillator.connect(gain);
      gain.connect(master);
      oscillator.start(startAt);
      oscillator.stop(startAt + 0.48);
    });

    setTimeout(() => {
      context.close().catch(() => {});
      resolve();
    }, 1150);
  });
}

function stopFocusMusicForShutdown() {
  for (const timer of state.music.timers) clearTimeout(timer);
  state.music.timers = [];
  if (state.music.masterGain && state.music.context) {
    state.music.masterGain.gain.setTargetAtTime(0.0001, state.music.context.currentTime, 0.18);
  }
}

function stopCurrentSpeech() {
  state.responsePlaybackToken += 1;
  if (state.activeAudio) {
    state.activeAudio.pause();
    state.activeAudio.currentTime = 0;
    state.activeAudio = null;
  }
  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
}

function audioCaptureConstraints() {
  return {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  };
}

function formatSleepDuration(ms) {
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds} seconds`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"}`;
  const hours = Math.round((minutes / 60) * 10) / 10;
  return `${hours} hour${hours === 1 ? "" : "s"}`;
}

function isQuitResponse(response) {
  return Array.isArray(response.actions) && response.actions.includes("quit_app");
}

function isStopResponse(response) {
  return response.uiState === "answer"
    && Array.isArray(response.actions)
    && response.actions.length === 1
    && response.actions[0] === "close";
}

function isSleepResponse(response) {
  return response.uiState === "answer"
    && Array.isArray(response.actions)
    && response.actions.includes("sleep");
}

function isEmptyTranscriptResponse(response) {
  return response.ok === false && response.error && response.error.code === "empty_transcript";
}

function isLikelySilenceTranscript(text) {
  const normalized = String(text || "")
    .toLowerCase()
    .replace(/[^a-z0-9' ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return !normalized || ["uh", "um", "hm", "hmm", "you"].includes(normalized);
}

function shouldIgnoreUnaddressedSpeech(response) {
  // Once the user has woken the agent, keep the exchange human-like: every
  // follow-up inside the conversation window is addressed to the agent. The
  // wake word is only needed to start a new session, not before every sentence.
  return false;
}

function normalizeVoiceCommand(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/[’]/g, "'")
    .replace(/[^a-z0-9' ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function isImmediateQuitCommand(text) {
  const command = normalizeVoiceCommand(text);
  return [
    "force quit",
    "quit immediately",
    "exit immediately",
  ].includes(command);
}

function mentionsAgentName(transcript) {
  const name = String(state.config.agentName || "Neha").toLowerCase();
  return transcript.includes(name) || transcript.includes("code duck") || transcript.includes("codeduck");
}

function looksLikeCodingCommand(transcript) {
  return [
    "explain",
    "fix",
    "debug",
    "review",
    "refactor",
    "change",
    "replace",
    "test",
    "what does",
    "what is",
    "why",
    "how",
    "tell me",
    "this line",
    "this code",
    "samjha",
    "bata",
  ].some((phrase) => transcript.includes(phrase));
}

function looksLikeConversationalFollowUp(transcript) {
  return [
    "yes",
    "no",
    "continue",
    "go on",
    "tell me more",
    "shorter",
    "in short",
    "again",
    "repeat",
    "apply",
    "cancel",
    "okay",
    "ok",
    "thanks",
    "thank you",
    "hello",
    "hi",
    "hey",
    "who are you",
    "what is your name",
    "pronounce your name",
    "can you talk",
    "do you only talk",
  ].some((phrase) => transcript === phrase || transcript.includes(phrase) || transcript.startsWith(`${phrase} `));
}

function enterSleep(durationMs, status, context) {
  state.audioState = AUDIO_STATE.IDLE;
  state.sleepUntil = durationMs > 0 ? Date.now() + durationMs : 0;
  clearSleepTimer();
  setStatus(status, context);
  appEl.classList.remove("recording");
  if (durationMs > 0) {
    state.sleepTimer = setTimeout(() => {
      state.sleepUntil = 0;
      state.sleepTimer = null;
      setStatus("Ready", `Shortcut: ${state.config.shortcut}`);
    }, durationMs);
  }
}

function wakeFromSleep() {
  if (!isSleeping()) return;
  state.sleepUntil = 0;
  clearSleepTimer();
}

function isSleeping() {
  return state.sleepUntil > Date.now();
}

function clearSleepTimer() {
  if (!state.sleepTimer) return;
  clearTimeout(state.sleepTimer);
  state.sleepTimer = null;
}

function closeConversation() {
  enterSleep(0, "Sleeping", "Press the shortcut to wake me");
  window.codeDuck.closePanel();
}

function labelForState(uiState) {
  if (uiState === "needs_project_root") return "Project folder needed";
  if (uiState === "patch_preview") return "Patch preview";
  if (uiState === "dictation_result") return "Dictation ready";
  if (uiState === "draft_preview") return "Draft ready";
  if (uiState === "meeting_summary") return "Meeting summary";
  if (uiState === "test_result") return "Tests finished";
  if (uiState === "error") return "Error";
  return "Answer ready";
}

function labelSuffix(context) {
  const parts = [];
  if (context.languageId) parts.push(context.languageId);
  if (context.fileName) parts.push(context.fileName);
  if (context.activeApp) parts.push(context.activeApp);
  return parts.length ? ` · ${parts.join(" · ")}` : "";
}

function isTerminalSource(context) {
  const appName = String(context?.activeApp || "").toLowerCase();
  return ["terminal", "iterm", "iterm2", "warp", "wezterm", "kitty", "alacritty"].some((name) => appName.includes(name));
}


function initParticleSphere() {
  const stage = document.getElementById("visualStage");
  if (!stage || stage.querySelector("canvas.particle-sphere")) return;

  const canvas = document.createElement("canvas");
  canvas.className = "particle-sphere";
  stage.appendChild(canvas);

  const ctx = canvas.getContext("2d");
  const particles = [];
  const particleCount = 1550;
  let width = 0;
  let height = 0;
  let radius = 0;
  let frame = 0;

  function resize() {
    const rect = stage.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = Math.max(1, Math.floor(rect.width));
    height = Math.max(1, Math.floor(rect.height));
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    radius = Math.min(width, height) * 0.28;
  }

  function createParticles() {
    particles.length = 0;
    for (let i = 0; i < particleCount; i += 1) {
      const u = Math.random();
      const v = Math.random();
      const theta = Math.PI * 2 * u;
      const phi = Math.acos(2 * v - 1);
      const jitter = 0.74 + Math.random() * 0.3;
      const x = Math.sin(phi) * Math.cos(theta) * jitter;
      const y = Math.cos(phi) * jitter;
      const z = Math.sin(phi) * Math.sin(theta) * jitter;
      particles.push({ x, y, z, size: 0.6 + Math.random() * 1.5, twinkle: Math.random() * Math.PI * 2 });
    }
  }

  function draw() {
    frame += 0.009;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "rgba(7, 9, 8, 0.96)";
    ctx.fillRect(0, 0, width, height);

    const cx = width * 0.5;
    const cy = height * 0.49;
    const sinY = Math.sin(frame * 0.72);
    const cosY = Math.cos(frame * 0.72);
    const sinX = Math.sin(frame * 0.33) * 0.32;
    const cosX = Math.cos(frame * 0.33) * 0.32 + 0.92;
    const perspective = radius * 3.2;

    for (const particle of particles) {
      const rx = particle.x * cosY - particle.z * sinY;
      const rz = particle.x * sinY + particle.z * cosY;
      const ry = particle.y * cosX - rz * sinX;
      const rz2 = particle.y * sinX + rz * cosX;
      const scale = perspective / (perspective - rz2 * radius);
      const px = cx + rx * radius * scale;
      const py = cy + ry * radius * scale;
      const depth = (rz2 + 1) / 2;
      const sparkle = Math.max(0, Math.sin(frame * 4.6 + particle.twinkle));
      const rareSparkle = sparkle > 0.965 ? (sparkle - 0.965) / 0.035 : 0;
      const alpha = Math.min(0.98, 0.24 + depth * 0.5 + sparkle * 0.16 + rareSparkle * 0.28);
      const size = particle.size * scale * (0.72 + depth * 0.62 + rareSparkle * 1.85);

      ctx.fillStyle = `rgba(246, 248, 244, ${alpha})`;
      ctx.beginPath();
      ctx.arc(px, py, size, 0, Math.PI * 2);
      ctx.fill();

      if (rareSparkle > 0) {
        const sparkleSize = size * (2.2 + rareSparkle * 1.4);
        ctx.strokeStyle = `rgba(255, 255, 255, ${0.34 + rareSparkle * 0.42})`;
        ctx.lineWidth = 0.7;
        ctx.beginPath();
        ctx.moveTo(px - sparkleSize, py);
        ctx.lineTo(px + sparkleSize, py);
        ctx.moveTo(px, py - sparkleSize);
        ctx.lineTo(px, py + sparkleSize);
        ctx.stroke();
      }
    }

    requestAnimationFrame(draw);
  }

  resize();
  createParticles();
  window.addEventListener("resize", resize);
  draw();
}
