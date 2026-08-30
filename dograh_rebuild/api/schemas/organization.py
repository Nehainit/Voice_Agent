from pydantic import BaseModel


class OrganizationCreate(BaseModel):
    name: str
