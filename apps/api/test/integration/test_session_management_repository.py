import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.domain.entities.agent import Agent
from app.domain.entities.exam_session import ExamSession
from app.domain.entities.session_workstation import SessionWorkstation
from app.infrastructure.persistence.database import SqliteDatabase

NOW = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)


def _agent(agent_id: str) -> Agent:
    return Agent.register(agent_id, f"HOST-{agent_id}", "192.168.3.55", "1.0.0", NOW)


def test_assignments_persist_without_agent_snapshot(tmp_path: Path) -> None:
    database = SqliteDatabase(tmp_path / "sessions.db")
    database.initialize()
    session = ExamSession.create_managed("Exam", "A101", ["PC01", "PC02"], NOW)
    first_assignment = SessionWorkstation.assign(session.id, "PC01", NOW)
    second_assignment = SessionWorkstation.assign(session.id, "PC02", NOW + timedelta(seconds=1))

    with database.unit_of_work() as uow:
        uow.agents.add(_agent("PC01"))
        uow.agents.add(_agent("PC02"))
        uow.sessions.add(session)
        uow.session_workstations.assign_many(
            [
                first_assignment,
                second_assignment,
            ]
        )
        uow.commit()

    with database.unit_of_work() as uow:
        assignments = uow.session_workstations.list_for_session(session.id)

    assert [item.agent_id for item in assignments] == ["PC01", "PC02"]
    assert not hasattr(assignments[0], "hostname")


def test_assignment_pair_is_unique(tmp_path: Path) -> None:
    database = SqliteDatabase(tmp_path / "unique.db")
    database.initialize()
    session = ExamSession.create_managed("Exam", "A101", ["PC01"], NOW)

    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"), database.unit_of_work() as uow:
        uow.agents.add(_agent("PC01"))
        uow.sessions.add(session)
        uow.session_workstations.assign_many(
            [
                SessionWorkstation.assign(session.id, "PC01", NOW),
                SessionWorkstation.assign(session.id, "PC01", NOW),
            ]
        )
        uow.commit()


def test_sessions_list_newest_first(tmp_path: Path) -> None:
    database = SqliteDatabase(tmp_path / "list.db")
    database.initialize()
    first_session = ExamSession.create_managed("First", "A101", ["PC01"], NOW)
    second_session = ExamSession.create_managed("Second", "A102", ["PC02"], NOW)

    with database.unit_of_work() as uow:
        uow.sessions.add(first_session)
        uow.commit()

    with database.unit_of_work() as uow:
        uow.sessions.add(second_session)
        uow.commit()

    with database.unit_of_work() as uow:
        sessions = uow.sessions.list_all()

    assert [session.id for session in sessions] == [second_session.id, first_session.id]


def test_session_and_assignments_roll_back_together(tmp_path: Path) -> None:
    database = SqliteDatabase(tmp_path / "rollback.db")
    database.initialize()
    session = ExamSession.create_managed("Exam", "A101", ["PC01"], NOW)
    assignment = SessionWorkstation.assign(session.id, "PC01", NOW)

    with pytest.raises(RuntimeError, match="rollback"), database.unit_of_work() as uow:
        uow.agents.add(_agent("PC01"))
        uow.sessions.add(session)
        uow.session_workstations.assign(assignment)
        raise RuntimeError("rollback")

    with database.unit_of_work() as uow:
        sessions = uow.sessions.list_all()
        assignments = uow.session_workstations.list_for_session(session.id)

    assert sessions == []
    assert assignments == []
