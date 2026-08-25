from __future__ import annotations

import json
import socket
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class WorkstationIdentity:
    agent_id: str
    hostname: str
    ip_address: str
    agent_version: str


class AgentClient:
    def __init__(
        self,
        server_url: str,
        timeout_seconds: int = 5,
        opener: Callable[..., Any] = urlopen,
    ):
        self._server_url = server_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def register(self, identity: WorkstationIdentity) -> None:
        payload = asdict(identity)
        payload["id"] = payload.pop("agent_id")
        self._post("/api/v1/agents/register", payload)

    def heartbeat(self, agent_id: str) -> None:
        self._post(f"/api/v1/agents/{agent_id}/heartbeat", {})

    def _post(self, path: str, payload: dict[str, str]) -> None:
        request = Request(
            f"{self._server_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self._opener(request, timeout=self._timeout_seconds) as response:
            response.read()


def collect_identity(
    agent_id: str,
    agent_version: str,
    server_url: str,
    hostname_getter: Callable[[], str] = socket.gethostname,
    resolver: Callable[[str], str] = socket.gethostbyname,
    socket_factory: Callable[..., socket.socket] = socket.socket,
) -> WorkstationIdentity:
    hostname = hostname_getter()
    server_hostname = urlsplit(server_url).hostname or "192.168.3.50"
    try:
        with socket_factory(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect((server_hostname, 80))
            ip_address = connection.getsockname()[0]
    except OSError:
        ip_address = resolver(hostname)
    return WorkstationIdentity(agent_id, hostname, ip_address, agent_version)
