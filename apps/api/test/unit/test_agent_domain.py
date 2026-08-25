from datetime import UTC, datetime, timedelta

import pytest
from app.domain.entities.agent import Agent
from app.domain.exceptions.errors import PolicyValidationError
from app.domain.value_objects.enums import AgentStatus

NOW = datetime(2026, 8, 25, 9, 0, tzinfo=UTC)


def test_register_agent_normalizes_fields_and_starts_online() -> None:
    agent = Agent.register(
        " PC01 ",
        " DESKTOP-A ",
        " 192.168.3.56 ",
        " 1.0.0 ",
        NOW,
    )

    assert agent.id == "PC01"
    assert agent.hostname == "DESKTOP-A"
    assert agent.ip_address == "192.168.3.56"
    assert agent.agent_version == "1.0.0"
    assert agent.status == AgentStatus.ONLINE
    assert agent.last_seen == NOW
    assert agent.created_at == NOW


def test_register_agent_rejects_blank_required_fields() -> None:
    with pytest.raises(PolicyValidationError, match="hostname must not be empty"):
        Agent.register("PC01", "   ", "192.168.3.56", "1.0.0", NOW)


def test_reregister_preserves_created_at_and_refreshes_mutable_fields() -> None:
    agent = Agent.register("PC01", "OLD", "192.168.3.10", "0.9.0", NOW)
    later = NOW + timedelta(minutes=1)

    agent.reregister(" NEW ", " 192.168.3.56 ", " 1.0.0 ", later)

    assert agent.created_at == NOW
    assert (agent.hostname, agent.ip_address, agent.agent_version) == (
        "NEW",
        "192.168.3.56",
        "1.0.0",
    )
    assert agent.status == AgentStatus.ONLINE
    assert agent.last_seen == later


def test_agent_is_offline_only_after_strict_fifteen_second_timeout() -> None:
    agent = Agent.register("PC01", "DESKTOP-A", "192.168.3.56", "1.0.0", NOW)

    assert agent.refresh_liveness(NOW + timedelta(seconds=15)) is False
    assert agent.status == AgentStatus.ONLINE
    assert agent.refresh_liveness(NOW + timedelta(seconds=16)) is True
    assert agent.status == AgentStatus.OFFLINE


def test_heartbeat_refreshes_last_seen_and_restores_online_status() -> None:
    agent = Agent.register("PC01", "DESKTOP-A", "192.168.3.56", "1.0.0", NOW)
    agent.refresh_liveness(NOW + timedelta(seconds=16))
    heartbeat_at = NOW + timedelta(seconds=17)

    agent.heartbeat(heartbeat_at)

    assert agent.last_seen == heartbeat_at
    assert agent.status == AgentStatus.ONLINE
