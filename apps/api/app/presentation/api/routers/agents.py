from fastapi import APIRouter, status

from app.application.dtos.agents import RegisterAgentInput
from app.presentation.api.deps import (
    HeartbeatAgentUseCase,
    ListAgentsUseCase,
    RegisterAgentUseCase,
)
from app.presentation.schemas.agents import AgentView, RegisterAgentRequest

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.post(
    "/register",
    response_model=AgentView,
    status_code=status.HTTP_201_CREATED,
)
def register_agent(
    body: RegisterAgentRequest,
    use_case: RegisterAgentUseCase,
) -> AgentView:
    agent = use_case(
        RegisterAgentInput(
            agent_id=body.id,
            hostname=body.hostname,
            ip_address=body.ip_address,
            agent_version=body.agent_version,
        )
    )
    return AgentView.model_validate(agent)


@router.post("/{agent_id}/heartbeat", response_model=AgentView)
def heartbeat_agent(
    agent_id: str,
    use_case: HeartbeatAgentUseCase,
) -> AgentView:
    return AgentView.model_validate(use_case(agent_id))


@router.get("", response_model=list[AgentView])
def list_agents(use_case: ListAgentsUseCase) -> list[AgentView]:
    return [AgentView.model_validate(agent) for agent in use_case()]
