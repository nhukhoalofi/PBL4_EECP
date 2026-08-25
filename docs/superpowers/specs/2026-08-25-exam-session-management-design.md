# Phase 2 Exam Session Management Design

Date: 2026-08-25
Status: Approved design, pending implementation plan

## Context

PBL4_EECP already contains an advanced `ExamSession` aggregate and API for the
policy pipeline:

```text
CREATED -> DEPLOYING -> PREFLIGHT -> READY -> RUNNING -> RESTORING -> NORMAL
```

Phase 2 adds teacher-facing session management with a smaller lifecycle:

```text
CREATED -> READY -> RUNNING -> FINISHED
```

The implementation must not create a second session model, replace the existing
pipeline, or break its API and tests. It will extend the existing aggregate and
use `gateway_id` to distinguish the two supported modes:

- A pipeline session has a gateway and continues to use deploy, preflight,
  start, finish, restore, telemetry, and summary endpoints.
- A management session has no gateway and uses the Phase 2 status endpoint.

The two modes share one `ExamSession` entity and one `exam_sessions` store, but
their lifecycle commands cannot be mixed.

## Goals

- Let a teacher create a management session from registered ONLINE agents.
- Persist explicit session-to-agent assignments without copying Agent data.
- List sessions and retrieve details enriched with current Agent liveness.
- Support `CREATED -> READY -> RUNNING -> FINISHED` with strict validation.
- Provide `/sessions` and `/sessions/create` pages using the existing Next.js
  feature-first structure.
- Preserve all existing policy-pipeline behavior and endpoints.

## Non-goals

- Editing session membership after creation.
- Deleting sessions.
- Adding authentication or teacher accounts.
- Deploying policy from a gateway-less management session.
- Replacing the advanced pipeline with the simplified lifecycle.
- Adding a frontend test framework solely for this phase.

## Domain Design

### Existing ExamSession aggregate

The existing `ExamSession` remains the only session aggregate. Its internal
names (`exam_name`, `room_id`, `state`) remain unchanged for compatibility.
Phase 2 DTOs and HTTP schemas expose these values as `name`, `room`, and
`status`.

The aggregate gains:

- `gateway_id: str | None`; legacy creation still requires a non-empty gateway.
- `updated_at: datetime`, initialized to `created_at`.
- `SessionState.FINISHED`.
- A `create_managed(name, room, agent_ids, at)` factory that creates a
  gateway-less session in `CREATED`.
- A management transition method supporting only:
  - `CREATED -> READY`
  - `READY -> RUNNING`
  - `RUNNING -> FINISHED`
- A management-mode guard requiring `gateway_id is None`.
- A pipeline-mode guard in `deploy_policy()` requiring a gateway.

The existing `create()` factory and advanced pipeline methods remain. Existing
`finish()` continues to move a pipeline session from `RUNNING` to `RESTORING`;
it does not produce `FINISHED`. The new management transition method produces
`FINISHED` and does not create restore commands.

All state-changing methods update `updated_at`. Deserialization of older JSON
payloads uses `created_at` when `updated_at` is absent, so existing SQLite data
remains readable.

### SessionWorkstation association

A new slotted dataclass represents assignment metadata:

```text
SessionWorkstation
- id
- session_id
- agent_id
- assigned_at
```

It stores only identifiers and assignment time. Hostname, IP address, heartbeat,
version, and ONLINE/OFFLINE status remain exclusively in the `Agent` entity and
`agents` table.

The existing `WorkstationSession` value inside the aggregate remains because it
stores pipeline-specific state such as policy hashes, preflight checks, and
restore acknowledgement. It is not a duplicate of Agent information.

Phase 2 does not support editing membership after creation, so the aggregate's
workstation keys and `session_workstations` rows are created together and cannot
diverge through a supported command.

## Persistence Design

The existing JSON-backed `exam_sessions` table remains unchanged. A new table is
created idempotently during database initialization:

```sql
CREATE TABLE IF NOT EXISTS session_workstations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    UNIQUE(session_id, agent_id),
    FOREIGN KEY(session_id) REFERENCES exam_sessions(id),
    FOREIGN KEY(agent_id) REFERENCES agents(id)
);

CREATE INDEX IF NOT EXISTS ix_session_workstations_session
    ON session_workstations(session_id, assigned_at, id);
```

No Agent columns are duplicated. Existing pipeline-only sessions are not
backfilled because historical workstation IDs may not exist in `agents`; their
membership continues to be read from the aggregate payload. New management
sessions always receive association rows.

Repository contracts are extended as follows:

- `SessionRepository.list_all() -> list[ExamSession]`
- `SessionWorkstationRepository.assign(association)`
- `SessionWorkstationRepository.assign_many(associations)`
- `SessionWorkstationRepository.list_for_session(session_id)`

`UnitOfWork` exposes `session_workstations`. Session creation, assignments, audit
entry, and any liveness refreshes commit or roll back as one SQLite transaction.

## Application Design

Management use cases live beside the current pipeline service rather than being
added to its already broad orchestration class.

### CreateExamSession

Input:

```text
name
room
agent_ids
actor = "teacher"
```

Behavior:

1. Trim name, room, and agent IDs; reject empty or duplicate IDs.
2. Load each Agent in the Unit of Work.
3. Refresh liveness using one injected clock value and persist any OFFLINE
   transition.
4. Return 404 when a selected Agent is not registered.
5. Return 409 with the affected IDs when any selected Agent is OFFLINE.
6. Create a gateway-less `ExamSession` in `CREATED`.
7. Add one `SessionWorkstation` per selected Agent.
8. Append `SESSION_CREATED` audit data and commit once.

### GetExamSession

