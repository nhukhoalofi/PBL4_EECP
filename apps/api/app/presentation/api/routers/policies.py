from fastapi import APIRouter

from app.application.dtos.policies import AcknowledgeCommandInput
from app.domain.entities.exam_session import ExamSession
from app.domain.entities.operations import Command
from app.presentation.api.deps import (
    AcknowledgeCommandUseCase,
    GetPendingCommandsUseCase,
    ListPolicyProfilesUseCase,
)
from app.presentation.schemas.exam_pipeline import SessionView
from app.presentation.schemas.policies import (
    AcknowledgeCommandRequest,
    CommandView,
    PolicyProfileView,
)
from app.presentation.serializers.policy_yaml import render_policy_yaml

router = APIRouter(prefix="/api/v1", tags=["policies"])


@router.get("/policy-profiles", response_model=list[PolicyProfileView])
def policy_profiles(use_case: ListPolicyProfilesUseCase) -> list[PolicyProfileView]:
    return [
        PolicyProfileView(
            id=profile.id,
            label=profile.label,
            description=profile.description,
            rules=profile.rules,
            yaml=render_policy_yaml(profile.id, profile.rules),
        )
        for profile in use_case()
    ]


@router.get("/agents/{target_id}/commands", response_model=list[CommandView])
def pending_commands(
    target_id: str, use_case: GetPendingCommandsUseCase
) -> list[CommandView]:
    return [_command_view(command) for command in use_case(target_id)]


@router.post("/commands/{command_id}/acknowledge", response_model=SessionView)
def acknowledge_command(
    command_id: str,
    body: AcknowledgeCommandRequest,
    use_case: AcknowledgeCommandUseCase,
) -> SessionView:
    session = use_case(
        AcknowledgeCommandInput(command_id=command_id, **body.model_dump())
    )
    return _session_view(session)


def _session_view(session: ExamSession) -> SessionView:
    return SessionView.model_validate(session.to_dict())


def _command_view(command: Command) -> CommandView:
    return CommandView(
        id=command.id,
        session_id=command.session_id,
        target_id=command.target_id,
        type=command.type,
        payload=command.payload,
        status=command.status,
        created_at=command.created_at,
    )
