from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.domain.entities.exam_session import new_id, utc_now
from app.domain.value_objects.enums import CommandStatus, CommandType, IncidentStatus, Severity


@dataclass(slots=True)
class Command:
    session_id: str
    target_id: str
    type: CommandType
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: new_id("cmd"))
    status: CommandStatus = CommandStatus.PENDING
    created_at: datetime = field(default_factory=utc_now)
    acknowledged_at: datetime | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    session_id: str
    workstation_id: str
    event_type: str
    severity: Severity
    category: str
    action: str
    destination: str | None = None
    correlation_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: new_id("evt"))
    occurred_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Incident:
    session_id: str
    category: str
    severity: Severity
    evidence: dict[str, Any]
    workstation_id: str | None = None
    id: str = field(default_factory=lambda: new_id("inc"))
    status: IncidentStatus = IncidentStatus.OPEN
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class AuditEvent:
    session_id: str
    actor: str
    action: str
    target: str
    details: dict[str, Any]
    previous_hash: str
    chain_hash: str
    id: str = field(default_factory=lambda: new_id("aud"))
    occurred_at: datetime = field(default_factory=utc_now)