Loads the aggregate and produces a management detail DTO. For management
sessions, assigned IDs come from `session_workstations`. For legacy pipeline
sessions, it falls back to aggregate workstation keys. Registered agents are
refreshed for liveness and included with current hostname, IP address, status,
last seen, and assignment time where available.

### ListExamSessions

Returns all sessions ordered newest first, with name, room, status, timestamps,
agent count, and enriched assigned agents. This supports both management and
legacy pipeline sessions.

### UpdateExamSessionStatus

Input contains `session_id`, requested status, and actor.

- It rejects pipeline-mode sessions; they must use existing pipeline commands.
- For `CREATED -> READY`, it refreshes every assigned Agent and returns 409 with
  OFFLINE IDs if any are unavailable.
- `READY -> RUNNING` and `RUNNING -> FINISHED` do not recheck liveness, avoiding
  a session becoming impossible to finish after a workstation disconnects.
- It delegates transition validity to the aggregate, saves the session, appends
  an audit event, and commits once.

## API Design

The existing router remains at `/api/v1`; no duplicate router is introduced.

### Create

`POST /api/v1/sessions`

The request schema accepts both forms.

Management form:

```json
{
  "name": "PBL4 Operating System Final",
  "room": "A101",
  "agent_ids": ["PC01", "PC02"]
}
```

Legacy pipeline form:

```json
{
  "exam_name": "PBL4 Operating System Final",
  "room_id": "A101",
  "gateway_id": "gw-a101",
  "workstation_ids": ["PC01", "PC02"],
  "actor": "teacher-01"
}
```

Presence of a non-empty `gateway_id` selects the existing pipeline creation
path. Its historical behavior is preserved, including allowing workstation IDs
that have not yet registered. A gateway-less request selects the management use
case and requires registered ONLINE agents.

The schema rejects mixed/conflicting new and legacy field names.

### Read and transition

- `GET /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`
- `PATCH /api/v1/sessions/{session_id}/status`

Patch body:

```json
{"status": "READY", "actor": "teacher"}
```

The enriched response includes Phase 2 fields:

```text
id, name, room, status, created_at, updated_at, agent_count, agents
```

It also retains the legacy session fields required by current pipeline clients,
including `exam_name`, `room_id`, `gateway_id`, `state`, policy, workstations,
pipeline timestamps, and aggregate version.

Error mapping:

- 404: session or selected Agent does not exist.
- 409: selected/assigned Agent is OFFLINE, invalid lifecycle transition, or a
  management operation is attempted on a pipeline session.
- 422: malformed body, empty values, duplicates, or conflicting aliases.

Existing deploy, command acknowledgement, preflight, start, telemetry, finish,
restore, and summary routes retain their current contracts.

## Frontend Design

The repository uses `apps/web/app` and `apps/web/features`; no new `src`
directory is introduced.

### `/sessions`

A dynamic server-rendered page loads the enriched session list. Each card shows:

- exam name, room, session status, and machine count;
- every assigned machine's ID and current Agent ONLINE/OFFLINE status;
- the session status beside each assignment, enabling the demo display
  `PC01 ONLINE READY` and `PC02 ONLINE READY`;
- the one valid next action for a management session: Mark Ready, Start Exam, or
  Finish Exam.

The page refreshes periodically so heartbeat changes are visible. Pipeline-mode
sessions remain visible but do not show simplified lifecycle controls.

### `/sessions/create`

The page fetches `GET /api/v1/agents` on the Next.js server and renders a form
with exam name, room, and workstation checkboxes. ONLINE agents are selectable;
OFFLINE agents remain visible but disabled. At least one selection is required.

Creation and transition mutations use Next.js Server Actions. Requests therefore
flow from the Next.js server to FastAPI using `EECP_API_URL`, avoiding browser
CORS configuration in the LAN demo. Server validation errors are rendered near
the form or action and successful creation redirects to `/sessions`.

The feature remains under `features/exam-sessions` with separate types, queries,
mutations/actions, and presentational components. App route files compose these
feature modules and remain small.

## Testing Strategy

Implementation follows test-driven development.

Domain tests cover:

- managed creation and optional gateway compatibility;
- each valid management transition;
- invalid/skipped/reversed transitions;
- refusal to mix management and pipeline commands;
- legacy payload deserialization without `updated_at`.

Repository tests cover:

- assignment persistence and ordering;
- uniqueness of `(session_id, agent_id)`;
- session `list_all()`;
- transaction rollback behavior where relevant.

Application/API tests cover:

- creating a session with ONLINE agents;
- rejecting OFFLINE and unknown agents;
- association creation;
- listing and getting enriched details;
- current liveness in the response;
- rechecking ONLINE status for `CREATED -> READY`;
- valid and invalid status patches;
- compatibility of legacy create payload and all existing pipeline tests.

Frontend verification consists of production build and TypeScript checking. The
project has no frontend test runner, and this phase will not add one solely for
the create form.

Final verification commands:

```powershell
uv run pytest
uv run ruff check apps/api agent

cd apps/web
npm run typecheck
npm run build
```

## LAN Demo Scenario

1. Start FastAPI and Next.js on the Control Server.
2. Start PC01 and PC02 agents with distinct required `EECP_AGENT_ID` values.
3. Open `/sessions/create`; verify both ONLINE machines are selectable and any
   OFFLINE machine is disabled.
4. Create `PBL4 Final Exam` in room `A101` with PC01 and PC02.
5. Open `/sessions`; verify status `CREATED` and two assigned machines.
6. Mark the session READY; the server rechecks both agents.
7. Verify the dashboard shows `PC01 ONLINE READY` and `PC02 ONLINE READY`.
8. Start the exam, then finish it, demonstrating the valid simplified lifecycle.
9. Confirm existing policy-pipeline demo endpoints and tests still work.
