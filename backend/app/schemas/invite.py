import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr


class InviteRequestCreate(BaseModel):
    email: EmailStr


class InviteRequestResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    status: str
    created_at: datetime
    approved_at: datetime | None = None

    model_config = {"from_attributes": True}


class InviteApprovalRequest(BaseModel):
    email: EmailStr


class PromoteUserRequest(BaseModel):
    email: EmailStr
