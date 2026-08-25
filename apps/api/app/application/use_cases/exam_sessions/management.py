from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from app.application.dtos.session_management import (
    AssignedAgentDetails,
    CreateExamSessionInput,
    ExamSessionDetails,
    UpdateExamSessionStatusInput,
)
from app.domain.entities.agent import Agent
from app.domain.entities.exam_session import ExamSession
from app.domain.entities.operations import Command
from app.domain.entities.session_workstation import SessionWorkstation
from app.domain.exceptions.errors import ReadinessGateError
from app.domain.interfaces.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.domain.services.policy_profiles import (
    BUILT_IN_POLICY_PROFILES,
    PolicyProfileCatalog,
)
from app.domain.value_objects.enums import AgentStatus, CommandType, Readiness, SessionState
from app.domain.value_objects.primitives import utc_now

Clock = Callable[[], datetime]


class CreateExamSession:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock = utc_now,
        policy_profiles: PolicyProfileCatalog = BUILT_IN_POLICY_PROFILES,
    ):
        self._uow_factory = uow_factory
        self._clock = clock
        self._policy_profiles = policy_profiles

    def __call__(self, data: CreateExamSessionInput) -> ExamSessionDetails:
        at = self._clock()
        session = ExamSession.create_managed(data.name, data.room, data.agent_ids, at)
        profile = self._policy_profiles.get(data.policy_profile)
        policy = session.assign_management_policy(profile.id, profile.rules)
        agent_ids = list(session.workstations)
        offline_ids: list[str] = []
        with self._uow_factory() as uow:
            agents = [uow.agents.get(agent_id) for agent_id in agent_ids]
            for agent in agents:
                if agent.refresh_liveness(at):
                    uow.agents.save(agent)
                if agent.status == AgentStatus.OFFLINE:
                    offline_ids.append(agent.id)
            if offline_ids:
                uow.commit()
            else:
                uow.sessions.add(session)
                uow.session_workstations.assign_many(
                    [SessionWorkstation.assign(session.id, agent.id, at) for agent in agents]
                )
                uow.commands.add_many(
                    [
                        Command(
                            session_id=session.id,
                            target_id=agent.id,
                            type=CommandType.APPLY_POLICY,
                            payload={
                                "format": "eecp-policy/v1",
                                "policy_hash": policy.policy_hash,
                                "version": policy.version,
                                "profile": policy.profile,
                                "rules": policy.rules,
                            },
                        )
                        for agent in agents
                    ]
                )
                uow.audits.append(
                    session.id,
                    actor=data.actor,
                    action="SESSION_CREATED",
                    target=session.id,
                    details={
                        "room_id": session.room_id,
                        "workstations": sorted(session.workstations),
                        "policy_profile": policy.profile,
                        "policy_hash": policy.policy_hash,
                    },
                )
                uow.commit()
                return ExamSessionDetails(
                    session=session,
                    agents=[
                        AssignedAgentDetails(
                            id=agent.id,
                            hostname=agent.hostname,
                            ip_address=agent.ip_address,
                            status=agent.status,
                            last_seen=agent.last_seen,
                            assigned_at=at,
                            policy_status="PENDING",
                        )
                        for agent in agents
                    ],
                )

        raise ReadinessGateError(f"offline agents cannot be assigned: {', '.join(offline_ids)}")


class GetExamSession:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock = utc_now):
        self._uow_factory = uow_factory
        self._clock = clock

    def __call__(self, session_id: str) -> ExamSessionDetails:
        normalized_id = session_id.strip()
        at = self._clock()
        with self._uow_factory() as uow:
            session = uow.sessions.get(normalized_id)
            details = _details(uow, session, at)
            uow.commit()
            return details


class ListExamSessions:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock = utc_now):
        self._uow_factory = uow_factory
        self._clock = clock

    def __call__(self) -> list[ExamSessionDetails]:
        at = self._clock()
        with self._uow_factory() as uow:
            details = [_details(uow, session, at) for session in uow.sessions.list_all()]
            uow.commit()
            return details


