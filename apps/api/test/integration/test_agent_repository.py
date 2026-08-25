from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.domain.entities.agent import Agent
from app.infrastructure.persistence.database import SqliteDatabase

NOW = datetime(2026, 8, 25, 9, 0, tzinfo=UTC)


def test_sqlite_agent_repository_round_trip_and_order(tmp_path: Path) -> None:
    database = SqliteDatabase(tmp_path / "agents.db")
    database.initialize()

    with database.unit_of_work() as uow:
        uow.agents.add(
            Agent.register("PC02", "DESKTOP-B", "192.168.3.55", "1.0.0", NOW)
        )
        uow.agents.add(
            Agent.register("PC01", "DESKTOP-A", "192.168.3.56", "1.0.0", NOW)
        )
        uow.commit()

    with database.unit_of_work() as uow:
        agents = uow.agents.list_all()

        assert [agent.id for agent in agents] == ["PC01", "PC02"]
        assert agents[0].hostname == "DESKTOP-A"
        assert uow.agents.find("MISSING") is None


def test_sqlite_agent_repository_saves_heartbeat(tmp_path: Path) -> None:
    database = SqliteDatabase(tmp_path / "heartbeat.db")
    database.initialize()
    heartbeat_at = NOW + timedelta(seconds=5)

    with database.unit_of_work() as uow:
        uow.agents.add(
            Agent.register("PC01", "DESKTOP-A", "192.168.3.56", "1.0.0", NOW)
        )
        uow.commit()

    with database.unit_of_work() as uow:
        agent = uow.agents.get("PC01")
        agent.heartbeat(heartbeat_at)
        uow.agents.save(agent)
        uow.commit()

    with database.unit_of_work() as uow:
        saved = uow.agents.get("PC01")

        assert saved.last_seen == heartbeat_at
        assert saved.created_at == NOW
