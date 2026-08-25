from __future__ import annotations

from agent.application.policy_commands import PolicyCommandProcessor
from agent.application.runtime import run_agent
from agent.config import (
    AGENT_VERSION,
    HEARTBEAT_INTERVAL_SECONDS,
    POLICY_MODE,
    POLICY_STATE_PATH,
    REQUEST_TIMEOUT_SECONDS,
    SERVER_URL,
    load_agent_id,
)
from agent.infrastructure.control_server import AgentClient
from agent.infrastructure.policy_enforcement import (
    AuditPolicyEnforcer,
    WindowsPolicyEnforcer,
)
from agent.infrastructure.system_identity import collect_identity


def main() -> None:
    try:
        agent_id = load_agent_id()
    except RuntimeError as exc:
        raise SystemExit(f"Configuration error: {exc}") from None

    identity = collect_identity(agent_id, AGENT_VERSION, SERVER_URL)
    client = AgentClient(SERVER_URL, REQUEST_TIMEOUT_SECONDS)
    if POLICY_MODE == "audit":
        enforcer = AuditPolicyEnforcer(POLICY_STATE_PATH)
    elif POLICY_MODE == "enforce":
        enforcer = WindowsPolicyEnforcer(POLICY_STATE_PATH)
    else:
        raise SystemExit(
            "Configuration error: EECP_POLICY_MODE must be 'enforce' or 'audit'"
        )
    command_processor = PolicyCommandProcessor(client, identity.agent_id, enforcer)
    try:
        run_agent(
            client,
            identity,
            HEARTBEAT_INTERVAL_SECONDS,
            process_commands=command_processor.process_pending,
        )
    except KeyboardInterrupt:
        print(f"Stopped agent {identity.agent_id}")


if __name__ == "__main__":
    main()
