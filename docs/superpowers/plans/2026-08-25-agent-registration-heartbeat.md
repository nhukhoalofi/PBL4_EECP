# Agent Registration and Heartbeat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent LAN workstation registration, five-second heartbeats, 15-second offline detection, a standalone workstation client, and a live Next.js monitoring page.

**Architecture:** Extend the current Unit of Work vertical slice with an Agent aggregate and three callable application use cases. Keep the workstation process independent and dependency-free, and have the Next.js server fetch FastAPI data while a client refresh component triggers five-second updates.

**Tech Stack:** Python 3.12, dataclasses, FastAPI, Pydantic, sqlite3, pytest, Next.js 16, React 19, TypeScript 5.9.

**Spec:** `docs/superpowers/specs/2026-08-25-agent-registration-heartbeat-design.md`

## Global Constraints

- Preserve `presentation -> application -> domain` and `infrastructure -> domain`; domain must not import FastAPI, Pydantic, or SQLite.
- Keep the existing exam-session API and state machine unchanged.
- Put the independent workstation process under root `agent/`, never under `apps/api/scripts`.
- Use UTC-aware datetimes and the exact status strings `ONLINE` and `OFFLINE`.
- Registration is an ID-based upsert that preserves `created_at`.
- An agent becomes OFFLINE only when `now - last_seen > 15 seconds`.
- The workstation heartbeat interval and dashboard refresh interval are both 5 seconds.
- Do not add a background scheduler, migration framework, authentication, TLS, or third-party workstation dependency.

---

### Task 1: Agent Domain Entity

**Files:**
- Create: `apps/api/app/domain/entities/agent.py`
- Modify: `apps/api/app/domain/value_objects/enums.py`
- Create: `apps/api/test/unit/test_agent_domain.py`

**Interfaces:**
- Consumes: `utc_now()` and `PolicyValidationError` from the existing domain.
- Produces: `AgentStatus`; `Agent.register(...)`; `Agent.reregister(...)`; `Agent.heartbeat(...)`; `Agent.refresh_liveness(...) -> bool`.

- [ ] **Step 1: Write failing domain tests**

```python
from datetime import UTC, datetime, timedelta

from app.domain.entities.agent import Agent
from app.domain.value_objects.enums import AgentStatus


NOW = datetime(2026, 8, 25, 9, 0, tzinfo=UTC)


def test_register_agent_normalizes_fields_and_starts_online() -> None:
    agent = Agent.register(" PC01 ", " DESKTOP-A ", " 192.168.3.56 ", " 1.0.0 ", NOW)
    assert agent.id == "PC01"
    assert agent.hostname == "DESKTOP-A"
    assert agent.ip_address == "192.168.3.56"
    assert agent.agent_version == "1.0.0"
    assert agent.status == AgentStatus.ONLINE
    assert agent.last_seen == NOW
    assert agent.created_at == NOW


def test_reregister_preserves_created_at_and_refreshes_mutable_fields() -> None:
    agent = Agent.register("PC01", "OLD", "192.168.3.10", "0.9.0", NOW)
    later = NOW + timedelta(minutes=1)
    agent.reregister("NEW", "192.168.3.56", "1.0.0", later)
    assert agent.created_at == NOW
    assert (agent.hostname, agent.ip_address, agent.agent_version) == (
        "NEW", "192.168.3.56", "1.0.0"
    )
    assert agent.status == AgentStatus.ONLINE
    assert agent.last_seen == later


def test_agent_is_offline_only_after_strict_fifteen_second_timeout() -> None:
    agent = Agent.register("PC01", "DESKTOP-A", "192.168.3.56", "1.0.0", NOW)
    assert agent.refresh_liveness(NOW + timedelta(seconds=15)) is False
    assert agent.status == AgentStatus.ONLINE
    assert agent.refresh_liveness(NOW + timedelta(seconds=16)) is True
    assert agent.status == AgentStatus.OFFLINE
    agent.heartbeat(NOW + timedelta(seconds=17))
    assert agent.status == AgentStatus.ONLINE
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest apps/api/test/unit/test_agent_domain.py -v`

Expected: collection fails because `app.domain.entities.agent` does not exist.

- [ ] **Step 3: Implement the enum and entity**

```python
class AgentStatus(StrEnum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
```

