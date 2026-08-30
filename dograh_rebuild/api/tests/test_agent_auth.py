from fastapi.testclient import TestClient

from api.app import app
from api.db.database import SessionLocal
from api.db.models import Agent, Organization, ServiceKey
from api.services.api_keys import api_key_prefix, generate_api_key, hash_api_key

client = TestClient(app)


def test_agents_requires_api_key():
    response = client.get("/api/v1/agents")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing X-API-Key header"


def test_api_key_only_lists_its_organization_agents():
    raw_key = generate_api_key()

    with SessionLocal() as db:
        org_a = Organization(name="Agent Tenant A")
        org_b = Organization(name="Agent Tenant B")
        db.add_all([org_a, org_b])
        db.commit()
        db.refresh(org_a)
        db.refresh(org_b)

        db.add_all(
            [
                ServiceKey(
                    organization_id=org_a.id,
                    name="Agent Tenant A key",
                    key_hash=hash_api_key(raw_key),
                    key_prefix=api_key_prefix(raw_key),
                ),
                Agent(
                    organization_id=org_a.id,
                    name="Tenant A agent",
                    system_prompt="Help tenant A.",
                    voice="alloy",
                ),
                Agent(
                    organization_id=org_b.id,
                    name="Tenant B agent",
                    system_prompt="Help tenant B.",
                    voice="verse",
                ),
            ]
        )
        db.commit()

    response = client.get("/api/v1/agents", headers={"X-API-Key": raw_key})

    assert response.status_code == 200
    names = {agent["name"] for agent in response.json()}
    assert "Tenant A agent" in names
    assert "Tenant B agent" not in names


def test_create_agent_uses_api_key_organization():
    raw_key = generate_api_key()

    with SessionLocal() as db:
        organization = Organization(name="Create Agent Tenant")
        db.add(organization)
        db.commit()
        db.refresh(organization)
        organization_id = organization.id

        db.add(
            ServiceKey(
                organization_id=organization_id,
                name="Create agent key",
                key_hash=hash_api_key(raw_key),
                key_prefix=api_key_prefix(raw_key),
            )
        )
        db.commit()

    response = client.post(
        "/api/v1/agents",
        headers={"X-API-Key": raw_key},
        json={
            "name": "Sales Bot",
            "system_prompt": "Qualify inbound leads clearly.",
            "voice": "alloy",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Sales Bot"
    assert data["organization_id"] == organization_id
