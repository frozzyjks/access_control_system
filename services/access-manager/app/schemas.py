from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):

    detail: str


class RequestOperation(StrEnum):

    GRANT = "GRANT"
    REVOKE = "REVOKE"


class RequestTargetType(StrEnum):

    ACCESS = "ACCESS"
    RIGHT_GROUP = "RIGHT_GROUP"


class RequestStatus(StrEnum):

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AccessRequestCreate(BaseModel):

    user_id: str = Field(min_length=1, max_length=255)
    operation: RequestOperation
    target_type: RequestTargetType
    target_id: UUID


class AccessRequestRead(BaseModel):

    id: UUID
    user_id: str
    operation: RequestOperation
    target_type: RequestTargetType
    target_id: UUID
    status: RequestStatus
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime
    last_modified_at: datetime | None
    last_modified_by: str | None


class AccessRead(BaseModel):

    id: UUID
    resource_id: UUID
    name: str
    description: str | None
    metadata: dict[str, Any]
    secret_ref: str | None
    created_at: datetime
    updated_at: datetime


class RightGroupRead(BaseModel):

    id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class UserPermissionsRead(BaseModel):

    user_id: str
    right_group: RightGroupRead | None
    direct_accesses: list[AccessRead] = Field(default_factory=list)
    effective_accesses: list[AccessRead] = Field(default_factory=list)