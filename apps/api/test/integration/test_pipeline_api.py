from pathlib import Path

from app.main import create_app
from fastapi.testclient import TestClient


def test_complete_exam_pipeline(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "pipeline.db")) as client:
        created = client.post(
            "/api/v1/sessions",
            json={
                "exam_name": "Lập trình C - No AI",
                "room_id": "F301",
                "gateway_id": "gw-f301",
                "workstation_ids": ["PC01", "PC02", "PC03"],
                "actor": "teacher-01",
            },
        )
        assert created.status_code == 201
        session_id = created.json()["id"]

        deployed = client.post(
            f"/api/v1/sessions/{session_id}/policy/deploy",
            json={
                "profile": "PROGRAMMING_EXAM",
                "actor": "teacher-01",
                "rules": {
                    "applications": {
                        "allow": ["vscode.exe", "gcc.exe"],
                        "deny": ["anydesk.exe", "teamviewer.exe"],
                    },
                    "network": {
                        "blocked_categories": ["generative_ai", "vpn_proxy"],
                        "allow_domains": ["lms.dut.udn.vn", "cppreference.com"],
                    },
                    "devices": {"usb_storage": "deny"},
                },
            },
        )
        assert deployed.status_code == 200
        assert deployed.json()["state"] == "DEPLOYING"
        policy_hash = deployed.json()["policy"]["policy_hash"]

        for target_id in ["gw-f301", "PC01", "PC02", "PC03"]:
            commands = client.get(f"/api/v1/agents/{target_id}/commands").json()
            assert len(commands) == 1
            acknowledged = client.post(
                f"/api/v1/commands/{commands[0]['id']}/acknowledge",
                json={"success": True, "policy_hash": policy_hash, "actor": target_id},
            )
            assert acknowledged.status_code == 200

        assert acknowledged.json()["state"] == "PREFLIGHT"

        checks = [
            {"name": "agent_online", "passed": True, "critical": True},
            {"name": "policy_compliant", "passed": True, "critical": True},
            {"name": "dns_policy", "passed": True, "critical": True},
            {"name": "exam_app", "passed": True, "critical": True},
            {"name": "clock_sync", "passed": True, "critical": False},
        ]
        for workstation_id in ["PC01", "PC02", "PC03"]:
            preflight = client.post(
                f"/api/v1/sessions/{session_id}/workstations/{workstation_id}/preflight",
                json={"checks": checks, "actor": workstation_id},
            )
            assert preflight.status_code == 200
        assert preflight.json()["state"] == "READY"

        started = client.post(
            f"/api/v1/sessions/{session_id}/start",
            json={"actor": "teacher-01"},
        )
        assert started.status_code == 200
        assert started.json()["state"] == "RUNNING"

        blocked = client.post(
            f"/api/v1/sessions/{session_id}/telemetry",
            json={
                "workstation_id": "PC01",
                "event_type": "NETWORK_BLOCK",
                "severity": "INFO",
                "category": "GENERATIVE_AI",
                "action": "BLOCKED",
                "destination": "chatgpt.com",
            },
        )
        assert blocked.status_code == 202
        assert blocked.json()["incident_id"] is None

        incident_id = None
        for workstation_id in ["PC01", "PC02", "PC03"]:
            dns_failure = client.post(
                f"/api/v1/sessions/{session_id}/telemetry",
                json={
                    "workstation_id": workstation_id,
                    "event_type": "DNS_FAILURE",
                    "severity": "WARNING",
                    "category": "DNS",
                    "action": "OBSERVED",
                },
            )
            assert dns_failure.status_code == 202
            incident_id = dns_failure.json()["incident_id"] or incident_id
        assert incident_id is not None

        finished = client.post(
            f"/api/v1/sessions/{session_id}/finish",
            json={"actor": "teacher-01"},
        )
        assert finished.status_code == 200
        assert finished.json()["state"] == "RESTORING"

        for target_id in ["gw-f301", "PC01", "PC02", "PC03"]:
            commands = client.get(f"/api/v1/agents/{target_id}/commands").json()
            restore = next(command for command in commands if command["type"] == "RESTORE_BASELINE")
            acknowledged = client.post(
                f"/api/v1/commands/{restore['id']}/acknowledge",
                json={"success": True, "actor": target_id},
            )
            assert acknowledged.status_code == 200

        assert acknowledged.json()["state"] == "NORMAL"
        summary = client.get(f"/api/v1/sessions/{session_id}/summary")
        assert summary.status_code == 200
        body = summary.json()
        assert body["session"]["state"] == "NORMAL"
        assert body["telemetry_count"] == 4
        assert body["blocked_event_count"] == 1
        assert len(body["incidents"]) == 1
        assert body["incidents"][0]["category"] == "INFRASTRUCTURE_DNS"
        assert body["audit_chain_valid"] is True


def test_start_gate_rejects_unready_session(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "gate.db")) as client:
        created = client.post(
            "/api/v1/sessions",
            json={
                "exam_name": "Exam",
                "room_id": "F301",
                "gateway_id": "gw-f301",
                "workstation_ids": ["PC01"],
            },
        ).json()

        response = client.post(
            f"/api/v1/sessions/{created['id']}/start",
            json={"actor": "teacher-01"},
        )

        assert response.status_code == 409
        assert response.json()["code"] == "READINESS_GATE"
