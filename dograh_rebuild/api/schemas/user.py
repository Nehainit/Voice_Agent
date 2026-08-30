from pydantic import BaseModel


class UserCreate(BaseModel):
    email: str
    organization_id: int
