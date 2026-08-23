from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from app.domain.exceptions.errors import (
    InvalidStateTransitionError,
    PolicyValidationError,
    ReadinessGateError,
)
from app.domain.value_objects.enums import Readiness, SessionState


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class PolicyDocument:
    profile: str
    rules: dict[str, Any]
    version: int
    policy_hash: str

    @classmethod
    def create(cls, profile: str, rules: dict[str, Any], version: int) -> PolicyDocument:
        normalized_profile = profile.strip().upper()
        if not normalized_profile:
            raise PolicyValidationError("profile must not be empty")
        if version < 1:
            raise PolicyValidationError("policy version must be positive")

        applications = rules.get("applications", {})
        allowed = set(applications.get("allow", []))
        denied = set(applications.get("deny", []))
        overlap = sorted(allowed & denied)
        if overlap:
            raise PolicyValidationError(
                f"applications cannot be both allowed and denied: {', '.join(overlap)}"
            )

        payload = {"profile": normalized_profile, "rules": rules, "version": version}
        policy_hash = sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        return cls(normalized_profile, rules, version, policy_hash)


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    name: str
    passed: bool
    critical: bool = True
    details: str | None = None


@dataclass(slots=True)
class WorkstationSession:
    workstation_id: str
    readiness: Readiness = Readiness.UNKNOWN
    desired_policy_hash: str | None = None
    actual_policy_hash: str | None = None
    preflight_checks: list[PreflightCheck] = field(default_factory=list)
    restored: bool = False

    @property
    def policy_compliant(self) -> bool:
        return (
            self.desired_policy_hash is not None
            and self.actual_policy_hash == self.desired_policy_hash
        )

    def acknowledge_policy(self, policy_hash: str) -> None:
        if policy_hash != self.desired_policy_hash:
            raise PolicyValidationError(
                f"{self.workstation_id} acknowledged an unexpected policy hash"
            )
        self.actual_policy_hash = policy_hash

    def record_preflight(self, checks: list[PreflightCheck]) -> Readiness:
        if not checks:
            raise ReadinessGateError("preflight requires at least one check")
        self.preflight_checks = checks
        if any(check.critical and not check.passed for check in checks):
            self.readiness = Readiness.FAILED
        elif any(not check.passed for check in checks):
            self.readiness = Readiness.WARNING
        else:
            self.readiness = Readiness.READY
        return self.readiness


