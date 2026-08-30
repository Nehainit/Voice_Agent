import base64

from fastapi.testclient import TestClient

from api.app import app
from api.db.database import SessionLocal
from api.db.models import Agent, Organization, ServiceKey, Workflow, WorkflowEdge, WorkflowNode
from api.services.api_keys import api_key_prefix, generate_api_key, hash_api_key

client = TestClient(app)


def test_workflows_requires_api_key():
    response = client.get("/api/v1/workflows")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing X-API-Key header"


def test_api_key_only_lists_its_organization_workflows():
    raw_key = generate_api_key()

    with SessionLocal() as db:
        org_a = Organization(name="Tenant A")
        org_b = Organization(name="Tenant B")
        db.add_all([org_a, org_b])
        db.commit()
        db.refresh(org_a)
        db.refresh(org_b)

        service_key = ServiceKey(
            organization_id=org_a.id,
            name="Tenant A test key",
            key_hash=hash_api_key(raw_key),
            key_prefix=api_key_prefix(raw_key),
        )
        workflow_a = Workflow(
            organization_id=org_a.id,
            name="Tenant A workflow",
            description="Visible with Tenant A key",
        )
        workflow_b = Workflow(
            organization_id=org_b.id,
            name="Tenant B workflow",
            description="Must not be visible with Tenant A key",
        )
        db.add_all([service_key, workflow_a, workflow_b])
        db.commit()

    response = client.get(
        "/api/v1/workflows",
        headers={"X-API-Key": raw_key},
    )

    assert response.status_code == 200
    names = {workflow["name"] for workflow in response.json()}
    assert "Tenant A workflow" in names
    assert "Tenant B workflow" not in names