```python
@dataclass(slots=True)
class Agent:
    id: str
    hostname: str
    ip_address: str
    status: AgentStatus
    agent_version: str
    last_seen: datetime
    created_at: datetime

    @classmethod
    def register(
        cls, agent_id: str, hostname: str, ip_address: str,
        agent_version: str, at: datetime,
    ) -> Agent:
        values = [_required(value, name) for value, name in (
            (agent_id, "agent id"), (hostname, "hostname"),
            (ip_address, "ip address"), (agent_version, "agent version"),
        )]
        return cls(values[0], values[1], values[2], AgentStatus.ONLINE, values[3], at, at)

    def reregister(self, hostname: str, ip_address: str, agent_version: str, at: datetime) -> None:
        self.hostname = _required(hostname, "hostname")
        self.ip_address = _required(ip_address, "ip address")
        self.agent_version = _required(agent_version, "agent version")
        self.heartbeat(at)

    def heartbeat(self, at: datetime) -> None:
        self.last_seen = at
        self.status = AgentStatus.ONLINE

    def refresh_liveness(self, at: datetime) -> bool:
        next_status = (
            AgentStatus.OFFLINE
            if at - self.last_seen > timedelta(seconds=15)
            else AgentStatus.ONLINE
        )
        changed = next_status != self.status
        self.status = next_status
        return changed
```

The `_required` helper strips strings and raises `PolicyValidationError(f"{name} must not be empty")` for an empty value.

- [ ] **Step 4: Verify GREEN and lint**

Run: `uv run pytest apps/api/test/unit/test_agent_domain.py -v`

Expected: 3 tests pass.

Run: `uv run ruff check apps/api/app/domain apps/api/test/unit/test_agent_domain.py`

Expected: exit 0.

- [ ] **Step 5: Commit**

```powershell
git add apps/api/app/domain/entities/agent.py apps/api/app/domain/value_objects/enums.py apps/api/test/unit/test_agent_domain.py
git commit -m "feat: add workstation agent domain model"
```

---

### Task 2: SQLite Agent Repository and Unit of Work Port

**Files:**
- Modify: `apps/api/app/domain/interfaces/unit_of_work.py`
- Modify: `apps/api/app/infrastructure/persistence/database.py`
- Modify: `apps/api/app/infrastructure/repositories/sqlite.py`
- Create: `apps/api/test/integration/test_agent_repository.py`

**Interfaces:**
- Consumes: `Agent` and `AgentStatus` from Task 1.
- Produces: `AgentRepository.add/get/find/save/list_all`; `UnitOfWork.agents`; SQLite `agents` table.

- [ ] **Step 1: Write failing repository tests**

```python
from datetime import UTC, datetime, timedelta

from app.domain.entities.agent import Agent
from app.infrastructure.persistence.database import SqliteDatabase


NOW = datetime(2026, 8, 25, 9, 0, tzinfo=UTC)


def test_sqlite_agent_repository_round_trip_and_order(tmp_path) -> None:
    database = SqliteDatabase(tmp_path / "agents.db")
    database.initialize()
    with database.unit_of_work() as uow:
        uow.agents.add(Agent.register("PC02", "B", "192.168.3.55", "1.0.0", NOW))
        uow.agents.add(Agent.register("PC01", "A", "192.168.3.56", "1.0.0", NOW))
        uow.commit()
    with database.unit_of_work() as uow:
        assert [agent.id for agent in uow.agents.list_all()] == ["PC01", "PC02"]
        assert uow.agents.find("missing") is None


def test_sqlite_agent_repository_saves_heartbeat(tmp_path) -> None:
    database = SqliteDatabase(tmp_path / "heartbeat.db")
    database.initialize()
    with database.unit_of_work() as uow:
        uow.agents.add(Agent.register("PC01", "A", "192.168.3.56", "1.0.0", NOW))
        uow.commit()
    with database.unit_of_work() as uow:
        agent = uow.agents.get("PC01")
        agent.heartbeat(NOW + timedelta(seconds=5))
        uow.agents.save(agent)
        uow.commit()
    with database.unit_of_work() as uow:
        assert uow.agents.get("PC01").last_seen == NOW + timedelta(seconds=5)
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest apps/api/test/integration/test_agent_repository.py -v`

Expected: failure because `UnitOfWork` has no `agents` repository and the table is absent.

- [ ] **Step 3: Add the domain port, schema, and adapter**

Add this protocol and property:

```python
class AgentRepository(Protocol):
    def add(self, agent: Agent) -> None: ...
    def get(self, agent_id: str) -> Agent: ...
    def find(self, agent_id: str) -> Agent | None: ...
    def save(self, agent: Agent) -> None: ...
    def list_all(self) -> list[Agent]: ...


class UnitOfWork(Protocol):
    agents: AgentRepository
```

