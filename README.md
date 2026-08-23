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

