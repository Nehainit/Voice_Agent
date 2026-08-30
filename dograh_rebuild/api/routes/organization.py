from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.db.database import get_db
from api.db.models import Organization
from api.schemas.organization import OrganizationCreate

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("")
def create_organization(
    organization: OrganizationCreate,
    db: Session = Depends(get_db),
):
    db_organization = Organization(name=organization.name)
    db.add(db_organization)
    db.commit()
    db.refresh(db_organization)

    return {"id": db_organization.id, "name": db_organization.name}
