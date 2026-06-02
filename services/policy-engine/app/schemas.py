from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID
from pydantic import BaseModel


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


class AccessRequestEvent(BaseModel):

    event_type: str
    request_id: UUID
    user_id: str
    operation: RequestOperation
    target_type: RequestTargetType
    target_id: UUID
    created_at: datetime


class AccessRequestRead(BaseModel):

    id: UUID
    user_id: str
    operation: RequestOperation
    target_type: RequestTargetType
    target_id: UUID
    status: RequestStatus
    rejection_reason: str | None


class AccessRead(BaseModel):

    id: UUID
    resource_id: UUID
    name: str
    description: str | None
    metadata: dict[str, Any]
    secret_ref: str | None


class RightGroupRead(BaseModel):

    id: UUID
    name: str
    description: str | None


class RightGroupConflictRead(BaseModel):

    group_id: UUID
    conflicting_group_id: UUID


class UserPermissionsRead(BaseModel):

    user_id: str
    right_group: RightGroupRead | None
    direct_access_ids: list[UUID] = []


class ApplyDecisionRequest(BaseModel):

    status: RequestStatus
    rejection_reason: str | None = None
    modified_by: str = "policy-engine"