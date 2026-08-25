# Agent Registration and Heartbeat Design

## Goal

Implement Phase 1 workstation discovery and liveness monitoring for the EECP LAN demo without changing the existing Clean Architecture boundaries or exam-session pipeline.

The control server at `192.168.3.50` must accept registrations and heartbeats from workstation agents. The dashboard must show PC01 (`192.168.3.56`) and PC02 (`192.168.3.55`) as `ONLINE` while their agents are running and as `OFFLINE` after their last heartbeat is more than 15 seconds old.

## Scope

This phase adds:

- An Agent domain entity and ONLINE/OFFLINE status.
- Agent persistence through the existing SQLite Unit of Work.
- Registration, heartbeat, and listing application use cases.
- Three FastAPI endpoints under `/api/v1/agents`.
- A standalone Python workstation agent in the repository-root `agent/` directory.
- A Next.js `/workstations` monitoring page that refreshes every 5 seconds.
- Unit and integration coverage for registration, heartbeat, listing, and offline detection.

This phase does not add authentication, agent command execution, a background scheduler, process/service installation, TLS, or changes to the existing exam-session state machine.

## Architecture

The backend keeps the existing dependency direction:

```text
presentation -> application -> domain
infrastructure ----------------> domain
```

The Agent entity and repository protocol belong to the domain. Application use cases coordinate entity behavior and persistence. SQLite implements the repository through the existing Unit of Work. FastAPI schemas and routes only translate HTTP input and output. The workstation agent remains a separate executable application and does not import FastAPI backend internals.

The frontend follows the current rule:

```text
app -> features -> components/lib
```

## Domain Model

`AgentStatus` is a string enum with these exact values:

- `ONLINE`
- `OFFLINE`

`Agent` is a slotted dataclass with:

- `id: str`
- `hostname: str`
- `ip_address: str`
- `status: AgentStatus`
- `agent_version: str`
- `last_seen: datetime`
- `created_at: datetime`

The entity owns liveness behavior:

- Registration creates an ONLINE agent whose `last_seen` and `created_at` use the same current UTC timestamp.
- Re-registration refreshes hostname, IP address, version, status, and `last_seen` while preserving `created_at`.
- A heartbeat sets `last_seen` to the current UTC timestamp and status to ONLINE.
- Liveness refresh sets status to OFFLINE only when `now - last_seen > 15 seconds`. Exactly 15 seconds remains ONLINE.
- IDs, hostnames, IP addresses, and versions are trimmed and must not be empty.

All persisted and returned datetimes are timezone-aware UTC values serialized as ISO 8601.

## Persistence and Unit of Work

The domain `AgentRepository` protocol provides:

```python
def add(self, agent: Agent) -> None: ...
def get(self, agent_id: str) -> Agent: ...
def find(self, agent_id: str) -> Agent | None: ...
def save(self, agent: Agent) -> None: ...
def list_all(self) -> list[Agent]: ...
```

`UnitOfWork` gains an `agents` repository alongside the existing repositories. `SqliteUnitOfWork` creates `SqliteAgentRepository` from the same connection, so each use case remains transactional.

SQLite gains an `agents` table with explicit columns matching the entity. `id` is the primary key. `list_all` orders agents by ID for deterministic API and dashboard output.

No migration framework is introduced in Phase 1. The existing idempotent `CREATE TABLE IF NOT EXISTS` initialization adds the table to new and existing demo databases.

## Application Use Cases

The application layer exposes three focused use cases, sharing a Unit of Work factory and an injectable UTC clock:

### RegisterAgent

Input fields are `agent_id`, `hostname`, `ip_address`, and `agent_version`.

Registration is idempotent by agent ID:

- If the ID is new, create and persist an Agent.
- If the ID exists, update the mutable registration fields, set it ONLINE, refresh `last_seen`, and preserve `created_at`.

The output is the resulting Agent.

### HeartbeatAgent

Input is `agent_id`. The use case loads the Agent, applies a heartbeat at the injected current time, saves it, and returns it. An unknown ID raises the existing domain not-found error and maps to HTTP 404 through the current exception handler.

### ListAgents

The use case loads all agents, evaluates each against the 15-second timeout at one shared current time, persists any status transitions, commits once, and returns the ordered list.

Offline detection is intentionally request-driven for Phase 1. The dashboard polls the list endpoint, so no background worker is required for the demo.

## HTTP API

A new router file at `apps/api/app/presentation/api/routers/agents.py` uses prefix `/api/v1/agents` and tag `agents`.

### Register

