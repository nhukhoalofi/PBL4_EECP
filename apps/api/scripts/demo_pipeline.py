from __future__ import annotations

import argparse
import json
import sys

import httpx

TARGETS = ["gw-f301", "PC01", "PC02", "PC03"]
WORKSTATIONS = TARGETS[1:]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run a complete EECP demo pipeline")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    with httpx.Client(base_url=args.base_url, timeout=10) as client:
        session = post(
            client,
            "/api/v1/sessions",
            {
                "exam_name": "Lập trình C - No AI",
                "room_id": "F301",
                "gateway_id": "gw-f301",
                "workstation_ids": WORKSTATIONS,
                "actor": "teacher-demo",
            },
        )
        session_id = session["id"]
        print_state("created", session)

        session = post(
            client,
            f"/api/v1/sessions/{session_id}/policy/deploy",
            {
                "profile": "PROGRAMMING_EXAM",
                "actor": "teacher-demo",
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
        policy_hash = session["policy"]["policy_hash"]
        print_state("policy deployed", session)

        for target in TARGETS:
            command = get(client, f"/api/v1/agents/{target}/commands")[0]
            session = post(
                client,
                f"/api/v1/commands/{command['id']}/acknowledge",
                {"success": True, "policy_hash": policy_hash, "actor": target},
            )
        print_state("all targets acknowledged policy", session)

        checks = [
            {"name": "agent_online", "passed": True, "critical": True},
            {"name": "policy_compliant", "passed": True, "critical": True},
            {"name": "dns_policy", "passed": True, "critical": True},
            {"name": "exam_app", "passed": True, "critical": True},
            {"name": "clock_sync", "passed": True, "critical": False},
        ]
        for workstation in WORKSTATIONS:
            session = post(
                client,
                f"/api/v1/sessions/{session_id}/workstations/{workstation}/preflight",
                {"checks": checks, "actor": workstation},
            )
        print_state("preflight complete", session)

        session = post(
            client,
            f"/api/v1/sessions/{session_id}/start",
            {"actor": "teacher-demo"},
        )
        print_state("exam started", session)

        post(
            client,
            f"/api/v1/sessions/{session_id}/telemetry",
            {
                "workstation_id": "PC01",
                "event_type": "NETWORK_BLOCK",
                "severity": "INFO",
                "category": "GENERATIVE_AI",
                "action": "BLOCKED",
                "destination": "chatgpt.com",
            },
        )
        for workstation in WORKSTATIONS:
            accepted = post(
                client,
                f"/api/v1/sessions/{session_id}/telemetry",
                {
                    "workstation_id": workstation,
                    "event_type": "DNS_FAILURE",
                    "severity": "WARNING",
                    "category": "DNS",
                    "action": "OBSERVED",
                },
            )
            if accepted["incident_id"]:
                print(f"incident correlated: {accepted['incident_id']}")

        session = post(
            client,
            f"/api/v1/sessions/{session_id}/finish",
            {"actor": "teacher-demo"},
        )
        print_state("restore requested", session)

        for target in TARGETS:
            commands = get(client, f"/api/v1/agents/{target}/commands")
            restore = next(item for item in commands if item["type"] == "RESTORE_BASELINE")
            session = post(
                client,
                f"/api/v1/commands/{restore['id']}/acknowledge",
                {"success": True, "actor": target},
            )
        print_state("restore complete", session)

        summary = get(client, f"/api/v1/sessions/{session_id}/summary")
        print(json.dumps(summary, ensure_ascii=False, indent=2))


def get(client: httpx.Client, path: str) -> dict | list:
    response = client.get(path)
    response.raise_for_status()
    return response.json()


def post(client: httpx.Client, path: str, payload: dict) -> dict:
    response = client.post(path, json=payload)
    response.raise_for_status()
    return response.json()


def print_state(label: str, session: dict) -> None:
    print(f"{label}: {session['state']}")


if __name__ == "__main__":
    main()