class UpdateExamSessionStatus:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock = utc_now):
        self._uow_factory = uow_factory
        self._clock = clock

    def __call__(self, data: UpdateExamSessionStatusInput) -> ExamSessionDetails:
        session_id = data.session_id.strip()
        at = self._clock()
        offline_ids: list[str] = []
        with self._uow_factory() as uow:
            session = uow.sessions.get(session_id)
            readiness_transition = (
                session.gateway_id is None
                and session.state == SessionState.CREATED
                and data.status == SessionState.READY
            )
            if readiness_transition:
                details = _details(uow, session, at)
                offline_ids = [
                    agent.id for agent in details.agents if agent.status != AgentStatus.ONLINE
                ]
                if offline_ids:
                    uow.commit()
                else:
                    self._transition(uow, session, data, at)
                    uow.commit()
                    return details
            else:
                details = _snapshot_details(uow, session)
                self._transition(uow, session, data, at)
                uow.commit()
                return details

        raise ReadinessGateError(f"offline agents block readiness: {', '.join(offline_ids)}")

    @staticmethod
    def _transition(
        uow: UnitOfWork,
        session: ExamSession,
        data: UpdateExamSessionStatusInput,
        at: datetime,
    ) -> None:
        session.transition_management(data.status, at)
        uow.sessions.save(session)
        if data.status == SessionState.FINISHED and session.policy is not None:
            uow.commands.add_many(
                [
                    Command(
                        session_id=session.id,
                        target_id=agent_id,
                        type=CommandType.RESTORE_BASELINE,
                        payload={
                            "format": "eecp-policy/v1",
                            "policy_hash": session.policy.policy_hash,
                            "baseline": "NORMAL",
                        },
                    )
                    for agent_id in sorted(session.workstations)
                ]
            )
        uow.audits.append(
            session.id,
            actor=data.actor,
            action="SESSION_STATUS_UPDATED",
            target=session.id,
            details={"state": session.state},
        )


def _details(uow: UnitOfWork, session: ExamSession, at: datetime) -> ExamSessionDetails:
    return _build_details(uow, session, refresh_at=at)


def _snapshot_details(uow: UnitOfWork, session: ExamSession) -> ExamSessionDetails:
    return _build_details(uow, session, refresh_at=None)


def _build_details(
    uow: UnitOfWork,
    session: ExamSession,
    refresh_at: datetime | None,
) -> ExamSessionDetails:
    assignments = _assignment_targets(uow, session)
    agents = []
    for agent_id, assigned_at in assignments:
        agent = uow.agents.find(agent_id)
        if agent is None:
            agents.append(
                AssignedAgentDetails(
                    id=agent_id,
                    hostname=None,
                    ip_address=None,
                    status=None,
                    last_seen=None,
                    assigned_at=assigned_at,
                    policy_status=_policy_status(session, agent_id),
                )
            )
            continue
        if refresh_at is not None and agent.refresh_liveness(refresh_at):
            uow.agents.save(agent)
        agents.append(_agent_details(session, agent, assigned_at))
    return ExamSessionDetails(session=session, agents=agents)


def _assignment_targets(uow: UnitOfWork, session: ExamSession) -> list[tuple[str, datetime | None]]:
    assignments = uow.session_workstations.list_for_session(session.id)
    if assignments or session.gateway_id is None:
        return [(assignment.agent_id, assignment.assigned_at) for assignment in assignments]
    return [(agent_id, None) for agent_id in sorted(session.workstations)]


def _agent_details(
    session: ExamSession, agent: Agent, assigned_at: datetime | None
) -> AssignedAgentDetails:
    return AssignedAgentDetails(
        id=agent.id,
        hostname=agent.hostname,
        ip_address=agent.ip_address,
        status=agent.status,
        last_seen=agent.last_seen,
        assigned_at=assigned_at,
        policy_status=_policy_status(session, agent.id),
    )


def _policy_status(session: ExamSession, agent_id: str) -> str:
    workstation = session.workstations[agent_id]
    if workstation.restored and session.state == SessionState.FINISHED:
        return "RESTORED"
    if workstation.policy_compliant:
        return "APPLIED"
    if workstation.readiness == Readiness.FAILED:
        return "FAILED"
    if workstation.desired_policy_hash:
        return "PENDING"
    return "NOT_ASSIGNED"
