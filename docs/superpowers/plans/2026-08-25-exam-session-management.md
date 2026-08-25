# Phase 2 Exam Session Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add teacher-facing exam session creation, workstation assignment, listing, detail, and simplified status management without breaking the existing policy pipeline.

**Architecture:** Extend the existing `ExamSession` aggregate with a gateway-less management mode and persist management assignments in a new `session_workstations` join table. New application use cases enrich sessions from current Agent records, while the existing pipeline service and endpoints remain intact. Next.js pages use server-side queries and Server Actions so the browser does not call FastAPI directly on the LAN.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLite, pytest, Ruff, Next.js 16 App Router, React 19, TypeScript 5.9.

**Spec:** `docs/superpowers/specs/2026-08-25-exam-session-management-design.md`

## Global Constraints

- Keep the existing Clean Architecture dependency direction: domain -> application -> infrastructure -> presentation.
- Reuse the existing `ExamSession`; do not create a duplicate session aggregate or router.
- Preserve all existing pipeline endpoints and the advanced `DEPLOYING/PREFLIGHT/DEGRADED/RESTORING/NORMAL` lifecycle.
- Management sessions have `gateway_id=None`; pipeline sessions have a non-empty gateway.
- Only management sessions use `CREATED -> READY -> RUNNING -> FINISHED`.
- Management creation requires at least one registered ONLINE Agent.
- Recheck all assigned Agents before `CREATED -> READY`; return conflict when any is OFFLINE.
- Do not copy hostname, IP, version, heartbeat, or Agent status into `session_workstations`.
- Do not add a new frontend test framework in this phase.
- Preserve unrelated user changes in the working tree.

## File Map

Backend domain and persistence:

- Modify `apps/api/app/domain/value_objects/enums.py` for `FINISHED`.
- Modify `apps/api/app/domain/entities/exam_session.py` for management mode, transitions, optional gateway, and `updated_at` compatibility.
- Create `apps/api/app/domain/entities/session_workstation.py` for assignment metadata.
- Modify `apps/api/app/domain/interfaces/unit_of_work.py` for list and assignment repository ports.
- Modify `apps/api/app/infrastructure/persistence/database.py` for the join table.
- Modify `apps/api/app/infrastructure/repositories/sqlite.py` for repository adapters and Unit of Work wiring.

Backend application and HTTP:

- Create `apps/api/app/application/dtos/session_management.py` for management inputs and enriched outputs.
- Create `apps/api/app/application/use_cases/exam_sessions/management.py` for four focused use cases.
- Modify `apps/api/app/infrastructure/di/container.py` and `apps/api/app/presentation/api/deps.py` for dependency injection.
- Modify `apps/api/app/presentation/schemas/exam_pipeline.py` for compatible request/response schemas.
- Modify `apps/api/app/presentation/api/routers/exam_sessions.py` to route old and new creation forms and add list/status endpoints.

Frontend:

- Modify `apps/web/lib/api-client.ts` to support JSON mutations and structured API errors.
- Modify `apps/web/features/exam-sessions/types.ts` and `queries.ts` for session data.
- Create `apps/web/features/exam-sessions/mutations.ts` for FastAPI mutation calls.
- Create `apps/web/features/exam-sessions/components/session-list.tsx`.
- Create `apps/web/features/exam-sessions/components/create-session-form.tsx`.
- Modify `apps/web/features/exam-sessions/index.ts` exports.
- Create `apps/web/app/sessions/actions.ts`, `page.tsx`, and `create/page.tsx`.
- Modify `apps/web/app/globals.css` for responsive session UI.

Tests and docs:

- Create `apps/api/test/unit/test_exam_session_management_domain.py`.
- Create `apps/api/test/integration/test_session_management_repository.py`.
- Create `apps/api/test/unit/test_session_management_use_cases.py`.
- Create `apps/api/test/integration/test_session_management_api.py`.
- Modify `README.md` with Phase 2 API and LAN demo steps.

---

### Task 1: Management Lifecycle in the Existing Domain

**Files:**
- Create: `apps/api/app/domain/entities/session_workstation.py`
- Modify: `apps/api/app/domain/entities/exam_session.py`
- Modify: `apps/api/app/domain/value_objects/enums.py`
- Test: `apps/api/test/unit/test_exam_session_management_domain.py`

**Interfaces:**
- Produces: `SessionState.FINISHED`.
- Produces: `SessionWorkstation.assign(session_id: str, agent_id: str, at: datetime) -> SessionWorkstation`.
- Produces: `ExamSession.create_managed(name: str, room: str, agent_ids: list[str], at: datetime) -> ExamSession`.
- Produces: `ExamSession.transition_management(target: SessionState, at: datetime) -> None`.
- Preserves: `ExamSession.create(exam_name, room_id, gateway_id, workstation_ids)` and all pipeline methods.

