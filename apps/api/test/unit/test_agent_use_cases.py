from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.application.dtos.agents import RegisterAgentInput
from app.application.use_cases.agents.management import (
    HeartbeatAgent,
    ListAgents,
    RegisterAgent,
)
from app.domain.value_objects.enums import AgentStatus
from app.infrastructure.persistence.database import SqliteDatabase

NOW = datetime(2026, 8, 25, 9, 0, tzinfo=UTC)


def test_register_is_idempotent_and_preserves_created_at(tmp_path: Path) -> None:
    current = [NOW]
    database = SqliteDatabase(tmp_path / "register-use-case.db")
    database.initialize()
    register = RegisterAgent(database.unit_of_work, lambda: current[0])

    first = register(
        RegisterAgentInput("PC01", "OLD", "192.168.3.10", "0.9.0")
    )
    current[0] += timedelta(minutes=1)
    second = register(
        RegisterAgentInput("PC01", "NEW", "192.168.3.56", "1.0.0")
    )

    assert second.created_at == first.created_at
    assert second.hostname == "NEW"
    assert second.ip_address == "192.168.3.56"
    assert second.agent_version == "1.0.0"
    assert second.last_seen == current[0]


def test_heartbeat_and_list_apply_and_persist_liveness_rule(tmp_path: Path) -> None:
    current = [NOW]
    database = SqliteDatabase(tmp_path / "liveness-use-case.db")
    database.initialize()
    register = RegisterAgent(database.unit_of_work, lambda: current[0])
    heartbeat = HeartbeatAgent(database.unit_of_work, lambda: current[0])
    list_agents = ListAgents(database.unit_of_work, lambda: current[0])
    register(RegisterAgentInput("PC02", "B", "192.168.3.55", "1.0.0"))
    register(RegisterAgentInput("PC01", "A", "192.168.3.56", "1.0.0"))

    current[0] += timedelta(seconds=16)
    offline_agents = list_agents()

    assert [agent.id for agent in offline_agents] == ["PC01", "PC02"]
    assert [agent.status for agent in offline_agents] == [AgentStatus.OFFLINE] * 2
    with database.unit_of_work() as uow:
        assert uow.agents.get("PC01").status == AgentStatus.OFFLINE

    heartbeat("PC01")

    assert [agent.status for agent in list_agents()] == [
        AgentStatus.ONLINE,
        AgentStatus.OFFLINE,
    ]