Add the explicit SQLite table:

```sql
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    hostname TEXT NOT NULL,
    ip_address TEXT NOT NULL,
    status TEXT NOT NULL,
    agent_version TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_agents_status_last_seen ON agents(status, last_seen);
```

Implement `SqliteAgentRepository`, mapping ISO strings with `datetime.fromisoformat`, raising `EntityNotFoundError(f"agent not found: {agent_id}")` from `get`/failed `save`, and ordering `list_all` with `ORDER BY id`. Instantiate it as `self.agents` in `SqliteUnitOfWork.__enter__`.

- [ ] **Step 4: Verify GREEN and regression tests**

Run: `uv run pytest apps/api/test/integration/test_agent_repository.py -v`

Expected: 2 tests pass.

Run: `uv run pytest apps/api/test/unit/test_domain_pipeline.py apps/api/test/integration/test_pipeline_api.py -v`

Expected: existing tests pass.

- [ ] **Step 5: Commit**

```powershell
git add apps/api/app/domain/interfaces/unit_of_work.py apps/api/app/infrastructure/persistence/database.py apps/api/app/infrastructure/repositories/sqlite.py apps/api/test/integration/test_agent_repository.py
git commit -m "feat: persist workstation agents in sqlite"
```

---

### Task 3: Registration, Heartbeat, and Listing Use Cases

**Files:**
- Create: `apps/api/app/application/dtos/agents.py`
- Create: `apps/api/app/application/use_cases/agents/__init__.py`
- Create: `apps/api/app/application/use_cases/agents/management.py`
- Create: `apps/api/test/unit/test_agent_use_cases.py`

**Interfaces:**
- Consumes: `UnitOfWorkFactory`, `AgentRepository`, and Agent domain methods.
- Produces: `RegisterAgentInput`; callable `RegisterAgent`, `HeartbeatAgent`, and `ListAgents` classes.

- [ ] **Step 1: Write failing use-case tests with a real temporary SQLite database**

```python
from datetime import UTC, datetime, timedelta

from app.application.dtos.agents import RegisterAgentInput
from app.application.use_cases.agents.management import HeartbeatAgent, ListAgents, RegisterAgent
from app.domain.value_objects.enums import AgentStatus
from app.infrastructure.persistence.database import SqliteDatabase


def test_register_is_idempotent_and_preserves_created_at(tmp_path) -> None:
    now = datetime(2026, 8, 25, 9, 0, tzinfo=UTC)
    database = SqliteDatabase(tmp_path / "use-cases.db")
    database.initialize()
    register = RegisterAgent(database.unit_of_work, lambda: now)
    first = register(RegisterAgentInput("PC01", "OLD", "192.168.3.10", "0.9.0"))
    now += timedelta(minutes=1)
    second = register(RegisterAgentInput("PC01", "NEW", "192.168.3.56", "1.0.0"))
    assert second.created_at == first.created_at
    assert second.hostname == "NEW"
    assert second.last_seen == now


def test_heartbeat_and_list_apply_liveness_rule(tmp_path) -> None:
    now = datetime(2026, 8, 25, 9, 0, tzinfo=UTC)
    database = SqliteDatabase(tmp_path / "liveness.db")
    database.initialize()
    register = RegisterAgent(database.unit_of_work, lambda: now)
    heartbeat = HeartbeatAgent(database.unit_of_work, lambda: now)
    list_agents = ListAgents(database.unit_of_work, lambda: now)
    register(RegisterAgentInput("PC02", "B", "192.168.3.55", "1.0.0"))
    register(RegisterAgentInput("PC01", "A", "192.168.3.56", "1.0.0"))
    now += timedelta(seconds=16)
    assert [agent.status for agent in list_agents()] == [AgentStatus.OFFLINE] * 2
    heartbeat("PC01")
    assert [agent.status for agent in list_agents()] == [
        AgentStatus.ONLINE, AgentStatus.OFFLINE
    ]
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest apps/api/test/unit/test_agent_use_cases.py -v`

Expected: collection fails because the DTO and use cases do not exist.

- [ ] **Step 3: Implement DTO and callable use cases**

```python
@dataclass(frozen=True, slots=True)
class RegisterAgentInput:
    agent_id: str
    hostname: str
    ip_address: str
    agent_version: str
```

