from __future__ import annotations

from fastapi import APIRouter, status

from app.application.dtos.exam_pipeline import (
    AcknowledgeCommandInput,
    CreateSessionInput,
    DeployPolicyInput,
    StartSessionInput,
    SubmitPreflightInput,
    TelemetryInput,
)
from app.domain.entities.exam_session import ExamSession, PreflightCheck
from app.domain.entities.operations import Command
from app.presentation.api.deps import Service
from app.presentation.schemas.exam_pipeline import (
    AcknowledgeCommandRequest,
    CommandView,
    CreateSessionRequest,
    DeployPolicyRequest,
    FinishSessionRequest,
    SessionView,
    StartSessionRequest,
    SubmitPreflightRequest,
    TelemetryAcceptedView,
    TelemetryRequest,
)

router = APIRouter(prefix="/api/v1", tags=["exam-pipeline"])


@router.post("/sessions", response_model=SessionView, status_code=status.HTTP_201_CREATED)
def create_session(
    body: CreateSessionRequest,
    service: Service,
) -> SessionView:
    session = service.create_session(CreateSessionInput(**body.model_dump()))
    return _session_view(session)


@router.get("/sessions/{session_id}", response_model=SessionView)
def get_session(
    session_id: str, service: Service
) -> SessionView:
    return _session_view(service.get_session(session_id))


@router.post("/sessions/{session_id}/policy/deploy", response_model=SessionView)
def deploy_policy(
    session_id: str,
    body: DeployPolicyRequest,
    service: Service,
) -> SessionView:
    session = service.deploy_policy(DeployPolicyInput(session_id=session_id, **body.model_dump()))
    return _session_view(session)


@router.get("/agents/{target_id}/commands", response_model=list[CommandView])
def pending_commands(
    target_id: str, service: Service
) -> list[CommandView]:
    return [_command_view(command) for command in service.pending_commands(target_id)]


@router.post("/commands/{command_id}/acknowledge", response_model=SessionView)
def acknowledge_command(
    command_id: str,
    body: AcknowledgeCommandRequest,
    service: Service,
) -> SessionView:
    session = service.acknowledge_command(
        AcknowledgeCommandInput(command_id=command_id, **body.model_dump())
    )
    return _session_view(session)


@router.post(
    "/sessions/{session_id}/workstations/{workstation_id}/preflight",
    response_model=SessionView,
)
def submit_preflight(
    session_id: str,
    workstation_id: str,
    body: SubmitPreflightRequest,
    service: Service,
) -> SessionView:
    checks = [PreflightCheck(**check.model_dump()) for check in body.checks]
    session = service.submit_preflight(
        SubmitPreflightInput(
            session_id=session_id,
            workstation_id=workstation_id,
            checks=checks,
            actor=body.actor,
        )
    )
    return _session_view(session)


@router.post("/sessions/{session_id}/start", response_model=SessionView)
def start_session(
    session_id: str,
    body: StartSessionRequest,
    service: Service,
) -> SessionView:
    session = service.start_session(StartSessionInput(session_id=session_id, **body.model_dump()))
    return _session_view(session)


@router.post(
    "/sessions/{session_id}/telemetry",
    response_model=TelemetryAcceptedView,
    status_code=status.HTTP_202_ACCEPTED,
)
def ingest_telemetry(
    session_id: str,
    body: TelemetryRequest,
    service: Service,
) -> TelemetryAcceptedView:
    event, incident_id = service.ingest_telemetry(
        TelemetryInput(session_id=session_id, **body.model_dump())
    )
    return TelemetryAcceptedView(event_id=event.id, incident_id=incident_id)


@router.post("/sessions/{session_id}/finish", response_model=SessionView)
def finish_session(
    session_id: str,
    body: FinishSessionRequest,
    service: Service,
) -> SessionView:
    return _session_view(service.finish_session(session_id, body.actor))


@router.get("/sessions/{session_id}/summary")
def get_summary(session_id: str, service: Service) -> dict:
    return service.get_summary(session_id)


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
