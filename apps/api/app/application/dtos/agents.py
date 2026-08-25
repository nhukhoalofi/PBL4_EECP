from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RegisterAgentInput:
    agent_id: str
    hostname: str
    ip_address: str
    agent_version: str