- [ ] **Step 1: Write failing domain tests for managed creation and association normalization**

Create `apps/api/test/unit/test_exam_session_management_domain.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.entities.exam_session import ExamSession
from app.domain.entities.session_workstation import SessionWorkstation
from app.domain.exceptions.errors import InvalidStateTransitionError, PolicyValidationError
from app.domain.value_objects.enums import SessionState


NOW = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)


def test_create_managed_session_has_no_gateway_and_tracks_updated_at() -> None:
    session = ExamSession.create_managed(
        " PBL4 Final ", " A101 ", [" PC01 ", "PC02"], NOW
    )

    assert session.exam_name == "PBL4 Final"
    assert session.room_id == "A101"
    assert session.gateway_id is None
    assert session.state == SessionState.CREATED
    assert sorted(session.workstations) == ["PC01", "PC02"]
    assert session.created_at == NOW
    assert session.updated_at == NOW


def test_session_workstation_assignment_contains_only_relation_data() -> None:
    assignment = SessionWorkstation.assign("ses_1", " PC01 ", NOW)

    assert assignment.id.startswith("sws_")
    assert assignment.session_id == "ses_1"
    assert assignment.agent_id == "PC01"
    assert assignment.assigned_at == NOW


def test_managed_creation_rejects_duplicate_agent_ids() -> None:
    with pytest.raises(PolicyValidationError, match="unique"):
        ExamSession.create_managed("Exam", "A101", ["PC01", " PC01 "], NOW)
```

- [ ] **Step 2: Run the new domain tests and confirm RED**

Run:

```powershell
uv run pytest apps/api/test/unit/test_exam_session_management_domain.py -q
```

Expected: collection or assertion failures because `SessionWorkstation`,
`create_managed`, `updated_at`, and `FINISHED` do not exist.

- [ ] **Step 3: Add the association entity and minimal managed factory**

Create `session_workstation.py` with this public shape:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.entities.exam_session import new_id
from app.domain.exceptions.errors import PolicyValidationError


@dataclass(frozen=True, slots=True)
class SessionWorkstation:
    id: str
    session_id: str
    agent_id: str
    assigned_at: datetime

    @classmethod
    def assign(
        cls, session_id: str, agent_id: str, at: datetime
    ) -> SessionWorkstation:
        normalized_session = session_id.strip()
        normalized_agent = agent_id.strip()
        if not normalized_session or not normalized_agent:
            raise PolicyValidationError("session id and agent id are required")
        return cls(new_id("sws"), normalized_session, normalized_agent, at)
```

In `ExamSession`, change `gateway_id` to `str | None`, add `updated_at`, and add
`create_managed`. Make legacy `create()` explicitly set the same timestamp for
`created_at` and `updated_at` while preserving its call signature.

- [ ] **Step 4: Run the domain tests and make managed creation GREEN**

Run:

```powershell
uv run pytest apps/api/test/unit/test_exam_session_management_domain.py -q
```

Expected: the three creation/association tests pass.

- [ ] **Step 5: Add failing tests for lifecycle isolation and timestamps**

Append:

```python
def test_management_lifecycle_reaches_finished_in_order() -> None:
    session = ExamSession.create_managed("Exam", "A101", ["PC01"], NOW)

    session.transition_management(SessionState.READY, NOW + timedelta(seconds=1))
    session.transition_management(SessionState.RUNNING, NOW + timedelta(seconds=2))
    session.transition_management(SessionState.FINISHED, NOW + timedelta(seconds=3))

    assert session.state == SessionState.FINISHED
    assert session.started_at == NOW + timedelta(seconds=2)
    assert session.finished_at == NOW + timedelta(seconds=3)
    assert session.updated_at == NOW + timedelta(seconds=3)


def test_management_lifecycle_rejects_skipped_transition() -> None:
    session = ExamSession.create_managed("Exam", "A101", ["PC01"], NOW)

    with pytest.raises(InvalidStateTransitionError, match="CREATED"):
        session.transition_management(SessionState.RUNNING, NOW)


def test_pipeline_session_rejects_management_transition() -> None:
    session = ExamSession.create("Exam", "A101", "gw-a101", ["PC01"])

    with pytest.raises(InvalidStateTransitionError, match="pipeline"):
        session.transition_management(SessionState.READY, NOW)