```http
POST /api/v1/agents/register
Content-Type: application/json

{
  "id": "PC01",
  "hostname": "DESKTOP-A",
  "ip_address": "192.168.3.56",
  "agent_version": "1.0.0"
}
```

The response is the complete Agent view. New registration returns HTTP 201; idempotent re-registration also returns HTTP 201 because the endpoint represents successful agent registration, not a generic update API.

### Heartbeat

```http
POST /api/v1/agents/PC01/heartbeat
```

The response is the updated Agent view with HTTP 200. An unknown agent returns HTTP 404.

### List

```http
GET /api/v1/agents
```

The response is an ID-ordered JSON array of complete Agent views after offline evaluation.

The new router is registered beside the existing exam-session router. The existing `/api/v1/agents/{target_id}/commands` endpoint remains unchanged and does not conflict with the static `/register`, collection GET, or `/heartbeat` routes.

## Standalone Workstation Agent

The root-level `agent/` directory contains:

- `config.py`: configuration constants with environment-variable overrides.
- `heartbeat.py`: workstation identity discovery and HTTP registration/heartbeat operations.
- `main.py`: startup registration and the five-second heartbeat loop.

Defaults are:

```text
SERVER_URL=http://192.168.3.50:8000
AGENT_ID=PC01
AGENT_VERSION=1.0.0
HEARTBEAT_INTERVAL_SECONDS=5
```

Environment variables `EECP_SERVER_URL`, `EECP_AGENT_ID`, and `EECP_AGENT_VERSION` override those defaults. This allows PC02 to run with `EECP_AGENT_ID=PC02` without editing source code.

Hostname comes from `socket.gethostname()`. Local IPv4 is discovered using a UDP socket connected toward the control server; this determines the interface without sending application data. If discovery fails, the agent falls back to hostname resolution.

The agent uses Python's standard HTTP library, so workstation setup needs no third-party package. Requests have a finite timeout. Startup retries registration after transient network failures, and heartbeat failures are logged without terminating the process. A failed heartbeat causes the next loop iteration to register again before resuming normal heartbeats, allowing recovery after a server restart or database reset. Ctrl+C exits cleanly.

## Frontend

The frontend adds a `workstations` feature containing API types, a query, and presentation components. The App Router exposes `/workstations` and keeps the existing home page intact.

The initial and refreshed workstation data is fetched on the Next.js server through the existing `fetchApi` helper and `EECP_API_URL`. A small client component calls `router.refresh()` every five seconds. This avoids browser-to-FastAPI CORS requirements and keeps the current server-side API configuration convention.

Each workstation card displays:

- Agent ID and hostname.
- IP address.
- ONLINE/OFFLINE status using the shared StatusPill component.
- Last heartbeat formatted for readability.

An empty list displays a clear no-workstations message. API failure displays an unavailable state rather than crashing the page. With five-second polling and a strict greater-than-15-second timeout, an agent normally appears OFFLINE between 15 and 20 seconds after its final heartbeat.

## Error Handling

- Invalid or empty registration fields are rejected through domain validation and mapped consistently by the presentation layer.
- Heartbeat for an unknown ID returns 404.
- SQLite operations remain transactional through Unit of Work commit/rollback.
- Agent network failures are logged and retried; they never fabricate a successful heartbeat.
- The dashboard distinguishes an empty successful response from an API failure.

## Testing Strategy

Implementation follows red-green-refactor TDD.

Backend unit tests cover:

- Agent creation normalization and ONLINE defaults.
- Re-registration preserving `created_at`.
- Heartbeat updating `last_seen` and restoring ONLINE.
- Offline transition only after more than 15 seconds.
- List ordering and persistence of offline transitions.

Backend integration tests cover:

- POST registration response and SQLite persistence.
- Idempotent registration update behavior.
- POST heartbeat update and unknown-agent 404.
- GET list response with ONLINE and OFFLINE agents using an injected clock where practical.

Workstation-agent tests cover payload construction, identity collection fallback, registration/heartbeat request paths, and retry control without real network calls.

Final verification runs:

```powershell
uv run ruff check apps/api agent
uv run pytest
cd apps/web
npm run typecheck
npm run build
```

## Acceptance Criteria

- PC01 and PC02 can register with the control server over the LAN.
- Both appear ONLINE on `/workstations` while sending five-second heartbeats.
- Stopping either agent makes it appear OFFLINE within the next dashboard refresh after the 15-second threshold.
- Restarting an agent re-registers the same ID without duplicate-key failure and preserves its original creation time.
- Existing exam pipeline routes and tests continue to pass.
- No standalone script is added inside the FastAPI backend for workstation behavior.
