from enum import StrEnum


class AgentStatus(StrEnum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class SessionState(StrEnum):
    CREATED = "CREATED"
    DEPLOYING = "DEPLOYING"
    PREFLIGHT = "PREFLIGHT"
    READY = "READY"
    DEGRADED = "DEGRADED"
    RUNNING = "RUNNING"
    RESTORING = "RESTORING"
    NORMAL = "NORMAL"


class Readiness(StrEnum):
    UNKNOWN = "UNKNOWN"
    READY = "READY"
    WARNING = "WARNING"
    FAILED = "FAILED"


class CommandType(StrEnum):
    APPLY_POLICY = "APPLY_POLICY"
    RESTORE_BASELINE = "RESTORE_BASELINE"


class CommandStatus(StrEnum):
    PENDING = "PENDING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FAILED = "FAILED"


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
