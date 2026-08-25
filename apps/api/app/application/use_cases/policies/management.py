from __future__ import annotations

from datetime import UTC, datetime

from app.application.dtos.policies import (
    AcknowledgeCommandInput,
    PolicyProfileDetails,
)
from app.domain.entities.exam_session import ExamSession
from app.domain.entities.operations import Command
from app.domain.exceptions.errors import InvalidStateTransitionError, PolicyValidationError
from app.domain.interfaces.unit_of_work import UnitOfWorkFactory
from app.domain.services.policy_profiles import PolicyProfileCatalog
from app.domain.value_objects.enums import CommandStatus, CommandType


class ListPolicyProfiles:
    def __init__(self, catalog: PolicyProfileCatalog):
        self._catalog = catalog

    def __call__(self) -> list[PolicyProfileDetails]:
        return [
            PolicyProfileDetails(
                id=profile.id,
                label=profile.label,
                description=profile.description,
                rules=profile.rules,
            )
            for profile in self._catalog.list_all()
        ]


class GetPendingCommands:
    def __init__(self, uow_factory: UnitOfWorkFactory):
        self._uow_factory = uow_factory

    def __call__(self, target_id: str) -> list[Command]:
        with self._uow_factory() as uow:
            return uow.commands.pending_for_target(target_id.strip())


class AcknowledgeCommand:
    """Acknowledge policy commands for either direct or gateway sessions."""

    def __init__(self, uow_factory: UnitOfWorkFactory):
        self._uow_factory = uow_factory

    def __call__(self, data: AcknowledgeCommandInput) -> ExamSession:
        with self._uow_factory() as uow:
            command = uow.commands.get(data.command_id.strip())
            if command.status != CommandStatus.PENDING:
                raise InvalidStateTransitionError(
                    "command has already been acknowledged"
                )
            session = uow.sessions.get(command.session_id)
            command.acknowledged_at = datetime.now(UTC)

            if not data.success:
                self._record_failure(session, command, data.error)
                uow.sessions.save(session)
                uow.commands.save(command)
                uow.audits.append(
                    session.id,
                    actor=data.actor,
                    action="COMMAND_FAILED",
                    target=command.target_id,
                    details={
                        "command_id": command.id,
                        "type": command.type,
                        "error": command.error,
                    },
                )
                uow.commit()
                return session

            command.status = CommandStatus.ACKNOWLEDGED
            self._record_success(session, command, data.policy_hash)
            uow.sessions.save(session)
            uow.commands.save(command)
            uow.audits.append(
                session.id,
                actor=data.actor,
                action="COMMAND_ACKNOWLEDGED",
                target=command.target_id,
                details={"command_id": command.id, "type": command.type},
            )
            uow.commit()
            return session

    @staticmethod
    def _record_failure(
        session: ExamSession, command: Command, error: str | None
    ) -> None:
        command.status = CommandStatus.FAILED
        command.error = error or "target reported command failure"
        if command.type != CommandType.APPLY_POLICY:
            return
        if session.gateway_id is None:
            session.record_management_policy_failure(command.target_id)
        else:
            session.record_policy_failure(command.target_id)

    @staticmethod
    def _record_success(
        session: ExamSession, command: Command, policy_hash: str | None
    ) -> None:
        if command.type == CommandType.APPLY_POLICY:
            if not policy_hash:
                raise PolicyValidationError(
                    "APPLY_POLICY acknowledgement requires policy_hash"
                )
            if session.gateway_id is None:
                session.acknowledge_management_policy(command.target_id, policy_hash)
            else:
                session.acknowledge_policy(command.target_id, policy_hash)
        elif command.type == CommandType.RESTORE_BASELINE:
            if session.gateway_id is None:
                session.acknowledge_management_restore(command.target_id)
            else:
                session.acknowledge_restore(command.target_id)
