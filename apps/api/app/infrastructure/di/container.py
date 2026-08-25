from __future__ import annotations

from dataclasses import dataclass

from app.application.use_cases.agents.management import (
    HeartbeatAgent,
    ListAgents,
    RegisterAgent,
)
from app.application.use_cases.exam_sessions.pipeline import ExamPipelineService
from app.config import Settings
from app.infrastructure.persistence.database import SqliteDatabase


@dataclass(frozen=True, slots=True)
class Container:
    database: SqliteDatabase
    pipeline_service: ExamPipelineService
    register_agent: RegisterAgent
    heartbeat_agent: HeartbeatAgent
    list_agents: ListAgents


def build_container(settings: Settings) -> Container:
    database = SqliteDatabase(settings.database_path)
    database.initialize()
    return Container(
        database=database,
        pipeline_service=ExamPipelineService(database.unit_of_work),
        register_agent=RegisterAgent(database.unit_of_work),
        heartbeat_agent=HeartbeatAgent(database.unit_of_work),
        list_agents=ListAgents(database.unit_of_work),
    )