Each use-case constructor accepts `uow_factory: UnitOfWorkFactory` and `clock: Callable[[], datetime] = utc_now`. `RegisterAgent.__call__` uses `find`, then `Agent.register` or `reregister`; `HeartbeatAgent.__call__(agent_id)` uses `get`, `heartbeat`, and `save`; `ListAgents.__call__()` uses one clock reading, calls `refresh_liveness`, saves changed agents, commits once, and returns the ordered list.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest apps/api/test/unit/test_agent_use_cases.py -v`

Expected: 2 tests pass.

Run: `uv run ruff check apps/api/app/application apps/api/test/unit/test_agent_use_cases.py`

Expected: exit 0.

- [ ] **Step 5: Commit**

```powershell
git add apps/api/app/application/dtos/agents.py apps/api/app/application/use_cases/agents apps/api/test/unit/test_agent_use_cases.py
git commit -m "feat: add agent management use cases"
```

---

### Task 4: FastAPI Agent Endpoints and DI

**Files:**
- Create: `apps/api/app/presentation/schemas/agents.py`
- Create: `apps/api/app/presentation/api/routers/agents.py`
- Modify: `apps/api/app/presentation/api/deps.py`
- Modify: `apps/api/app/infrastructure/di/container.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/test/integration/test_agents_api.py`

**Interfaces:**
- Consumes: callable use cases from Task 3.
- Produces: `POST /api/v1/agents/register`; `POST /api/v1/agents/{agent_id}/heartbeat`; `GET /api/v1/agents`.

- [ ] **Step 1: Write failing API tests**

```python
from pathlib import Path

from app.main import create_app
from fastapi.testclient import TestClient


def test_register_heartbeat_and_list_agents(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "agents-api.db")) as client:
        registered = client.post("/api/v1/agents/register", json={
            "id": "PC01", "hostname": "DESKTOP-A",
            "ip_address": "192.168.3.56", "agent_version": "1.0.0",
        })
        assert registered.status_code == 201
        created_at = registered.json()["created_at"]
        registered_again = client.post("/api/v1/agents/register", json={
            "id": "PC01", "hostname": "DESKTOP-A2",
            "ip_address": "192.168.3.56", "agent_version": "1.0.1",
        })
        assert registered_again.status_code == 201
        assert registered_again.json()["created_at"] == created_at
        heartbeat = client.post("/api/v1/agents/PC01/heartbeat")
        assert heartbeat.status_code == 200
        agents = client.get("/api/v1/agents")
        assert agents.status_code == 200
        assert [agent["id"] for agent in agents.json()] == ["PC01"]


def test_heartbeat_unknown_agent_returns_404(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "missing-agent.db")) as client:
        response = client.post("/api/v1/agents/MISSING/heartbeat")
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest apps/api/test/integration/test_agents_api.py -v`

Expected: requests return 404 because the router is not registered.

- [ ] **Step 3: Implement schemas, dependencies, routes, and composition**

```python
class RegisterAgentRequest(ApiModel):
    id: str = Field(min_length=1)
    hostname: str = Field(min_length=1)
    ip_address: str = Field(min_length=1)
    agent_version: str = Field(min_length=1)


class AgentView(ApiModel):
    id: str
    hostname: str
    ip_address: str
    status: AgentStatus
    agent_version: str
    last_seen: datetime
    created_at: datetime
```

Create three typed dependencies from `request.app.state.container`, add the three use cases to the frozen `Container`, and build them from `database.unit_of_work`. The new router maps request `id` to DTO `agent_id`, uses status 201 for registration, and validates entity instances with `AgentView.model_validate(agent, from_attributes=True)` or equivalent configured `from_attributes` support. Include `agents.router` after the existing router in `create_app`.

- [ ] **Step 4: Verify GREEN and OpenAPI route coexistence**

Run: `uv run pytest apps/api/test/integration/test_agents_api.py apps/api/test/integration/test_pipeline_api.py -v`

Expected: new and existing integration tests pass, including existing `/api/v1/agents/{target_id}/commands` behavior.

Run: `uv run ruff check apps/api`

Expected: exit 0.

- [ ] **Step 5: Commit**

```powershell
git add apps/api/app/presentation/schemas/agents.py apps/api/app/presentation/api/routers/agents.py apps/api/app/presentation/api/deps.py apps/api/app/infrastructure/di/container.py apps/api/app/main.py apps/api/test/integration/test_agents_api.py
git commit -m "feat: expose agent registration and heartbeat API"
```

---

### Task 5: Standalone Workstation Agent

**Files:**
- Create: `agent/__init__.py`
- Create: `agent/config.py`
- Create: `agent/heartbeat.py`
- Create: `agent/main.py`
- Create: `apps/api/test/unit/test_workstation_agent.py`

**Interfaces:**
- Consumes: HTTP endpoints from Task 4.
- Produces: `WorkstationIdentity`; `collect_identity`; `AgentClient.register`; `AgentClient.heartbeat`; `run_agent`.

- [ ] **Step 1: Write failing client tests**

```python
import json

