from typing import Annotated

from fastapi import Depends, Request

from app.application.use_cases.agents.management import (
    HeartbeatAgent,
    ListAgents,
    RegisterAgent,
)
from app.application.use_cases.exam_sessions.pipeline import ExamPipelineService


def get_pipeline_service(request: Request) -> ExamPipelineService:
    return request.app.state.container.pipeline_service


Service = Annotated[ExamPipelineService, Depends(get_pipeline_service)]


def get_register_agent(request: Request) -> RegisterAgent:
    return request.app.state.container.register_agent


def get_heartbeat_agent(request: Request) -> HeartbeatAgent:
    return request.app.state.container.heartbeat_agent


def get_list_agents(request: Request) -> ListAgents:
    return request.app.state.container.list_agents


RegisterAgentUseCase = Annotated[RegisterAgent, Depends(get_register_agent)]
HeartbeatAgentUseCase = Annotated[HeartbeatAgent, Depends(get_heartbeat_agent)]
ListAgentsUseCase = Annotated[ListAgents, Depends(get_list_agents)]

