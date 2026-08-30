# Coding Rubber Duck Agent - Product Note

## Product Concept

A voice-first coding companion that stays present on screen while a developer works. The agent behaves like a calm senior engineer or rubber duck: it helps the user reason through code, debug failures, review changes, and decide the next step.

The first version should be focused on developer utility, not a generic AI friend.

## Recommended MVP

Build a VS Code extension with a voice side panel.

Why VS Code first:
- Developers already work there.
- The extension can access selected code, open files, terminal output, and git diffs more naturally than a separate desktop app.
- It is easier to demo and validate quickly.

## Core Features

### 1. Floating / Side Panel Presence

- Small persistent UI inside VS Code.
- Push-to-talk mic button.
- Transcript of the conversation.
- Short text response from the agent.
- Optional spoken response using text-to-speech.

### 2. Voice Interaction

- Speech-to-text for developer questions.
- Text-to-speech for agent replies.
- Keep conversation history visible.
- Prefer concise responses with clear next steps.

### 3. Code Context

Initial context sources:
- Selected code.
- Current file.
- User-pasted error messages.

Later context sources:
- Terminal output.
- Git diff.
- Test results.
- Project file tree.

### 4. Debugging Mode

The agent should:
- Ask clarifying questions.
- Explain likely causes.
- Suggest hypotheses.
- Recommend the next command or test to run.
- Help the developer reason instead of only giving an answer.

### 5. Review Mode

The agent should review selected code or diffs for:
- Bugs.
- Missing edge cases.
- Naming issues.
- Complexity.
- Test gaps.
- Risky assumptions.

### 6. Explanation Mode

The agent should explain:
- What selected code does.
- How a function or module works.
- Why an error may be happening.
- What unfamiliar syntax or framework behavior means.

## Initial Voice Commands

- "Explain selected code."
- "Why is this error happening?"
- "Review this diff."
- "Help me debug this test."
- "What should I do next?"
- "Write a test for this function."
- "Summarize this file."

## Agent Personality

The agent should feel like a practical senior engineer:
- Calm.
- Direct.
- Curious.
- Concise.
- Focused on the next useful step.
- Comfortable saying when more context is needed.

Avoid making it overly emotional, overly chatty, or avatar-first. Utility should come before personality.

## Possible Product Names

- CodeDuck
- PairDuck
- VoicePair
- DebugMate
- DevCompanion
- RubberStack

## First Build Scope

Version 0 should include:
- VS Code extension.
- Side panel UI.
- Push-to-talk voice input.
- OpenAI API call using selected code as context.
- Text response in the panel.
- Optional text-to-speech response.
- Three modes: Explain, Debug, Review.

## Future Expansion

After validating the single-agent MVP, expand into a team of coding agents:
- Architect: design and architecture decisions.
- Debugger: failures, logs, and tests.
- Reviewer: code quality and PR review.
- Documenter: README, comments, API docs.
- DevOps helper: deploy, config, CI/CD issues.

Do not start with the team version. Start with one strong coding rubber duck agent.