def test_management_session_rejects_policy_deployment() -> None:
    session = ExamSession.create_managed("Exam", "A101", ["PC01"], NOW)

    with pytest.raises(InvalidStateTransitionError, match="gateway"):
        session.deploy_policy("PROGRAMMING_EXAM", {})
```

- [ ] **Step 6: Run lifecycle tests and confirm RED**

Run the same test file. Expected: failures because `transition_management` and
`SessionState.FINISHED` are absent and deploy does not guard missing gateways.

- [ ] **Step 7: Implement lifecycle transitions and backward-compatible serialization**

Add `FINISHED` to `SessionState`. Implement the transition table exactly:

```python
allowed = {
    SessionState.CREATED: SessionState.READY,
    SessionState.READY: SessionState.RUNNING,
    SessionState.RUNNING: SessionState.FINISHED,
}
```

Reject calls when `gateway_id is not None`. Set `started_at` on RUNNING,
`finished_at` on FINISHED, and always set `updated_at=at`. Add `updated_at` to
`to_dict()` and parse it in `from_dict()` with:

```python
updated_at=datetime.fromisoformat(value.get("updated_at", value["created_at"])),
```

Guard `deploy_policy()` when `gateway_id is None`. Update all existing pipeline
state mutations to touch `updated_at`, using an existing `at` argument where one
exists and `utc_now()` otherwise.

- [ ] **Step 8: Run all domain and pipeline tests**

Run:

```powershell
uv run pytest apps/api/test/unit/test_exam_session_management_domain.py apps/api/test/unit/test_domain_pipeline.py -q
```

Expected: all tests pass.

- [ ] **Step 9: Commit the domain change**

```powershell
git add apps/api/app/domain/entities/session_workstation.py apps/api/app/domain/entities/exam_session.py apps/api/app/domain/value_objects/enums.py apps/api/test/unit/test_exam_session_management_domain.py
git commit -m "feat: extend exam session management domain"
```

---

### Task 2: SQLite Assignment Persistence and Repository Ports

**Files:**
- Modify: `apps/api/app/domain/interfaces/unit_of_work.py`
- Modify: `apps/api/app/infrastructure/persistence/database.py`
- Modify: `apps/api/app/infrastructure/repositories/sqlite.py`
- Test: `apps/api/test/integration/test_session_management_repository.py`

**Interfaces:**
- Consumes: `SessionWorkstation` from Task 1.
- Produces: `SessionRepository.list_all() -> list[ExamSession]`.
- Produces: `SessionWorkstationRepository.assign(assignment) -> None`.
- Produces: `SessionWorkstationRepository.assign_many(assignments) -> None`.
- Produces: `SessionWorkstationRepository.list_for_session(session_id) -> list[SessionWorkstation]`.
- Produces: `UnitOfWork.session_workstations`.

- [ ] **Step 1: Write failing repository integration tests**

Create the database, registered Agents, managed session, and assignments using
real repositories:

```python
from datetime import UTC, datetime
import sqlite3
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

    with database.unit_of_work() as uow:
        uow.agents.add(_agent("PC01"))
        uow.agents.add(_agent("PC02"))
        uow.sessions.add(session)
        uow.session_workstations.assign_many(
            [
                SessionWorkstation.assign(session.id, "PC01", NOW),
                SessionWorkstation.assign(session.id, "PC02", NOW),
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

    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        with database.unit_of_work() as uow:
            uow.agents.add(_agent("PC01"))
            uow.sessions.add(session)
            uow.session_workstations.assign_many(
                [
                    SessionWorkstation.assign(session.id, "PC01", NOW),
                    SessionWorkstation.assign(session.id, "PC01", NOW),
                ]
            )
            uow.commit()
```

- [ ] **Step 2: Run repository tests and confirm RED**

```powershell
uv run pytest apps/api/test/integration/test_session_management_repository.py -q
```

Expected: failures because the table, repository port, adapter, and UoW member do
not exist.

- [ ] **Step 3: Add schema and repository protocols**

Add `session_workstations` SQL exactly as specified in the design, including both
foreign keys, unique pair, and session index. Extend `SessionRepository` with
`list_all()`. Define:

```python
class SessionWorkstationRepository(Protocol):
    def assign(self, assignment: SessionWorkstation) -> None: ...
    def assign_many(self, assignments: Sequence[SessionWorkstation]) -> None: ...
    def list_for_session(self, session_id: str) -> list[SessionWorkstation]: ...
```

Expose it as `session_workstations` on `UnitOfWork`.

- [ ] **Step 4: Implement SQLite adapters and UoW wiring**

Implement `SqliteSessionRepository.list_all()` by selecting payloads in reverse
row insertion order and deserializing each aggregate. Implement
`SqliteSessionWorkstationRepository` with explicit columns only:

```sql
INSERT INTO session_workstations(id, session_id, agent_id, assigned_at)
VALUES (?, ?, ?, ?)
```

and:

```sql
SELECT id, session_id, agent_id, assigned_at
FROM session_workstations
WHERE session_id = ?
ORDER BY assigned_at, id
```

Instantiate the adapter in `SqliteUnitOfWork.__enter__`.

- [ ] **Step 5: Add and verify list/rollback tests**

Add a test that creates two sessions in separate transactions and asserts
`list_all()` returns newest first. Add a rollback test that raises inside the UoW
after adding a session and assignments, then confirms neither was persisted.

Run:

```powershell
uv run pytest apps/api/test/integration/test_session_management_repository.py apps/api/test/integration/test_agent_repository.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Run the existing pipeline integration test**

```powershell
uv run pytest apps/api/test/integration/test_pipeline_api.py -q
```

Expected: existing pipeline tests pass without requiring Agent registration.

- [ ] **Step 7: Commit persistence changes**

```powershell
git add apps/api/app/domain/interfaces/unit_of_work.py apps/api/app/infrastructure/persistence/database.py apps/api/app/infrastructure/repositories/sqlite.py apps/api/test/integration/test_session_management_repository.py
git commit -m "feat: persist exam session workstation assignments"
```

---

### Task 3: Management Use Cases and Enriched Session DTOs

**Files:**
- Create: `apps/api/app/application/dtos/session_management.py`
- Create: `apps/api/app/application/use_cases/exam_sessions/management.py`
- Test: `apps/api/test/unit/test_session_management_use_cases.py`

**Interfaces:**
- Consumes: repositories and domain methods from Tasks 1-2.
- Produces: `CreateExamSession`, `GetExamSession`, `ListExamSessions`, and `UpdateExamSessionStatus` callable classes.
- Produces: `ExamSessionDetails` with `session`, `agents`, and computed `agent_count`.
- Produces: `AssignedAgentDetails` with nullable live fields for unregistered legacy targets.

- [ ] **Step 1: Define wished-for DTO usage in failing create tests**

Use a real temporary SQLite database so the test covers transaction behavior and
does not assert against mocks:

```python
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.application.dtos.session_management import (
    CreateExamSessionInput,
    UpdateExamSessionStatusInput,
)
from app.application.use_cases.exam_sessions.management import (
    CreateExamSession,
    GetExamSession,
    ListExamSessions,
    UpdateExamSessionStatus,
)
from app.domain.entities.agent import Agent
from app.domain.exceptions.errors import EntityNotFoundError, ReadinessGateError
from app.domain.value_objects.enums import SessionState
from app.infrastructure.persistence.database import SqliteDatabase


NOW = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)


def _database(tmp_path: Path) -> SqliteDatabase:
    database = SqliteDatabase(tmp_path / "management.db")
    database.initialize()
    return database


def _register(database: SqliteDatabase, agent_id: str, last_seen=NOW) -> None:
    with database.unit_of_work() as uow:
        uow.agents.add(
            Agent.register(agent_id, f"HOST-{agent_id}", "192.168.3.55", "1.0.0", last_seen)
        )
        uow.commit()


def test_create_session_assigns_online_agents(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _register(database, "PC01")
    _register(database, "PC02")

    details = CreateExamSession(database.unit_of_work, clock=lambda: NOW)(
        CreateExamSessionInput("PBL4 Final", "A101", ["PC01", "PC02"])
    )

    assert details.session.state == SessionState.CREATED
    assert details.agent_count == 2
    assert [agent.id for agent in details.agents] == ["PC01", "PC02"]


def test_create_session_rejects_unknown_agent(tmp_path: Path) -> None:
    database = _database(tmp_path)

    with pytest.raises(EntityNotFoundError, match="PC99"):
        CreateExamSession(database.unit_of_work, clock=lambda: NOW)(
            CreateExamSessionInput("Exam", "A101", ["PC99"])
        )


def test_create_session_rejects_offline_agent(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _register(database, "PC01", NOW - timedelta(seconds=16))

    with pytest.raises(ReadinessGateError, match="PC01"):
        CreateExamSession(database.unit_of_work, clock=lambda: NOW)(
            CreateExamSessionInput("Exam", "A101", ["PC01"])
        )
```

- [ ] **Step 2: Run the use-case tests and confirm RED**

```powershell
uv run pytest apps/api/test/unit/test_session_management_use_cases.py -q
```

Expected: import failures because the DTO and use-case modules do not exist.

- [ ] **Step 3: Implement immutable input and output DTOs**

Define these exact public dataclasses:

```python
@dataclass(frozen=True, slots=True)
class CreateExamSessionInput:
    name: str
    room: str
    agent_ids: list[str]
    actor: str = "teacher"


@dataclass(frozen=True, slots=True)
class UpdateExamSessionStatusInput:
    session_id: str
    status: SessionState
    actor: str = "teacher"


@dataclass(frozen=True, slots=True)
class AssignedAgentDetails:
    id: str
    hostname: str | None
    ip_address: str | None
    status: AgentStatus | None
    last_seen: datetime | None
    assigned_at: datetime | None


@dataclass(frozen=True, slots=True)
class ExamSessionDetails:
    session: ExamSession
    agents: list[AssignedAgentDetails]

    @property
    def agent_count(self) -> int:
        return len(self.session.workstations)
```

- [ ] **Step 4: Implement CreateExamSession minimally and make create tests GREEN**

Normalize the IDs before any database call. In one UoW, call `uow.agents.get`,
refresh each Agent with the injected clock, save status changes, collect OFFLINE
IDs, then create the aggregate and assignments. Raise:

```python
ReadinessGateError(f"offline agents cannot be assigned: {', '.join(offline_ids)}")
```

Append a `SESSION_CREATED` audit event after `uow.sessions.add(session)` and
commit once. Return details built from the real Agent values.

Run the three tests and expect PASS.

- [ ] **Step 5: Add failing get/list/status tests**

Append tests that:

1. Create a session and assert `GetExamSession` returns current hostname, IP,
   status, last seen, and assignment time.
2. Create two sessions and assert `ListExamSessions` returns newest first.
3. Set an assigned Agent heartbeat to 16 seconds old, then assert
   `CREATED -> READY` raises `ReadinessGateError` and persists OFFLINE.
4. Assert valid READY, RUNNING, and FINISHED patches succeed in order.
5. Create a legacy gateway session through `ExamPipelineService` and assert
   `UpdateExamSessionStatus` rejects it with `InvalidStateTransitionError`.

Use literal timestamps and statuses in all assertions.

- [ ] **Step 6: Run the expanded tests and confirm RED**

Expected: failures because Get/List/Update classes and shared enrichment do not
exist.

- [ ] **Step 7: Implement Get, List, Update, and shared enrichment**

Implement `_details(uow, session, at)` as an application helper:

- For management sessions, use `uow.session_workstations.list_for_session`.
- For legacy sessions without rows, synthesize assignment IDs from sorted
  `session.workstations` and use `assigned_at=None`.
- Use `uow.agents.find`; unregistered legacy targets produce nullable live
  fields rather than failing the read.
- Refresh and save registered Agent liveness before returning.

`UpdateExamSessionStatus` loads details, rechecks ONLINE only when the requested
status is READY, delegates transition validation, saves, audits
`SESSION_STATUS_UPDATED`, and commits.

- [ ] **Step 8: Verify all use cases and regression tests**

```powershell
uv run pytest apps/api/test/unit/test_session_management_use_cases.py apps/api/test/unit/test_agent_use_cases.py apps/api/test/integration/test_pipeline_api.py -q
```

Expected: all tests pass.

- [ ] **Step 9: Commit application changes**

```powershell
git add apps/api/app/application/dtos/session_management.py apps/api/app/application/use_cases/exam_sessions/management.py apps/api/test/unit/test_session_management_use_cases.py
git commit -m "feat: add exam session management use cases"
```

---

### Task 4: Compatible FastAPI Session Management Endpoints

**Files:**
- Modify: `apps/api/app/infrastructure/di/container.py`
- Modify: `apps/api/app/presentation/api/deps.py`
- Modify: `apps/api/app/presentation/schemas/exam_pipeline.py`
- Modify: `apps/api/app/presentation/api/routers/exam_sessions.py`
- Test: `apps/api/test/integration/test_session_management_api.py`

**Interfaces:**
- Consumes: all four management use cases from Task 3.
- Produces: management and pipeline variants for `POST /api/v1/sessions`.
- Produces: `GET /api/v1/sessions` and `PATCH /api/v1/sessions/{id}/status`.
- Preserves: existing session detail and all pipeline operation routes.

- [ ] **Step 1: Write failing API tests for management create/list/get**

Create a `TestClient(create_app(tmp_path / "api.db"))`, register PC01 and PC02 via
the real agent API, and exercise:

```python
created = client.post(
    "/api/v1/sessions",
    json={"name": "PBL4 Final", "room": "A101", "agent_ids": ["PC01", "PC02"]},
)
assert created.status_code == 201
assert created.json()["name"] == "PBL4 Final"
assert created.json()["status"] == "CREATED"
assert created.json()["agent_count"] == 2

listed = client.get("/api/v1/sessions")
assert listed.status_code == 200
assert [item["id"] for item in listed.json()] == [created.json()["id"]]

detail = client.get(f"/api/v1/sessions/{created.json()['id']}")
assert [item["id"] for item in detail.json()["agents"]] == ["PC01", "PC02"]
```

Use helper registration payloads with distinct hostnames and IPs so enrichment
assertions prove data comes from Agent records.

- [ ] **Step 2: Run API tests and confirm RED**

```powershell
uv run pytest apps/api/test/integration/test_session_management_api.py -q
```

Expected: management POST returns 422 and list route returns 405/404.

- [ ] **Step 3: Add DI fields and exact HTTP schemas**

Add use-case fields to `Container` and providers/Annotated aliases in `deps.py`.
Define separate extra-forbid request models:

```python
class CreateManagementSessionRequest(ApiModel):
    name: str = Field(min_length=1)
    room: str = Field(min_length=1)
    agent_ids: list[str] = Field(min_length=1)
    actor: str = Field(default="teacher", min_length=1)


class CreatePipelineSessionRequest(ApiModel):
    exam_name: str = Field(min_length=1)
    room_id: str = Field(min_length=1)
    gateway_id: str = Field(min_length=1)
    workstation_ids: list[str] = Field(min_length=1)
    actor: str = Field(default="teacher", min_length=1)


class UpdateSessionStatusRequest(ApiModel):
    status: SessionState
    actor: str = Field(default="teacher", min_length=1)
```

Define nullable `AssignedAgentView` and an enriched `SessionDetailView` that
extends the existing legacy `SessionView` with `name`, `room`, `status`,
`updated_at`, `agent_count`, and `agents`.

- [ ] **Step 4: Route both create schemas without ambiguity**

Type the body as:

```python
CreateManagementSessionRequest | CreatePipelineSessionRequest
```

Use `isinstance` to dispatch. Pipeline input goes to the existing
`ExamPipelineService.create_session`; management input goes to
`CreateExamSession`. Convert either result to the combined detail response via
`GetExamSession` so one response shape is returned.

Add list and patch routes before the parameterized detail route where helpful
for readability. Keep `GET /sessions/{session_id}` but switch it to enriched
details.

- [ ] **Step 5: Run management API tests and make create/list/get GREEN**

Run the management API test file. Expected: create/list/get tests pass.

- [ ] **Step 6: Add failing API tests for status and errors**

Test these literal contracts:

- `PATCH CREATED -> READY` returns 200 and `status="READY"`.
- Skipping to RUNNING returns 409 with `code="INVALID_STATE"`.
- An Agent made stale before READY returns 409 with `code="READINESS_GATE"` and
  includes its ID.
- Unknown selected Agent returns 404 with `code="NOT_FOUND"`.
- OFFLINE selected Agent returns 409.
- A body mixing `name` with `exam_name` returns 422.

- [ ] **Step 7: Implement patch/error response wiring and verify GREEN**

Map `UpdateSessionStatusRequest` to `UpdateExamSessionStatusInput`. Reuse current
exception handlers; do not add duplicate HTTP exception logic in the route.

Run:

```powershell
uv run pytest apps/api/test/integration/test_session_management_api.py -q
```

Expected: all management API tests pass.

- [ ] **Step 8: Verify legacy API compatibility**

```powershell
uv run pytest apps/api/test/integration/test_pipeline_api.py apps/api/test/integration/test_agents_api.py -q
```

Expected: all existing tests pass, including legacy POST fields and full
pipeline completion.

- [ ] **Step 9: Commit API changes**

```powershell
git add apps/api/app/infrastructure/di/container.py apps/api/app/presentation/api/deps.py apps/api/app/presentation/schemas/exam_pipeline.py apps/api/app/presentation/api/routers/exam_sessions.py apps/api/test/integration/test_session_management_api.py
git commit -m "feat: expose exam session management API"
```

---

### Task 5: Frontend Session Data, Mutations, and Server Actions

**Files:**
- Modify: `apps/web/lib/api-client.ts`
- Modify: `apps/web/features/exam-sessions/types.ts`
- Modify: `apps/web/features/exam-sessions/queries.ts`
- Create: `apps/web/features/exam-sessions/mutations.ts`
- Create: `apps/web/app/sessions/actions.ts`

**Interfaces:**
- Produces: `ApiError` carrying `status`, `code`, and `detail`.
- Produces: `getSessions()`, `getAvailableAgents()`, `createSession()`, and `updateSessionStatus()`.
- Produces: Server Actions `createSessionAction` and `transitionSessionAction`.

- [ ] **Step 1: Define frontend session types and strict API boundary**

Add exact unions and response shapes:

```typescript
export type SessionStatus =
  | "CREATED"
  | "DEPLOYING"
  | "PREFLIGHT"
  | "READY"
  | "DEGRADED"
  | "RUNNING"
  | "RESTORING"
  | "NORMAL"
  | "FINISHED";

export type AssignedAgent = {
  id: string;
  hostname: string | null;
  ip_address: string | null;
  status: "ONLINE" | "OFFLINE" | null;
  last_seen: string | null;
  assigned_at: string | null;
};

export type ExamSession = {
  id: string;
  name: string;
  room: string;
  status: SessionStatus;
  gateway_id: string | null;
  created_at: string;
  updated_at: string;
  agent_count: number;
  agents: AssignedAgent[];
};

export type CreateSessionPayload = {
  name: string;
  room: string;
  agent_ids: string[];
};
```

- [ ] **Step 2: Extend api-client for JSON mutations and structured failures**

Change `fetchApi<T>` to accept `RequestInit`, merge the `Accept` header, and
throw:

```typescript
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    public readonly detail: string,
  ) {
    super(detail);
  }
}
```

On non-2xx, parse `{code, detail}` when possible and fall back to
`EECP API returned <status> for <path>`.

- [ ] **Step 3: Implement queries and mutations**

Keep query error behavior consistent with workstation queries:

```typescript
export async function getSessions(): Promise<ExamSession[] | null>
export async function getAvailableAgents(): Promise<Agent[] | null>
```

In `mutations.ts`, call:

```typescript
export function createSession(payload: CreateSessionPayload): Promise<ExamSession>
export function updateSessionStatus(
  sessionId: string,
  status: "READY" | "RUNNING" | "FINISHED",
): Promise<ExamSession>
```

Use JSON content type and POST/PATCH exactly as the FastAPI contract specifies.

- [ ] **Step 4: Implement Server Actions with validation and redirect**

In `actions.ts`, add `"use server"` and define:

```typescript
export type CreateSessionActionState = { error: string | null };

export async function createSessionAction(
  _previous: CreateSessionActionState,
  formData: FormData,
): Promise<CreateSessionActionState>

export async function transitionSessionAction(
  sessionId: string,
  target: "READY" | "RUNNING" | "FINISHED",
): Promise<void>
```

Trim `name` and `room`, read all `agent_ids` using `formData.getAll`, return a
Vietnamese validation message for missing fields/selection, convert `ApiError`
to its detail, and let unexpected errors return a generic connection message.
On success call `revalidatePath("/sessions")`; creation then calls
`redirect("/sessions")`.

- [ ] **Step 5: Run TypeScript RED/GREEN loop**

Run after each file group:

```powershell
cd apps/web
npm run typecheck
```

Expected first run after types but before implementation: failures for missing
exports. Expected final run: exit 0 with no TypeScript diagnostics.

- [ ] **Step 6: Commit frontend data/action layer**

```powershell
cd D:\EECP
git add apps/web/lib/api-client.ts apps/web/features/exam-sessions/types.ts apps/web/features/exam-sessions/queries.ts apps/web/features/exam-sessions/mutations.ts apps/web/app/sessions/actions.ts
git commit -m "feat: add exam session frontend data actions"
```

---

### Task 6: Session List and Creation Pages

**Files:**
- Create: `apps/web/features/exam-sessions/components/session-list.tsx`
- Create: `apps/web/features/exam-sessions/components/create-session-form.tsx`
- Modify: `apps/web/features/exam-sessions/index.ts`
- Create: `apps/web/app/sessions/page.tsx`
- Create: `apps/web/app/sessions/create/page.tsx`
- Modify: `apps/web/app/globals.css`

**Interfaces:**
- Consumes: types, queries, and Server Actions from Task 5.
- Produces: `/sessions` dynamic dashboard and `/sessions/create` form.

- [ ] **Step 1: Build the session list component against real response types**

Create an async server component that calls `getSessions()`, renders API
unavailable/empty states, includes the existing `AutoRefresh`, and renders one
article per session. Derive the next action exactly:

```typescript
const nextStatus = {
  CREATED: ["READY", "Mark Ready"],
  READY: ["RUNNING", "Start Exam"],
  RUNNING: ["FINISHED", "Finish Exam"],
} as const;
```

Only render this action when `session.gateway_id === null`. Bind
`transitionSessionAction` with the session ID and target. Render every assigned
Agent with two pills/labels: current Agent status and current session status.

- [ ] **Step 2: Build the accessible client creation form**

Use `useActionState(createSessionAction, {error: null})`. Render labeled text
inputs and checkbox rows. For each Agent:

```tsx
<input
  type="checkbox"
  name="agent_ids"
  value={agent.id}
  disabled={agent.status !== "ONLINE"}
/>
```

Show hostname, IP, and status. Keep OFFLINE agents visible. Use an `aria-live`
error region and disable the submit button while pending with `useFormStatus` in
a focused child component.

- [ ] **Step 3: Compose small App Router pages**

`/sessions/page.tsx` exports `dynamic = "force-dynamic"`, a page header, a link
to `/sessions/create`, and `SessionList`.

`/sessions/create/page.tsx` loads `getAvailableAgents()`, renders a back link,
API unavailable state, and `CreateSessionForm` with an empty array only when the
API successfully returns no Agents.

Export both feature components from `features/exam-sessions/index.ts` without
removing the existing `PipelineOverview` export.

- [ ] **Step 4: Add scoped responsive CSS**

Add classes prefixed `sessions-`, `session-`, and `session-form-`. Reuse existing
CSS variables, border radius, card surface, status pill, and breakpoints. Ensure:

- two-column cards above 900px and one column below;
- form controls have visible labels and focus outlines;
- disabled Agent rows are visibly muted but readable;
- action buttons have hover, focus, and disabled states;
- no horizontal overflow at 360px width.

- [ ] **Step 5: Run frontend verification**

Run sequentially so Next-generated types do not race:

```powershell
cd apps/web
npm run typecheck
npm run build
```

Expected: both exit 0; build output includes `/sessions` and `/sessions/create`.

- [ ] **Step 6: Commit UI pages**

```powershell
cd D:\EECP
git add apps/web/features/exam-sessions/components/session-list.tsx apps/web/features/exam-sessions/components/create-session-form.tsx apps/web/features/exam-sessions/index.ts apps/web/app/sessions/page.tsx apps/web/app/sessions/create/page.tsx apps/web/app/globals.css
git commit -m "feat: add exam session management pages"
```

---

### Task 7: Runbook, Full Regression, and Demo Verification

**Files:**
- Modify: `README.md`
- Verify: all files changed in Tasks 1-6

**Interfaces:**
- Consumes: complete backend and frontend feature.
- Produces: repeatable LAN demo instructions and final verification evidence.

- [ ] **Step 1: Add Phase 2 runbook and API examples**

Document:

- database creation of `session_workstations` on server restart;
- management POST, list, detail, and PATCH examples;
- required Agent startup with distinct PC01/PC02 IDs;
- frontend URL `http://192.168.3.50:3000/sessions/create`;
- demo sequence CREATED -> READY -> RUNNING -> FINISHED;
- behavior when an Agent is OFFLINE at creation or READY transition;
- statement that legacy pipeline endpoints remain available.

Use valid PowerShell commands without Markdown-link text inside environment
variable values.

- [ ] **Step 2: Run all backend tests**

```powershell
cd D:\EECP
uv run pytest
```

Expected: zero failures, including original pipeline and Phase 1 Agent tests.

- [ ] **Step 3: Run backend lint**

```powershell
uv run ruff check apps/api agent
```

Expected: `All checks passed!`

- [ ] **Step 4: Run frontend checks sequentially**

```powershell
cd D:\EECP\apps\web
npm run typecheck
npm run build
```

Expected: both exit 0 and both session routes appear in build output.

- [ ] **Step 5: Inspect OpenAPI and perform an HTTP smoke flow**

Use `TestClient(create_app(temp_db))` or a one-off `uv run python -c` command to
assert OpenAPI contains:

```text
/api/v1/sessions
/api/v1/sessions/{session_id}
/api/v1/sessions/{session_id}/status
```

Register PC01 and PC02, create a management session, GET it, and PATCH READY,
RUNNING, FINISHED. Assert literal 2xx status codes and final `FINISHED`.

- [ ] **Step 6: Check repository integrity and review the complete diff**

```powershell
cd D:\EECP
git diff --check
git status --short --branch
git diff --stat 5497b97..HEAD
```

Confirm no runtime database, `.next`, generated Agent instruction files, or
unrelated user files are staged.

- [ ] **Step 7: Commit runbook changes**

```powershell
git add README.md
git commit -m "docs: add exam session management demo runbook"
```

- [ ] **Step 8: Record final handoff information**

Report changed files grouped by domain/application/infrastructure/API/frontend,
the new table and constraints, API request examples, server/agent/frontend run
commands, test counts, build/typecheck/lint evidence, and the LAN demo sequence.
Do not push or merge unless the user explicitly requests it.
