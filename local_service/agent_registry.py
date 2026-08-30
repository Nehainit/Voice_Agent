from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .app_config import get_platform_config


@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    name: str
    aliases: tuple[str, ...]
    type: str
    default_language: str
    tools: tuple[str, ...]
    permissions: dict[str, Any]


def load_agents() -> dict[str, AgentDefinition]:
    agents_config = get_platform_config().get("agents", {}).get("agents", [])
    agents: dict[str, AgentDefinition] = {}
    for item in agents_config:
        if not isinstance(item, dict):
            continue
        agent_id = str(item.get("agentId") or "").strip()
        if not agent_id:
            continue
        agents[agent_id] = AgentDefinition(
            agent_id=agent_id,
            name=str(item.get("name") or agent_id).strip(),
            aliases=tuple(str(alias).lower() for alias in item.get("aliases") or []),
            type=str(item.get("type") or "general").strip(),
            default_language=str(item.get("defaultLanguage") or "Auto").strip(),
            tools=tuple(str(tool) for tool in item.get("tools") or []),
            permissions=dict(item.get("permissions") or {}),
        )
    return agents


def resolve_agent(transcript: str, request_active_agent_id: str, context: dict[str, Any]) -> AgentDefinition:
    agents = load_agents()
    text = f" {transcript.lower()} "

    for agent in agents.values():
        names = (agent.name.lower(), *agent.aliases)
        if any(f" {alias} " in text or text.strip().startswith(f"{alias},") for alias in names if alias):
            return agent

    if request_active_agent_id in agents:
        return agents[request_active_agent_id]

    inferred = infer_agent_from_context(context)
    if inferred in agents:
        return agents[inferred]

    return agents.get("general_assistant") or AgentDefinition(
        agent_id="general_assistant",
        name="Neha",
        aliases=("neha", "assistant", "buddy"),
        type="general",
        default_language="Hinglish",
        tools=(),
        permissions={},
    )


def infer_agent_from_context(context: dict[str, Any]) -> str:
    active_app = str(context.get("activeApp") or "").lower()
    window_title = str(context.get("windowTitle") or "").lower()
    file_name = str(context.get("fileName") or "").lower()
    focused = str(context.get("focusedInputType") or "").lower()
    combined = " ".join([active_app, window_title, file_name, focused])

    if any(marker in combined for marker in ("cursor", "visual studio code", "vscode", ".py", ".js", ".ts", ".tsx", ".jsx")):
        return "code_assistant"
    if any(marker in combined for marker in ("gmail", "mail", "slack", "docs", "linkedin message")):
        return "email_assistant"
    if any(marker in combined for marker in ("zoom", "meet", "teams", "facetime")):
        return "meeting_assistant"
    if any(marker in combined for marker in ("crm", "hubspot", "salesforce", "lead", "prospect", "linkedin")):
        return "sales_assistant"
    return "general_assistant"


def response_language(request_language: str, agent: AgentDefinition) -> str:
    language = (request_language or "").strip()
    if language and language.lower() != "auto":
        return language
    app_language = get_platform_config().get("app", {}).get("language", {}).get("preferredResponseLanguage", "Auto")
    if str(app_language).lower() != "auto":
        return str(app_language)
    return agent.default_language or "English"
