from pydantic import BaseModel


class AgentCreate(BaseModel):
    name: str
    system_prompt: str
    voice: str
