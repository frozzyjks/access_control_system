from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    detail: str


class ResourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    resource_type: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=1000)


class ResourceRead(BaseModel):

    id: UUID
    name: str
    resource_type: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AccessCreate(BaseModel):

    resource_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    secret_ref: str | None = Field(default=None, max_length=500)


class AccessRead(BaseModel):

    id: UUID
    resource_id: UUID
    name: str
    description: str | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    secret_ref: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RightGroupCreate(BaseModel):

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)


class RightGroupRead(BaseModel):

    id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AddAccessToGroup(BaseModel):

    access_id: UUID


class AddGroupConflict(BaseModel):

    conflicting_group_id: UUID


class GroupAccessRead(BaseModel):

    group_id: UUID
    access_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GroupConflictRead(BaseModel):

    group_id: UUID
    conflicting_group_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


class ApplyDecision(BaseModel):

    status: Literal[RequestStatus.APPROVED, RequestStatus.REJECTED]
    rejection_reason: str | None = Field(default=None, max_length=1000)
    modified_by: str = Field(default="policy-engine", min_length=1, max_length=255)


class UserPermissionsRead(BaseModel):

    user_id: str
    right_group: RightGroupRead | None
    direct_accesses: list[AccessRead] = Field(default_factory=list)
    effective_accesses: list[AccessRead] = Field(default_factory=list)