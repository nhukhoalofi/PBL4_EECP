from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from agent.config import (
    AGENT_VERSION,
    HEARTBEAT_INTERVAL_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    SERVER_URL,
    load_agent_id,
)
from agent.heartbeat import AgentClient, WorkstationIdentity, collect_identity


class AgentTransport(Protocol):
    def register(self, identity: WorkstationIdentity) -> None: ...
    def heartbeat(self, agent_id: str) -> None: ...


def run_agent(
    client: AgentTransport,
    identity: WorkstationIdentity,
    interval_seconds: int,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
) -> None:
    registered = False
    while True:
        try:
            if registered:
                client.heartbeat(identity.agent_id)
                log(f"Heartbeat sent for {identity.agent_id}")
            else:
                client.register(identity)
                registered = True
                log(
                    f"Registered {identity.agent_id} ({identity.hostname}) "
                    f"at {identity.ip_address}"
                )
        except OSError as exc:
            registered = False
            log(f"Agent request failed: {exc}; retrying registration")
        sleep(interval_seconds)


def main() -> None:
    try:
        agent_id = load_agent_id()
    except RuntimeError as exc:
        raise SystemExit(f"Configuration error: {exc}") from None

    identity = collect_identity(agent_id, AGENT_VERSION, SERVER_URL)
    client = AgentClient(SERVER_URL, REQUEST_TIMEOUT_SECONDS)
    try:
        run_agent(client, identity, HEARTBEAT_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print(f"Stopped agent {identity.agent_id}")


if __name__ == "__main__":
    main()
