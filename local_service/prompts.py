MODE_INSTRUCTIONS = {
    "explain": "Explain the code clearly and briefly. Focus on what it does, the important flow, and any surprising behavior.",
    "debug": "Help debug the issue. Give likely causes, concrete checks, and the next command or code change to try.",
    "review": "Review like a senior engineer. Lead with bugs, edge cases, risks, and missing tests. Keep style feedback secondary.",
}


def build_prompt(mode: str, question: str, context: dict) -> str:
    selected_text = (context.get("selectedText") or "").strip()
    surrounding_text = (context.get("surroundingText") or "").strip()
    code_context = selected_text or surrounding_text or "No editor context was provided."
    language = context.get("languageId") or "unknown"
    file_name = context.get("fileName") or "unknown"

    instruction = MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["debug"])

    return f"""You are CodeDuck, a practical senior engineer and coding rubber duck.

Behavior:
- Be concise and concrete.
- Prefer next useful steps over broad theory.
- If context is insufficient, say exactly what is missing.
- Do not invent files, APIs, or test results.
- For debugging, reason through hypotheses and suggest verification.

Mode: {mode}
Mode instruction: {instruction}

File: {file_name}
Language: {language}

Developer question:
{question}

Code context:
```{language}
{code_context}
```

Answer:"""
