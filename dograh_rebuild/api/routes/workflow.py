from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.db.database import get_db
from api.db.models import Agent, Workflow, WorkflowEdge, WorkflowNode
from api.dependencies import get_current_organization_id
from api.schemas.workflow import (
    WorkflowAudioTurnRequest,
    WorkflowCreate,
    WorkflowEdgeCreate,
    WorkflowNodeCreate,
    WorkflowTextTurnRequest,
)
from api.services.openai_provider import (
    ProviderConfigError,
    ProviderRequestError,
    decode_audio,
    encode_audio,
    generate_llm_response,
    synthesize_speech,
    transcribe_audio,
)
from api.services.workflow_runtime import (
    run_workflow_text_turn,
    summarize_workflow_graph,
)

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _get_owned_workflow(
    workflow_id: int,
    organization_id: int,
    db: Session,
):
    workflow = (
        db.query(Workflow)
        .filter(Workflow.id == workflow_id)
        .filter(Workflow.organization_id == organization_id)
        .first()
    )
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


def _load_workflow_runtime(
    workflow_id: int,
    organization_id: int,
    db: Session,
):
    workflow = _get_owned_workflow(workflow_id, organization_id, db)
    agent = (
        db.query(Agent)
        .filter(Agent.id == workflow.agent_id)
        .filter(Agent.organization_id == organization_id)
        .first()
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    nodes = (
        db.query(WorkflowNode)
        .filter(WorkflowNode.workflow_id == workflow_id)
        .order_by(WorkflowNode.id)
        .all()
    )
    edges = (
        db.query(WorkflowEdge)
        .filter(WorkflowEdge.workflow_id == workflow_id)
        .order_by(WorkflowEdge.id)
        .all()
    )
    return workflow, agent, nodes, edges


def _provider_http_error(error: Exception):
    if isinstance(error, ProviderConfigError):
        raise HTTPException(status_code=503, detail=str(error)) from error
    if isinstance(error, ProviderRequestError):
        raise HTTPException(status_code=502, detail="Provider request failed") from error
    raise error


@router.get("")
def list_workflows(
    organization_id: int = Depends(get_current_organization_id),
    db: Session = Depends(get_db),
):
    workflows = (
        db.query(Workflow)
        .filter(Workflow.organization_id == organization_id)
        .order_by(Workflow.id)
        .all()
    )

    result = []
    for workflow in workflows:
        result.append(
            {
                "id": workflow.id,
                "organization_id": workflow.organization_id,
                "agent_id": workflow.agent_id,
                "name": workflow.name,
                "description": workflow.description,
            }
        )

    return result


@router.post("")
def create_workflow(
    workflow: WorkflowCreate,
    organization_id: int = Depends(get_current_organization_id),
    db: Session = Depends(get_db),
):
    agent = (
        db.query(Agent)
        .filter(Agent.id == workflow.agent_id)
        .filter(Agent.organization_id == organization_id)
        .first()
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    db_workflow = Workflow(
        organization_id=organization_id,
        agent_id=workflow.agent_id,
        name=workflow.name,
        description=workflow.description,
    )
    db.add(db_workflow)
    db.commit()
    db.refresh(db_workflow)

    return {
        "id": db_workflow.id,
        "organization_id": db_workflow.organization_id,
        "agent_id": db_workflow.agent_id,
        "name": db_workflow.name,
        "description": db_workflow.description,
    }


@router.get("/{workflow_id}/graph")
def get_workflow_graph(
    workflow_id: int,
    organization_id: int = Depends(get_current_organization_id),
    db: Session = Depends(get_db),
):
    workflow = _get_owned_workflow(workflow_id, organization_id, db)
    nodes = (
        db.query(WorkflowNode)
        .filter(WorkflowNode.workflow_id == workflow_id)
        .order_by(WorkflowNode.id)
        .all()
    )
    edges = (
        db.query(WorkflowEdge)
        .filter(WorkflowEdge.workflow_id == workflow_id)
        .order_by(WorkflowEdge.id)
        .all()
    )

    return {
        "workflow": {
            "id": workflow.id,
            "organization_id": workflow.organization_id,
            "agent_id": workflow.agent_id,
            "name": workflow.name,
            "description": workflow.description,
        },
        "nodes": [
            {
                "id": node.id,
                "workflow_id": node.workflow_id,
                "node_key": node.node_key,
                "node_type": node.node_type,
                "label": node.label,
            }
            for node in nodes
        ],
        "edges": [
            {
                "id": edge.id,
                "workflow_id": edge.workflow_id,
                "source_node_key": edge.source_node_key,
                "target_node_key": edge.target_node_key,
            }
            for edge in edges
        ],
    }


@router.post("/{workflow_id}/llm-test-turn")
def run_workflow_llm_test_turn(
    workflow_id: int,
    request: WorkflowTextTurnRequest,
    organization_id: int = Depends(get_current_organization_id),
    db: Session = Depends(get_db),
):
    workflow, agent, nodes, edges = _load_workflow_runtime(
        workflow_id,
        organization_id,
        db,
    )
    try:
        response_text = generate_llm_response(
            system_prompt=agent.system_prompt,
            graph_summary=summarize_workflow_graph(nodes, edges),
            user_text=request.user_text,
        )
    except Exception as error:  # noqa: BLE001
        _provider_http_error(error)

    return {
        "agent": {"id": agent.id, "name": agent.name, "voice": agent.voice},
        "workflow": {"id": workflow.id, "name": workflow.name},
        "user_text": request.user_text,
        "response_text": response_text,
    }


@router.post("/{workflow_id}/voice-test-turn")
def run_workflow_voice_test_turn(
    workflow_id: int,
    request: WorkflowAudioTurnRequest,
    organization_id: int = Depends(get_current_organization_id),
    db: Session = Depends(get_db),
):
    workflow, agent, nodes, edges = _load_workflow_runtime(
        workflow_id,
        organization_id,
        db,
    )
    try:
        user_text = transcribe_audio(
            audio_bytes=decode_audio(request.audio_base64),
            filename=request.filename,
            content_type=request.content_type,
        )
        response_text = generate_llm_response(
            system_prompt=agent.system_prompt,
            graph_summary=summarize_workflow_graph(nodes, edges),
            user_text=user_text,
        )
        audio_bytes = synthesize_speech(response_text, agent.voice)
    except Exception as error:  # noqa: BLE001
        _provider_http_error(error)

    return {
        "agent": {"id": agent.id, "name": agent.name, "voice": agent.voice},
        "workflow": {"id": workflow.id, "name": workflow.name},
        "user_text": user_text,
        "response_text": response_text,
        "audio_base64": encode_audio(audio_bytes),
        "audio_content_type": "audio/mpeg",
    }


@router.post("/{workflow_id}/test-turn")
def run_workflow_test_turn(
    workflow_id: int,
    request: WorkflowTextTurnRequest,
    organization_id: int = Depends(get_current_organization_id),
    db: Session = Depends(get_db),
):
    workflow = _get_owned_workflow(workflow_id, organization_id, db)
    agent = (
        db.query(Agent)
        .filter(Agent.id == workflow.agent_id)
        .filter(Agent.organization_id == organization_id)
        .first()
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    nodes = (
        db.query(WorkflowNode)
        .filter(WorkflowNode.workflow_id == workflow_id)
        .order_by(WorkflowNode.id)
        .all()
    )
    edges = (
        db.query(WorkflowEdge)
        .filter(WorkflowEdge.workflow_id == workflow_id)
        .order_by(WorkflowEdge.id)
        .all()
    )

    return run_workflow_text_turn(
        agent=agent,
        workflow=workflow,
        nodes=nodes,
        edges=edges,
        user_text=request.user_text,
    )


@router.get("/{workflow_id}/nodes")
def list_workflow_nodes(
    workflow_id: int,
    organization_id: int = Depends(get_current_organization_id),
    db: Session = Depends(get_db),
):
    _get_owned_workflow(workflow_id, organization_id, db)
    nodes = (
        db.query(WorkflowNode)
        .filter(WorkflowNode.workflow_id == workflow_id)
        .order_by(WorkflowNode.id)
        .all()
    )

    return [
        {
            "id": node.id,
            "workflow_id": node.workflow_id,
            "node_key": node.node_key,
            "node_type": node.node_type,
            "label": node.label,
        }
        for node in nodes
    ]


@router.post("/{workflow_id}/nodes")
def create_workflow_node(
    workflow_id: int,
    node: WorkflowNodeCreate,
    organization_id: int = Depends(get_current_organization_id),
    db: Session = Depends(get_db),
):
    _get_owned_workflow(workflow_id, organization_id, db)
    db_node = WorkflowNode(
        workflow_id=workflow_id,
        node_key=node.node_key,
        node_type=node.node_type,
        label=node.label,
    )
    db.add(db_node)
    db.commit()
    db.refresh(db_node)

    return {
        "id": db_node.id,
        "workflow_id": db_node.workflow_id,
        "node_key": db_node.node_key,
        "node_type": db_node.node_type,
        "label": db_node.label,
    }


@router.get("/{workflow_id}/edges")
def list_workflow_edges(
    workflow_id: int,
    organization_id: int = Depends(get_current_organization_id),
    db: Session = Depends(get_db),
):
    _get_owned_workflow(workflow_id, organization_id, db)
    edges = (
        db.query(WorkflowEdge)
        .filter(WorkflowEdge.workflow_id == workflow_id)
        .order_by(WorkflowEdge.id)
        .all()
    )

    return [
        {
            "id": edge.id,
            "workflow_id": edge.workflow_id,
            "source_node_key": edge.source_node_key,
            "target_node_key": edge.target_node_key,
        }
        for edge in edges
    ]


@router.post("/{workflow_id}/edges")
def create_workflow_edge(
    workflow_id: int,
    edge: WorkflowEdgeCreate,
    organization_id: int = Depends(get_current_organization_id),
    db: Session = Depends(get_db),
):
    _get_owned_workflow(workflow_id, organization_id, db)
    db_edge = WorkflowEdge(
        workflow_id=workflow_id,
        source_node_key=edge.source_node_key,
        target_node_key=edge.target_node_key,
    )
    db.add(db_edge)
    db.commit()
    db.refresh(db_edge)

    return {
        "id": db_edge.id,
        "workflow_id": db_edge.workflow_id,
        "source_node_key": db_edge.source_node_key,
        "target_node_key": db_edge.target_node_key,
    }
