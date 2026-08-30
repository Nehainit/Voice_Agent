from pydantic import BaseModel


class WorkflowCreate(BaseModel):
    agent_id: int
    name: str
    description: str


class WorkflowNodeCreate(BaseModel):
    node_key: str
    node_type: str
    label: str


class WorkflowEdgeCreate(BaseModel):
    source_node_key: str
    target_node_key: str


class WorkflowTextTurnRequest(BaseModel):
    user_text: str


class WorkflowAudioTurnRequest(BaseModel):
    filename: str
    content_type: str
    audio_base64: str