import pytest

from agent.heartbeat import AgentClient, WorkstationIdentity
from agent.main import run_agent


class Response:
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def read(self): return b'{}'


def test_agent_client_sends_registration_and_heartbeat_paths() -> None:
    requests = []
    def open_request(request, timeout):
        requests.append((request, timeout))
        return Response()
    client = AgentClient("http://192.168.3.50:8000", opener=open_request)
    identity = WorkstationIdentity("PC01", "DESKTOP-A", "192.168.3.56", "1.0.0")
    client.register(identity)
    client.heartbeat("PC01")
    assert requests[0][0].full_url.endswith("/api/v1/agents/register")
    assert json.loads(requests[0][0].data) == {
        "id": "PC01", "hostname": "DESKTOP-A",
        "ip_address": "192.168.3.56", "agent_version": "1.0.0",
    }
    assert requests[1][0].full_url.endswith("/api/v1/agents/PC01/heartbeat")


def test_failed_heartbeat_causes_reregistration_on_next_iteration() -> None:
    calls = []
    class Client:
        def register(self, _identity): calls.append("register")
        def heartbeat(self, _agent_id):
            calls.append("heartbeat")
            raise OSError("server unavailable")
    sleeps = 0
    def stop_after_three_sleeps(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 3: raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        run_agent(
            Client(),
            WorkstationIdentity("PC01", "A", "1.2.3.4", "1.0.0"),
            5,
            stop_after_three_sleeps,
        )
    assert calls == ["register", "heartbeat", "register"]
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest apps/api/test/unit/test_workstation_agent.py -v`

Expected: collection fails because the `agent` package does not exist.

- [ ] **Step 3: Implement configuration, identity, HTTP client, and loop**

Use environment-backed constants:

```python
SERVER_URL = os.getenv("EECP_SERVER_URL", "http://192.168.3.50:8000").rstrip("/")
AGENT_ID = os.getenv("EECP_AGENT_ID", "PC01")
AGENT_VERSION = os.getenv("EECP_AGENT_VERSION", "1.0.0")
HEARTBEAT_INTERVAL_SECONDS = 5
REQUEST_TIMEOUT_SECONDS = 5
```

`AgentClient._post` builds a JSON `urllib.request.Request` with method POST and `Content-Type: application/json`. `collect_identity` obtains `socket.gethostname()` and selects local IPv4 through a UDP socket pointed at the hostname parsed from `SERVER_URL`, falling back to `socket.gethostbyname(hostname)`. `run_agent` registers first, heartbeats on later iterations, marks itself unregistered on `URLError`, `OSError`, or timeout, logs the exception, and sleeps in a `finally` block. `main()` catches `KeyboardInterrupt` and prints a stop message.

- [ ] **Step 4: Verify GREEN and CLI importability**

Run: `uv run pytest apps/api/test/unit/test_workstation_agent.py -v`

Expected: 2 tests pass.

Run: `uv run python -c "from agent.main import main; print('agent import ok')"`

Expected: prints `agent import ok` without making a network request.

Run: `uv run ruff check agent apps/api/test/unit/test_workstation_agent.py`

Expected: exit 0.

- [ ] **Step 5: Commit**

```powershell
git add agent apps/api/test/unit/test_workstation_agent.py
git commit -m "feat: add standalone workstation heartbeat agent"
```

---

### Task 6: Live Workstation Dashboard

**Files:**
- Create: `apps/web/features/workstations/types.ts`
- Create: `apps/web/features/workstations/queries.ts`
- Create: `apps/web/features/workstations/components/auto-refresh.tsx`
- Create: `apps/web/features/workstations/components/workstation-list.tsx`
- Create: `apps/web/features/workstations/index.ts`
- Create: `apps/web/app/workstations/page.tsx`
- Modify: `apps/web/app/globals.css`

**Interfaces:**
- Consumes: `GET /api/v1/agents` and shared `fetchApi`/`StatusPill`.
- Produces: server-rendered `/workstations` page with five-second refresh.

- [ ] **Step 1: Add the page against missing feature modules and verify RED**

```tsx
import { WorkstationList } from "@/features/workstations";

export const dynamic = "force-dynamic";

export default function WorkstationsPage() {
  return (
    <main className="page-shell">
      <header className="hero">
        <p className="eyebrow">Control Server</p>
        <h1>Exam Workstations</h1>
        <p>Live registration and heartbeat status for workstation agents.</p>
      </header>
      <WorkstationList />
    </main>
  );
}
```

- [ ] **Step 2: Verify RED**

Run from `apps/web`: `npm run typecheck`

Expected: TypeScript cannot resolve `@/features/workstations`.

- [ ] **Step 3: Implement types, query, refresh, list, exports, and styles**

```typescript
export type Agent = {
  id: string;
  hostname: string;
  ip_address: string;
  status: "ONLINE" | "OFFLINE";
  agent_version: string;
  last_seen: string;
  created_at: string;
};
```

`getAgents(): Promise<Agent[] | null>` calls `fetchApi<Agent[]>("/api/v1/agents")` and returns `null` only on API failure. `AutoRefresh` is a `"use client"` component whose effect installs `setInterval(() => router.refresh(), 5000)` and clears it on unmount. `WorkstationList` renders the refresh component, API-unavailable message for `null`, empty message for `[]`, and ID-keyed cards for data. Cards use `StatusPill` with `success` for ONLINE and `warning` for OFFLINE and show hostname, IP, version, and formatted last heartbeat.

Add focused `.workstations-card`, `.workstations-grid`, `.workstation`, and `.workstation__details` CSS using existing color variables and responsive breakpoints; do not alter the existing pipeline styles.

- [ ] **Step 4: Verify GREEN and production build**

Run from `apps/web`: `npm run typecheck`

Expected: exit 0.

Run from `apps/web`: `npm run build`

Expected: production build succeeds and lists `/workstations`.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/features/workstations apps/web/app/workstations/page.tsx apps/web/app/globals.css
git commit -m "feat: add live workstation monitoring page"
```

---

### Task 7: LAN Runbook and Full Verification

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: finished backend, workstation agent, and dashboard.
- Produces: exact PC01/PC02 commands and LAN demo sequence.

- [ ] **Step 1: Add the Phase 1 runbook**

Document these commands exactly, with Python available on each workstation:

```powershell
# Control Server 192.168.3.50
uv sync --all-packages
uv run --package eecp-api uvicorn app.main:app --app-dir apps/api --host 0.0.0.0 --port 8000
```

```powershell
# Frontend on Control Server
$env:EECP_API_URL="http://192.168.3.50:8000"
cd apps/web
npm install
npm run dev -- --hostname 0.0.0.0
```

```powershell
# Workstation A / PC01
$env:EECP_SERVER_URL="http://192.168.3.50:8000"
$env:EECP_AGENT_ID="PC01"
python -m agent.main
```

```powershell
# Workstation B / PC02
$env:EECP_SERVER_URL="http://192.168.3.50:8000"
$env:EECP_AGENT_ID="PC02"
python -m agent.main
```

Explain copying/cloning the repo to each workstation, opening `http://192.168.3.50:3000/workstations`, verifying both ONLINE, stopping one agent with Ctrl+C, waiting up to 20 seconds, and verifying OFFLINE.

- [ ] **Step 2: Run all backend and agent checks**

Run: `uv run ruff check apps/api agent`

Expected: exit 0.

Run: `uv run pytest`

Expected: all existing and new tests pass.

- [ ] **Step 3: Run all frontend checks**

Run from `apps/web`: `npm run typecheck`

Expected: exit 0.

Run from `apps/web`: `npm run build`

Expected: exit 0 and `/workstations` is present.

- [ ] **Step 4: Inspect final diff and endpoint registration**

Run: `git diff --check`

Expected: no whitespace errors.

Run: `uv run --package eecp-api python -c "from app.main import create_app; paths=create_app('data/route-check.db').openapi()['paths']; print(sorted(path for path in paths if 'agents' in path))"`

Expected output includes `/api/v1/agents`, `/api/v1/agents/register`, `/api/v1/agents/{agent_id}/heartbeat`, and the existing `/api/v1/agents/{target_id}/commands`.

- [ ] **Step 5: Commit documentation**

```powershell
git add README.md
git commit -m "docs: add workstation LAN demo runbook"
```
