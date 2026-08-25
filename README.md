# Exam Environment Control Platform (EECP)

Monorepo tách rõ backend FastAPI và frontend Next.js, tổ chức theo Clean Architecture.

```text
PBL4_EECP/
├── apps/
│   ├── api/                    # Backend FastAPI
│   │   ├── app/
│   │   │   ├── domain/         # Business rules và output ports
│   │   │   ├── application/    # DTO + use cases
│   │   │   ├── infrastructure/ # SQLite, repository, DI
│   │   │   ├── presentation/   # FastAPI routers + HTTP schemas
│   │   │   ├── config.py
│   │   │   └── main.py
│   │   ├── scripts/
│   │   ├── test/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   └── web/                    # Frontend Next.js, feature-first
│       ├── app/
│       ├── features/
│       ├── components/
│       ├── lib/
│       ├── Dockerfile
│       └── package.json
├── docs/
├── compose.yaml
├── pyproject.toml              # Python workspace/tooling
└── README.md
```

Không có `worker/` vì pipeline hiện tại được xử lý đồng bộ trong API và chưa có background job đủ độc lập để tách service.

## Pipeline đã triển khai

`Create → Deploy Policy → Agent/Gateway ACK → Preflight → Start → Telemetry/Incident → Finish → Restore → Summary`

- State machine: `CREATED → DEPLOYING → PREFLIGHT → READY/DEGRADED → RUNNING → RESTORING → NORMAL`.
- Policy có version và SHA-256 hash.
- Agent/Gateway poll command và ACK đúng policy hash.
- Preflight tính `READY/WARNING/FAILED` từ critical/non-critical check.
- Ba lỗi DNS trên ba máy được gom thành incident `INFRASTRUCTURE_DNS`.
- Blocked event không tự động được coi là bằng chứng gian lận.
- Audit event dùng hash-chain và được verify trong summary.

Chi tiết dependency rule và vị trí đặt code mới: [docs/clean-architecture-structure.md](docs/clean-architecture-structure.md).

## Chạy backend

```powershell
uv sync --all-packages
uv run --package eecp-api uvicorn app.main:app --app-dir apps/api --reload
```

- API docs: <http://127.0.0.1:8000/docs>
- Health: <http://127.0.0.1:8000/health>

Chạy demo pipeline khi API đang hoạt động:

```powershell
uv run --package eecp-api python apps/api/scripts/demo_pipeline.py
```

## Chạy frontend

```powershell
cd apps/web
npm install
npm run dev
```

Frontend: <http://127.0.0.1:3000>

## Chạy bằng Docker

```powershell
docker compose up --build
```

## Kiểm tra

```powershell
uv run ruff check apps/api
uv run pytest

cd apps/web
npm run typecheck
npm run build
```

## Demo Phase 1: Agent registration and heartbeat on LAN

### 1. Start the Control Server at 192.168.3.50

From the repository root:

```powershell
uv sync --all-packages
uv run --package eecp-api uvicorn app.main:app --app-dir apps/api --host 0.0.0.0 --port 8000
```

In another PowerShell terminal:

```powershell
$env:EECP_API_URL="http://192.168.3.50:8000"
cd apps/web
npm install
npm run dev -- --hostname 0.0.0.0
```

Allow inbound TCP ports 8000 and 3000 in Windows Firewall when other LAN machines cannot connect.

### 2. Start Workstation A as PC01

Clone or copy this repository to Workstation A, open PowerShell at the repository root, then run:

`EECP_AGENT_ID` is required and has no default. The agent exits before registration
when the variable is missing or blank.

```powershell
$env:EECP_SERVER_URL="http://192.168.3.50:8000"
$env:EECP_AGENT_ID="PC01"
Write-Host $env:EECP_AGENT_ID
python -m agent.main
```

Expected workstation address for the demo: `192.168.3.56`.

### 3. Start Workstation B as PC02

Clone or copy this repository to Workstation B, open PowerShell at the repository root, then run:

```powershell
$env:EECP_SERVER_URL="http://192.168.3.50:8000"
$env:EECP_AGENT_ID="PC02"
Write-Host $env:EECP_AGENT_ID
python -m agent.main
```

Expected workstation address for the demo: `192.168.3.55`.

### 4. Run the LAN demo

1. Open `http://192.168.3.50:3000/workstations` on the Control Server or another LAN machine.
2. Verify PC01 and PC02 both show `ONLINE`.
3. Stop one workstation agent with Ctrl+C.
4. Wait up to 20 seconds for the 15-second timeout plus the next dashboard refresh.
5. Verify the stopped workstation shows `OFFLINE` while the other remains `ONLINE`.
6. Restart the stopped agent and verify it returns to `ONLINE` without creating a duplicate record.

