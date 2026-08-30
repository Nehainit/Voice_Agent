# CodeDuck

CodeDuck is a local-first desktop voice coding agent. The MVP runs as a small always-on-top Electron pill: highlight code in any editor, trigger CodeDuck, speak your request, and get either an answer or a patch preview.

## Target Local Stack

Recommended for this machine:

- Speech-to-text: `faster-whisper` with `small.en`
- Coding model: `qwen2.5-coder:7b-instruct` through Ollama
- Text-to-speech: Kokoro
- App shell: Electron desktop pill
- Local service: Python FastAPI

## Product Behavior

CodeDuck is voice-first:

- No typed chat composer.
- The mic pill is the primary control.
- It captures highlighted code through the clipboard.
- For fixes, it can ask the user to choose a project folder.
- It previews replacement code and applies it only after user approval.
- It sleeps until the user wakes it with the shortcut or mic.
- The default agent name is `Neha`; during follow-up listening, calling her by name helps distinguish real commands from background speech.
- On wake, Neha says: "Hi, I am Neha. How can I help you?"
- Recording stops on a short silence after speech, with a max recording cap as backup.
- Saying "pause" puts it to sleep for 2 minutes. Saying "stop" ends the current listening loop.

The backend never edits files directly. Patch application happens through the Electron client by pasting the approved replacement into the active selection.

## Setup

Install the Ollama model:

```bash
ollama pull qwen2.5-coder:7b-instruct
```

Create a Python environment with Python 3.12. Do not use Python 3.14 for this project yet; some audio/ML dependencies are not ready there.

```bash
python3.12 -m venv local_service/.venv
source local_service/.venv/bin/activate
pip install -r local_service/requirements.txt
```

Start Ollama if it is not already running:

```bash
ollama serve
```

Start the local CodeDuck service. The default dev backend uses a lighter local LLM and Kokoro speech so the desktop app feels conversational:

```bash
source local_service/.venv/bin/activate
npm run dev:backend
```

For a silent lightweight run on a 16 GB MacBook Air:

```bash
npm run service:light
```

For spoken answers with the larger coding model, use this only when your system has enough free memory:

```bash
npm run service:voice
```

Install the Electron frontend dependencies:

```bash
npm install
```

Run the desktop pill in a second terminal:

```bash
npm run desktop
```

The default global shortcut is:

```text
CommandOrControl+Alt+K
```

On macOS, grant the terminal app Accessibility permission so CodeDuck can copy the selected code and paste approved patches. Grant Microphone permission when prompted.

## Current Features

- Electron floating pill.
- Global shortcut.
- Highlighted-code capture from the active app.
- Voice-only interaction.
- Browser MediaRecorder audio capture.
- Local FastAPI service.
- LangChain `ChatOllama` coding response.
- Optional Whisper transcription.
- Optional Kokoro speech output.
- Sleep/pause control commands before coding intent routing.
- Project-root prompt for code fixes.
- Patch preview with Apply, Modify, Copy, and Cancel actions.
- Streaming backend events for status, transcript, test logs, and final result.

## Environment Variables

The local service supports:

```bash
export OLLAMA_BASE_URL=http://127.0.0.1:11434
export OLLAMA_MODEL=qwen2.5-coder:7b-instruct
export OLLAMA_NUM_CTX=4096

export WHISPER_MODEL=small.en
export WHISPER_DEVICE=cpu
export WHISPER_COMPUTE_TYPE=int8

export CODEDUCK_TTS=1
export KOKORO_VOICE=af_heart
export KOKORO_LANG_CODE=a
```

The desktop shell supports:

```bash
export CODEDUCK_AGENT_NAME=Neha
export CODEDUCK_SHORTCUT=CommandOrControl+Alt+K
```

For a lighter run without voice output:

```bash
export CODEDUCK_TTS=0
```

## MVP Flow

```text
Select code in any editor
 -> trigger CodeDuck
 -> Neha greets the user
 -> speak the request
 -> recording stops after the user finishes speaking
 -> local service transcribes audio if needed
 -> control commands like stop/pause are handled first
 -> LangGraph-style backend routes answer vs patch
 -> answer returns directly, or patch asks for project root if needed
 -> short follow-up window stays active
 -> CodeDuck sleeps again when stopped, paused, or inactive
 -> patch preview is shown in Electron
 -> user approves before replacement is pasted
```

## Notes

The first request using Whisper or Kokoro can be slow because the model loads into memory. Later requests reuse the loaded model while the service is running.

If the Electron binary is reinstalled and macOS reports a broken app bundle, clear the generated `node_modules/electron/dist` folder, reinstall Electron, and verify `npm run check` before launching the desktop app.
