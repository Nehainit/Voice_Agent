from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.db.database import get_db
from api.db.models import User
from api.schemas.user import UserCreate

router = APIRouter(prefix="/users", tags=["users"])


@router.post("")
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
):
    db_user = User(email=user.email, organization_id=user.organization_id)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return {
        "id": db_user.id,
        "email": db_user.email,
        "organization_id": db_user.organization_id,
    }
