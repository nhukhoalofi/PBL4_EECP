from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.value_objects.enums import CommandStatus, CommandType


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AcknowledgeCommandRequest(ApiModel):
    success: bool
    policy_hash: str | None = None
    error: str | None = None
    actor: str = Field(default="agent", min_length=1)


class CommandView(ApiModel):
    id: str
    session_id: str
    target_id: str
    type: CommandType
    payload: dict[str, Any]
    status: CommandStatus
    created_at: datetime


class PolicyProfileView(ApiModel):
    id: str
    label: str
    description: str
    rules: dict[str, Any]
    yaml: str
