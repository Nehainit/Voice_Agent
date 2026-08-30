from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from api.db.database import get_db
from api.db.models import ServiceKey
from api.services.api_keys import hash_api_key


def get_current_organization_id(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    key_hash = hash_api_key(x_api_key)

    service_key = (
        db.query(ServiceKey)
        .filter(ServiceKey.key_hash == key_hash)
        .filter(ServiceKey.revoked_at.is_(None))
        .first()
    )

    if service_key is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return service_key.organization_id

