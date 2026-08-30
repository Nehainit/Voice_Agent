import os
from typing import Any


async def ask_ollama(prompt: str, model: str | None = None, num_ctx: int | None = None) -> str:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model = model or os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b-instruct")
    try:
        from langchain_ollama import ChatOllama
    except ImportError as error:
        raise RuntimeError("Install langchain-ollama to enable Ollama chat models.") from error

    llm = ChatOllama(
        model=model,
        base_url=base_url,
        temperature=0.2,
        num_ctx=int(num_ctx or os.getenv("OLLAMA_NUM_CTX", "4096")),
    )

    response = await llm.ainvoke(prompt)
    return message_content_to_text(response.content)


def message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
        return "\n".join(parts).strip()
    return str(content).strip()
