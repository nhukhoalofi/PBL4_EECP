from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.exceptions.errors import PolicyValidationError
from app.domain.value_objects.enums import AgentStatus

OFFLINE_TIMEOUT = timedelta(seconds=15)


@dataclass(slots=True)
class Agent:
    id: str
    hostname: str
    ip_address: str
    status: AgentStatus
    agent_version: str
    last_seen: datetime
    created_at: datetime

    @classmethod
    def register(
        cls,
        agent_id: str,
        hostname: str,
        ip_address: str,
        agent_version: str,
        at: datetime,
    ) -> Agent:
        return cls(
            id=_required(agent_id, "agent id"),
            hostname=_required(hostname, "hostname"),
            ip_address=_required(ip_address, "ip address"),
            status=AgentStatus.ONLINE,
            agent_version=_required(agent_version, "agent version"),
            last_seen=at,
            created_at=at,
        )

    def reregister(
        self,
        hostname: str,
        ip_address: str,
        agent_version: str,
        at: datetime,
    ) -> None:
        self.hostname = _required(hostname, "hostname")
        self.ip_address = _required(ip_address, "ip address")
        self.agent_version = _required(agent_version, "agent version")
        self.heartbeat(at)

    def heartbeat(self, at: datetime) -> None:
        self.last_seen = at
        self.status = AgentStatus.ONLINE

    def refresh_liveness(self, at: datetime) -> bool:
        next_status = (
            AgentStatus.OFFLINE
            if at - self.last_seen > OFFLINE_TIMEOUT
            else AgentStatus.ONLINE
        )
        changed = self.status != next_status
        self.status = next_status
        return changed


def _required(value: str, name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise PolicyValidationError(f"{name} must not be empty")
    return normalized
