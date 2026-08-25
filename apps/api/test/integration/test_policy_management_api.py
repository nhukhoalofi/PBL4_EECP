from pathlib import Path

from app.main import create_app
from fastapi.testclient import TestClient


def _register(client: TestClient, agent_id: str) -> None:
    response = client.post(
        "/api/v1/agents/register",
        json={
            "id": agent_id,
            "hostname": f"HOST-{agent_id}",
            "ip_address": "192.168.3.56",
            "agent_version": "1.1.0",
        },
    )
    assert response.status_code == 201


def test_profile_catalog_exposes_generated_yaml(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "profiles.db")) as client:
        response = client.get("/api/v1/policy-profiles")

    assert response.status_code == 200
    profile = response.json()[0]
    assert profile["id"] == "INTERNET_NO_AI"
    assert profile["label"] == "Internet + No AI"
    assert "policy:" in profile["yaml"]
    assert "generative_ai" in profile["yaml"]
    assert profile["rules"]["devices"]["usb"] == "deny"


def test_new_session_pushes_policy_and_restores_after_finish(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "policy-flow.db")) as client:
        _register(client, "PC01")
        created = client.post(
            "/api/v1/sessions",
            json={
                "name": "PBL4 Final",
                "room": "A101",
                "agent_ids": ["PC01"],
                "policy_profile": "INTERNET_NO_AI",
            },
        )
        assert created.status_code == 201
        session = created.json()
        session_id = session["id"]
        assert session["policy"]["profile"] == "INTERNET_NO_AI"
        assert session["agents"][0]["policy_status"] == "PENDING"

        commands = client.get("/api/v1/agents/PC01/commands").json()
        assert len(commands) == 1
        apply_command = commands[0]
        assert apply_command["type"] == "APPLY_POLICY"
        assert apply_command["payload"]["format"] == "eecp-policy/v1"
        policy_hash = apply_command["payload"]["policy_hash"]

        acknowledged = client.post(
            f"/api/v1/commands/{apply_command['id']}/acknowledge",
            json={
                "success": True,
                "policy_hash": policy_hash,
                "actor": "PC01",
            },
        )
        assert acknowledged.status_code == 200
        detail = client.get(f"/api/v1/sessions/{session_id}").json()
        assert detail["agents"][0]["policy_status"] == "APPLIED"

        for target in ("READY", "RUNNING", "FINISHED"):
            transitioned = client.patch(
                f"/api/v1/sessions/{session_id}/status",
                json={"status": target},
            )
            assert transitioned.status_code == 200

        commands = client.get("/api/v1/agents/PC01/commands").json()
        assert len(commands) == 1
        restore_command = commands[0]
        assert restore_command["type"] == "RESTORE_BASELINE"
        restored = client.post(
            f"/api/v1/commands/{restore_command['id']}/acknowledge",
            json={"success": True, "actor": "PC01"},
        )
        assert restored.status_code == 200
        detail = client.get(f"/api/v1/sessions/{session_id}").json()
        assert detail["status"] == "FINISHED"
        assert detail["agents"][0]["policy_status"] == "RESTORED"


def test_unknown_policy_profile_is_rejected_without_creating_session(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(tmp_path / "unknown-profile.db")) as client:
        _register(client, "PC01")
        response = client.post(
            "/api/v1/sessions",
            json={
                "name": "Exam",
                "room": "A101",
                "agent_ids": ["PC01"],
                "policy_profile": "NOT_A_PROFILE",
            },
        )

        assert response.status_code == 422
        assert response.json()["code"] == "DOMAIN_VALIDATION"
        assert client.get("/api/v1/sessions").json() == []