def test_create_workflow_uses_api_key_organization():
    raw_key = generate_api_key()

    with SessionLocal() as db:
        organization = Organization(name="Create Scope Tenant")
        db.add(organization)
        db.commit()
        db.refresh(organization)

        agent = Agent(
            organization_id=organization.id,
            name="Create workflow agent",
            system_prompt="Create workflow test.",
            voice="alloy",
        )
        service_key = ServiceKey(
            organization_id=organization.id,
            name="Create scope test key",
            key_hash=hash_api_key(raw_key),
            key_prefix=api_key_prefix(raw_key),
        )
        db.add_all([agent, service_key])
        db.commit()
        db.refresh(agent)
        organization_id = organization.id
        agent_id = agent.id

    response = client.post(
        "/api/v1/workflows",
        headers={"X-API-Key": raw_key},
        json={
            "agent_id": agent_id,
            "name": "Created by key",
            "description": "Org comes from API key",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Created by key"
    assert data["organization_id"] == organization_id
    assert data["agent_id"] == agent_id



def test_create_workflow_rejects_agent_from_another_organization():
    raw_key = generate_api_key()

    with SessionLocal() as db:
        org_a = Organization(name="Workflow Agent Tenant A")
        org_b = Organization(name="Workflow Agent Tenant B")
        db.add_all([org_a, org_b])
        db.commit()
        db.refresh(org_a)
        db.refresh(org_b)

        other_agent = Agent(
            organization_id=org_b.id,
            name="Other org agent",
            system_prompt="Not accessible.",
            voice="verse",
        )
        service_key = ServiceKey(
            organization_id=org_a.id,
            name="Tenant A workflow key",
            key_hash=hash_api_key(raw_key),
            key_prefix=api_key_prefix(raw_key),
        )
        db.add_all([other_agent, service_key])
        db.commit()
        db.refresh(other_agent)
        other_agent_id = other_agent.id

    response = client.post(
        "/api/v1/workflows",
        headers={"X-API-Key": raw_key},
        json={
            "agent_id": other_agent_id,
            "name": "Should fail",
            "description": "Cannot attach to another org agent",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found"



def test_workflow_nodes_and_edges_are_scoped_to_workflow_org():
    raw_key = generate_api_key()

    with SessionLocal() as db:
        organization = Organization(name="Graph Tenant")
        db.add(organization)
        db.commit()
        db.refresh(organization)

        agent = Agent(
            organization_id=organization.id,
            name="Graph Agent",
            system_prompt="Run graph.",
            voice="alloy",
        )
        service_key = ServiceKey(
            organization_id=organization.id,
            name="Graph key",
            key_hash=hash_api_key(raw_key),
            key_prefix=api_key_prefix(raw_key),
        )
        db.add_all([agent, service_key])
        db.commit()
        db.refresh(agent)

        workflow = Workflow(
            organization_id=organization.id,
            agent_id=agent.id,
            name="Graph workflow",
            description="Has nodes and edges",
        )
        db.add(workflow)
        db.commit()
        db.refresh(workflow)
        workflow_id = workflow.id

    node_response = client.post(
        f"/api/v1/workflows/{workflow_id}/nodes",
        headers={"X-API-Key": raw_key},
        json={"node_key": "start", "node_type": "start", "label": "Start"},
    )
    edge_response = client.post(
        f"/api/v1/workflows/{workflow_id}/edges",
        headers={"X-API-Key": raw_key},
        json={"source_node_key": "start", "target_node_key": "end"},
    )

    assert node_response.status_code == 200
    assert node_response.json()["node_key"] == "start"
    assert edge_response.status_code == 200
    assert edge_response.json()["source_node_key"] == "start"

    nodes = client.get(
        f"/api/v1/workflows/{workflow_id}/nodes",
        headers={"X-API-Key": raw_key},
    )
    edges = client.get(
        f"/api/v1/workflows/{workflow_id}/edges",
        headers={"X-API-Key": raw_key},
    )

    assert nodes.status_code == 200
    assert edges.status_code == 200
    assert nodes.json()[0]["label"] == "Start"
    assert edges.json()[0]["target_node_key"] == "end"


def test_workflow_nodes_reject_other_organization_workflow():
    raw_key = generate_api_key()

    with SessionLocal() as db:
        org_a = Organization(name="Node Tenant A")
        org_b = Organization(name="Node Tenant B")
        db.add_all([org_a, org_b])
        db.commit()
        db.refresh(org_a)
        db.refresh(org_b)

        agent_b = Agent(
            organization_id=org_b.id,
            name="Other graph agent",
            system_prompt="Other org.",
            voice="verse",
        )
        service_key = ServiceKey(
            organization_id=org_a.id,
            name="Node Tenant A key",
            key_hash=hash_api_key(raw_key),
            key_prefix=api_key_prefix(raw_key),
        )
        db.add_all([agent_b, service_key])
        db.commit()
        db.refresh(agent_b)

        workflow_b = Workflow(
            organization_id=org_b.id,
            agent_id=agent_b.id,
            name="Other org workflow",
            description="Not accessible",
        )
        db.add(workflow_b)
        db.commit()
        db.refresh(workflow_b)
        workflow_b_id = workflow_b.id

    response = client.post(
        f"/api/v1/workflows/{workflow_b_id}/nodes",
        headers={"X-API-Key": raw_key},
        json={"node_key": "start", "node_type": "start", "label": "Start"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Workflow not found"



def test_workflow_graph_returns_workflow_nodes_and_edges():
    raw_key = generate_api_key()

    with SessionLocal() as db:
        organization = Organization(name="Graph Read Tenant")
        db.add(organization)
        db.commit()
        db.refresh(organization)

        agent = Agent(
            organization_id=organization.id,
            name="Graph Read Agent",
            system_prompt="Read graph.",
            voice="alloy",
        )
        service_key = ServiceKey(
            organization_id=organization.id,
            name="Graph read key",
            key_hash=hash_api_key(raw_key),
            key_prefix=api_key_prefix(raw_key),
        )
        db.add_all([agent, service_key])
        db.commit()
        db.refresh(agent)

        workflow = Workflow(
            organization_id=organization.id,
            agent_id=agent.id,
            name="Graph read workflow",
            description="Loads full canvas",
        )
        db.add(workflow)
        db.commit()
        db.refresh(workflow)

        db.add_all(
            [
                WorkflowNode(
                    workflow_id=workflow.id,
                    node_key="start",
                    node_type="start",
                    label="Start",
                ),
                WorkflowNode(
                    workflow_id=workflow.id,
                    node_key="end",
                    node_type="end",
                    label="End",
                ),
                WorkflowEdge(
                    workflow_id=workflow.id,
                    source_node_key="start",
                    target_node_key="end",
                ),
            ]
        )
        db.commit()
        workflow_id = workflow.id

    response = client.get(
        f"/api/v1/workflows/{workflow_id}/graph",
        headers={"X-API-Key": raw_key},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["workflow"]["name"] == "Graph read workflow"
    assert [node["node_key"] for node in data["nodes"]] == ["start", "end"]
    assert data["edges"] == [
        {
            "id": data["edges"][0]["id"],
            "workflow_id": workflow_id,
            "source_node_key": "start",
            "target_node_key": "end",
        }
    ]



def test_workflow_test_turn_loads_agent_and_graph():
    raw_key = generate_api_key()

    with SessionLocal() as db:
        organization = Organization(name="Runtime Tenant")
        db.add(organization)
        db.commit()
        db.refresh(organization)

        agent = Agent(
            organization_id=organization.id,
            name="Runtime Agent",
            system_prompt="Use the configured graph.",
            voice="alloy",
        )
        service_key = ServiceKey(
            organization_id=organization.id,
            name="Runtime key",
            key_hash=hash_api_key(raw_key),
            key_prefix=api_key_prefix(raw_key),
        )
        db.add_all([agent, service_key])
        db.commit()
        db.refresh(agent)

        workflow = Workflow(
            organization_id=organization.id,
            agent_id=agent.id,
            name="Runtime workflow",
            description="Runtime fallback",
        )
        db.add(workflow)
        db.commit()
        db.refresh(workflow)

        db.add_all(
            [
                WorkflowNode(
                    workflow_id=workflow.id,
                    node_key="start",
                    node_type="start",
                    label="Start call",
                ),
                WorkflowNode(
                    workflow_id=workflow.id,
                    node_key="ask_need",
                    node_type="message",
                    label="Ask what the caller needs",
                ),
                WorkflowEdge(
                    workflow_id=workflow.id,
                    source_node_key="start",
                    target_node_key="ask_need",
                ),
            ]
        )
        db.commit()
        workflow_id = workflow.id

    response = client.post(
        f"/api/v1/workflows/{workflow_id}/test-turn",
        headers={"X-API-Key": raw_key},
        json={"user_text": "hello"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["agent"]["name"] == "Runtime Agent"
    assert data["workflow"]["name"] == "Runtime workflow"
    assert data["user_text"] == "hello"
    assert data["current_node_key"] == "start"
    assert data["next_node_key"] == "ask_need"
    assert data["response_text"] == "Runtime Agent: Ask what the caller needs"



def test_workflow_voice_test_turn_uses_stt_llm_and_tts(monkeypatch):
    raw_key = generate_api_key()

    with SessionLocal() as db:
        organization = Organization(name="Voice Runtime Tenant")
        db.add(organization)
        db.commit()
        db.refresh(organization)

        agent = Agent(
            organization_id=organization.id,
            name="Voice Runtime Agent",
            system_prompt="Answer using the graph.",
            voice="alloy",
        )
        service_key = ServiceKey(
            organization_id=organization.id,
            name="Voice runtime key",
            key_hash=hash_api_key(raw_key),
            key_prefix=api_key_prefix(raw_key),
        )
        db.add_all([agent, service_key])
        db.commit()
        db.refresh(agent)

        workflow = Workflow(
            organization_id=organization.id,
            agent_id=agent.id,
            name="Voice runtime workflow",
            description="Runs STT LLM TTS",
        )
        db.add(workflow)
        db.commit()
        db.refresh(workflow)
        workflow_id = workflow.id

    def fake_transcribe_audio(audio_bytes, filename, content_type):
        assert audio_bytes == b"audio input"
        assert filename == "input.wav"
        assert content_type == "audio/wav"
        return "I want pricing"

    def fake_generate_llm_response(system_prompt, graph_summary, user_text):
        assert system_prompt == "Answer using the graph."
        assert user_text == "I want pricing"
        return "Pricing depends on call volume."

    def fake_synthesize_speech(text, voice):
        assert text == "Pricing depends on call volume."
        assert voice == "alloy"
        return b"audio output"

    monkeypatch.setattr("api.routes.workflow.transcribe_audio", fake_transcribe_audio)
    monkeypatch.setattr("api.routes.workflow.generate_llm_response", fake_generate_llm_response)
    monkeypatch.setattr("api.routes.workflow.synthesize_speech", fake_synthesize_speech)

    response = client.post(
        f"/api/v1/workflows/{workflow_id}/voice-test-turn",
        headers={"X-API-Key": raw_key},
        json={
            "filename": "input.wav",
            "content_type": "audio/wav",
            "audio_base64": base64.b64encode(b"audio input").decode("ascii"),
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user_text"] == "I want pricing"
    assert data["response_text"] == "Pricing depends on call volume."
    assert base64.b64decode(data["audio_base64"]) == b"audio output"
    assert data["audio_content_type"] == "audio/mpeg"
