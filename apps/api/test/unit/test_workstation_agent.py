import json

import pytest

from agent import config as agent_config
from agent import main as agent_main
from agent.heartbeat import AgentClient, WorkstationIdentity, collect_identity
from agent.main import run_agent


class Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return b"{}"


def test_agent_id_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EECP_AGENT_ID", raising=False)

    with pytest.raises(RuntimeError, match="EECP_AGENT_ID"):
        agent_config.load_agent_id()


def test_agent_id_cannot_be_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EECP_AGENT_ID", "   ")

    with pytest.raises(RuntimeError, match="EECP_AGENT_ID"):
        agent_config.load_agent_id()


def test_agent_id_is_trimmed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EECP_AGENT_ID", "  PC02  ")

    assert agent_config.load_agent_id() == "PC02"


def test_main_stops_before_registration_when_agent_id_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EECP_AGENT_ID", raising=False)
    monkeypatch.setattr(
        agent_main,
        "collect_identity",
        lambda *_args: pytest.fail("identity must not be collected without an agent id"),
    )

    with pytest.raises(SystemExit, match="EECP_AGENT_ID is required"):
        agent_main.main()


def test_main_uses_configured_agent_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EECP_AGENT_ID", "PC02")
    captured_id = None

    def collect(agent_id, *_args):
        nonlocal captured_id
        captured_id = agent_id
        raise KeyboardInterrupt

    monkeypatch.setattr(agent_main, "collect_identity", collect)

    with pytest.raises(KeyboardInterrupt):
        agent_main.main()

    assert captured_id == "PC02"


def test_agent_client_sends_registration_payload_and_heartbeat_path() -> None:
    requests = []

    def open_request(request, timeout):
        requests.append((request, timeout))
        return Response()

    client = AgentClient(
        "http://192.168.3.50:8000/",
        timeout_seconds=4,
        opener=open_request,
    )
    identity = WorkstationIdentity(
        agent_id="PC01",
        hostname="DESKTOP-A",
        ip_address="192.168.3.56",
        agent_version="1.0.0",
    )

    client.register(identity)
    client.heartbeat("PC01")

    assert requests[0][0].full_url == (
        "http://192.168.3.50:8000/api/v1/agents/register"
    )
    assert json.loads(requests[0][0].data) == {
        "id": "PC01",
        "hostname": "DESKTOP-A",
        "ip_address": "192.168.3.56",
        "agent_version": "1.0.0",
    }
    assert requests[0][1] == 4
    assert requests[1][0].full_url == (
        "http://192.168.3.50:8000/api/v1/agents/PC01/heartbeat"
    )
    assert requests[1][0].get_method() == "POST"


def test_collect_identity_falls_back_to_hostname_resolution() -> None:
    def unavailable_socket(*_args, **_kwargs):
        raise OSError("no route")

    identity = collect_identity(
        agent_id="PC01",
        agent_version="1.0.0",
        server_url="http://192.168.3.50:8000",
        hostname_getter=lambda: "DESKTOP-A",
        resolver=lambda _hostname: "192.168.3.56",
        socket_factory=unavailable_socket,
    )

    assert identity == WorkstationIdentity(
        agent_id="PC01",
        hostname="DESKTOP-A",
        ip_address="192.168.3.56",
        agent_version="1.0.0",
    )


def test_failed_heartbeat_causes_reregistration_on_next_iteration() -> None:
    calls = []

    class Client:
        def register(self, _identity):
            calls.append("register")

        def heartbeat(self, _agent_id):
            calls.append("heartbeat")
            raise OSError("server unavailable")

    sleeps = 0

    def stop_after_three_sleeps(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 3:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_agent(
            Client(),
            WorkstationIdentity("PC01", "A", "1.2.3.4", "1.0.0"),
            interval_seconds=5,
            sleep=stop_after_three_sleeps,
            log=lambda _message: None,
        )

    assert calls == ["register", "heartbeat", "register"]
