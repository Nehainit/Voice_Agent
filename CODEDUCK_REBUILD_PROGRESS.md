# CodeDuck Rebuild Progress

Goal: recreate this repo step by step with AI assistance while understanding the logic well enough to explain and modify it.

Progress: 0/8 phases complete.

## Phase Map

- [ ] 1. Repo map and core concept
- [ ] 2. Minimal FastAPI backend
- [ ] 3. Request/response contract with Pydantic
- [ ] 4. Intent routing graph
- [ ] 5. Ollama LLM integration
- [ ] 6. Audio input: browser recording to STT
- [ ] 7. Electron shell: shortcut, clipboard capture, patch preview
- [ ] 8. Safety layer: approvals, tests, settings, final polish

## Current Assignment

Phase 1: understand the existing repo shape and explain the main data flow.

Tasks:

1. Read `README.md`.
2. Read `docs/frontend-backend-contract.md` until the end of "Intent routing".
3. Skim these files only:
   - `local_service/app.py`
   - `local_service/agent_contract.py`
   - `local_service/agent_responder.py`
   - `local_service/agent_graph.py`
   - `electron/main.js`
   - `electron/preload.js`
   - `electron/renderer/renderer.js`
4. Write your own 10-15 line summary answering:
   - What does the Electron app own?
   - What does the FastAPI backend own?
   - What happens from pressing the shortcut to seeing an answer or patch?
   - Why does the backend return a patch preview instead of editing files directly?

Completion check:

- You can explain the flow without looking at the code.
- You can name the two most important backend files.
- You can name the two most important Electron files.

## Mentor Notes

- Rebuild scope is CodeDuck, not the large `dograh_local/dograh` reference tree.
- We will rebuild the smallest useful version first, then add voice, patching, and settings.
- AI can write chunks of code, but you must first describe the target behavior in plain English.