@dataclass(slots=True)
class ExamSession:
    id: str
    exam_name: str
    room_id: str
    gateway_id: str
    workstations: dict[str, WorkstationSession]
    state: SessionState = SessionState.CREATED
    policy: PolicyDocument | None = None
    gateway_policy_hash: str | None = None
    gateway_restored: bool = False
    force_started: bool = False
    force_start_reason: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    aggregate_version: int = 0

    @classmethod
    def create(
        cls,
        exam_name: str,
        room_id: str,
        gateway_id: str,
        workstation_ids: list[str],
    ) -> ExamSession:
        normalized_ids = [item.strip() for item in workstation_ids if item.strip()]
        if not exam_name.strip() or not room_id.strip() or not gateway_id.strip():
            raise PolicyValidationError("exam_name, room_id and gateway_id are required")
        if not normalized_ids:
            raise PolicyValidationError("at least one workstation is required")
        if len(normalized_ids) != len(set(normalized_ids)):
            raise PolicyValidationError("workstation ids must be unique")
        return cls(
            id=new_id("ses"),
            exam_name=exam_name.strip(),
            room_id=room_id.strip(),
            gateway_id=gateway_id.strip(),
            workstations={item: WorkstationSession(item) for item in normalized_ids},
        )

    def deploy_policy(self, profile: str, rules: dict[str, Any]) -> PolicyDocument:
        if self.state not in {SessionState.CREATED, SessionState.DEGRADED}:
            raise InvalidStateTransitionError(
                f"cannot deploy policy while session is {self.state}"
            )
        next_version = 1 if self.policy is None else self.policy.version + 1
        self.policy = PolicyDocument.create(profile, rules, next_version)
        self.gateway_policy_hash = None
        self.gateway_restored = False
        for workstation in self.workstations.values():
            workstation.desired_policy_hash = self.policy.policy_hash
            workstation.actual_policy_hash = None
            workstation.readiness = Readiness.UNKNOWN
            workstation.preflight_checks = []
            workstation.restored = False
        self.state = SessionState.DEPLOYING
        return self.policy

    def acknowledge_policy(self, target_id: str, policy_hash: str) -> None:
        if self.state != SessionState.DEPLOYING or self.policy is None:
            raise InvalidStateTransitionError("policy acknowledgements require DEPLOYING state")
        if policy_hash != self.policy.policy_hash:
            raise PolicyValidationError("acknowledged policy hash does not match desired policy")
        if target_id == self.gateway_id:
            self.gateway_policy_hash = policy_hash
        elif target_id in self.workstations:
            self.workstations[target_id].acknowledge_policy(policy_hash)
        else:
            raise PolicyValidationError(f"unknown policy target: {target_id}")

        if self.gateway_policy_hash == policy_hash and all(
            workstation.policy_compliant for workstation in self.workstations.values()
        ):
            self.state = SessionState.PREFLIGHT

    def record_policy_failure(self, target_id: str) -> None:
        if self.state != SessionState.DEPLOYING:
            raise InvalidStateTransitionError("policy failure requires DEPLOYING state")
        if target_id in self.workstations:
            self.workstations[target_id].readiness = Readiness.FAILED
        elif target_id != self.gateway_id:
            raise PolicyValidationError(f"unknown policy target: {target_id}")
        self.state = SessionState.DEGRADED

    def record_preflight(
        self, workstation_id: str, checks: list[PreflightCheck]
    ) -> Readiness:
        if self.state not in {SessionState.PREFLIGHT, SessionState.DEGRADED}:
            raise InvalidStateTransitionError("preflight reports require PREFLIGHT/DEGRADED state")
        workstation = self._workstation(workstation_id)
        if not workstation.policy_compliant:
            raise ReadinessGateError("workstation policy is not compliant")
        readiness = workstation.record_preflight(checks)

        if all(item.readiness != Readiness.UNKNOWN for item in self.workstations.values()):
            if any(item.readiness == Readiness.FAILED for item in self.workstations.values()):
                self.state = SessionState.DEGRADED
            else:
                self.state = SessionState.READY
        return readiness

    def start(self, force: bool, reason: str | None, at: datetime) -> None:
        if self.state == SessionState.READY:
            self.force_started = False
        elif force and self.state == SessionState.DEGRADED:
            if not reason or not reason.strip():
                raise ReadinessGateError("force-start requires a reason")
            self.force_started = True
            self.force_start_reason = reason.strip()
        else:
            raise ReadinessGateError(
                f"session cannot start from {self.state}; READY is required"
            )
        self.state = SessionState.RUNNING
        self.started_at = at

    def finish(self, at: datetime) -> None:
        if self.state != SessionState.RUNNING:
            raise InvalidStateTransitionError("only a RUNNING session can finish")
        self.state = SessionState.RESTORING
        self.finished_at = at
        for workstation in self.workstations.values():
            workstation.restored = False
        self.gateway_restored = False

    def acknowledge_restore(self, target_id: str) -> None:
        if self.state != SessionState.RESTORING:
            raise InvalidStateTransitionError("restore acknowledgement requires RESTORING state")
        if target_id == self.gateway_id:
            self.gateway_restored = True
        else:
            self._workstation(target_id).restored = True
        if self.gateway_restored and all(
            workstation.restored for workstation in self.workstations.values()
        ):
            self.state = SessionState.NORMAL

    def _workstation(self, workstation_id: str) -> WorkstationSession:
        try:
            return self.workstations[workstation_id]
        except KeyError as exc:
            raise PolicyValidationError(
                f"workstation {workstation_id} does not belong to this session"
            ) from exc

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["state"] = self.state.value
        value["created_at"] = self.created_at.isoformat()
        value["started_at"] = self.started_at.isoformat() if self.started_at else None
        value["finished_at"] = self.finished_at.isoformat() if self.finished_at else None
        for workstation in value["workstations"].values():
            workstation["readiness"] = workstation["readiness"].value
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ExamSession:
        policy_value = value.get("policy")
        policy = PolicyDocument(**policy_value) if policy_value else None
        workstations = {}
        for workstation_id, item in value["workstations"].items():
            checks = [PreflightCheck(**check) for check in item.get("preflight_checks", [])]
            workstations[workstation_id] = WorkstationSession(
                workstation_id=item["workstation_id"],
                readiness=Readiness(item["readiness"]),
                desired_policy_hash=item.get("desired_policy_hash"),
                actual_policy_hash=item.get("actual_policy_hash"),
                preflight_checks=checks,
                restored=item.get("restored", False),
            )
        return cls(
            id=value["id"],
            exam_name=value["exam_name"],
            room_id=value["room_id"],
            gateway_id=value["gateway_id"],
            workstations=workstations,
            state=SessionState(value["state"]),
            policy=policy,
            gateway_policy_hash=value.get("gateway_policy_hash"),
            gateway_restored=value.get("gateway_restored", False),
            force_started=value.get("force_started", False),
            force_start_reason=value.get("force_start_reason"),
            created_at=datetime.fromisoformat(value["created_at"]),
            started_at=(
                datetime.fromisoformat(value["started_at"])
                if value.get("started_at")
                else None
            ),
            finished_at=(
                datetime.fromisoformat(value["finished_at"])
                if value.get("finished_at")
                else None
            ),
            aggregate_version=value.get("aggregate_version", 0),
        )
