from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.db.database import get_db
from api.db.models import Agent
from api.dependencies import get_current_organization_id
from api.schemas.agent import AgentCreate

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("")
def list_agents(
    organization_id: int = Depends(get_current_organization_id),
    db: Session = Depends(get_db),
):
    agents = (
        db.query(Agent)
        .filter(Agent.organization_id == organization_id)
        .order_by(Agent.id)
        .all()
    )

    return [
        {
            "id": agent.id,
            "organization_id": agent.organization_id,
            "name": agent.name,
            "system_prompt": agent.system_prompt,
            "voice": agent.voice,
        }
        for agent in agents
    ]


@router.post("")
def create_agent(
    agent: AgentCreate,
    organization_id: int = Depends(get_current_organization_id),
    db: Session = Depends(get_db),
):
    db_agent = Agent(
        organization_id=organization_id,
        name=agent.name,
        system_prompt=agent.system_prompt,
        voice=agent.voice,
    )
    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)

    return {
        "id": db_agent.id,
        "organization_id": db_agent.organization_id,
        "name": db_agent.name,
        "system_prompt": db_agent.system_prompt,
        "voice": db_agent.voice,
    }
