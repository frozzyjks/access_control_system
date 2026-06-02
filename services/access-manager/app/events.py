from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel
from app.schemas import AccessRequestRead, RequestOperation, RequestTargetType


class AccessRequestCreatedEvent(BaseModel):
    event_type: Literal["ACCESS_REQUEST_CREATED"] = "ACCESS_REQUEST_CREATED"
    request_id: UUID
    user_id: str
    operation: RequestOperation
    target_type: RequestTargetType
    target_id: UUID
    created_at: datetime

    @classmethod
    def from_request(cls, request: AccessRequestRead) -> "AccessRequestCreatedEvent":

        return cls(
            request_id=request.id,
            user_id=request.user_id,
            operation=request.operation,
            target_type=request.target_type,
            target_id=request.target_id,
            created_at=request.created_at,
        )
