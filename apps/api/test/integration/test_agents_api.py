from pathlib import Path

from app.main import create_app
from fastapi.testclient import TestClient


def test_register_heartbeat_and_list_agents(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "agents-api.db")) as client:
        registered = client.post(
            "/api/v1/agents/register",
            json={
                "id": "PC01",
                "hostname": "DESKTOP-A",
                "ip_address": "192.168.3.56",
                "agent_version": "1.0.0",
            },
        )
        assert registered.status_code == 201
        assert registered.json()["status"] == "ONLINE"
        created_at = registered.json()["created_at"]

        registered_again = client.post(
            "/api/v1/agents/register",
            json={
                "id": "PC01",
                "hostname": "DESKTOP-A2",
                "ip_address": "192.168.3.56",
                "agent_version": "1.0.1",
            },
        )
        assert registered_again.status_code == 201
        assert registered_again.json()["created_at"] == created_at
        assert registered_again.json()["hostname"] == "DESKTOP-A2"

        heartbeat = client.post("/api/v1/agents/PC01/heartbeat")
        assert heartbeat.status_code == 200
        assert heartbeat.json()["status"] == "ONLINE"

        agents = client.get("/api/v1/agents")
        assert agents.status_code == 200
        assert [agent["id"] for agent in agents.json()] == ["PC01"]


def test_heartbeat_unknown_agent_returns_404(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "missing-agent.db")) as client:
        response = client.post("/api/v1/agents/MISSING/heartbeat")

        assert response.status_code == 404
        assert response.json() == {
            "code": "NOT_FOUND",
            "detail": "agent not found: MISSING",
        }
