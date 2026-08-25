# Phase 3 Policy Management

## Flow

```text
Teacher selects Exam Profile
  -> POST /api/v1/sessions
  -> Control Server creates session + policy + commands atomically
  -> Agent polls GET /api/v1/agents/{agent_id}/commands
  -> Agent applies Windows controls
  -> Agent POSTs /api/v1/commands/{command_id}/acknowledge
  -> Dashboard reports the per-Agent policy status
```

The transport is short polling on the existing five-second Agent loop. A
command is durable in SQLite, so an Agent that is temporarily offline receives
it after reconnecting. This gives the requested push-command behavior without
losing commands when a workstation is disconnected.

## Policy profile contract

`GET /api/v1/policy-profiles` returns the selectable catalog, rule object, and a
generated YAML preview. Session creation accepts `policy_profile`:

```json
{
  "name": "PBL4 Final",
  "room": "A101",
  "agent_ids": ["PC01", "PC02"],
  "policy_profile": "INTERNET_NO_AI"
}
```

For backward compatibility, omitting `policy_profile` selects
`INTERNET_NO_AI`. Its generated YAML is equivalent to:

```yaml
policy:
  profile: INTERNET_NO_AI
  rules:
    applications:
      allow:
        - vscode.exe
        - gcc.exe
      deny:
        - chatgpt.exe
        - anydesk.exe
        - teamviewer.exe
    network:
      block:
        - generative_ai
        - social_network
    devices:
      usb: deny
```

Each policy contains a monotonically increasing version and a SHA-256 hash over
its normalized profile, rules, and version. The Agent must ACK that exact hash;
an unexpected hash is rejected and the command remains pending.

## Lifecycle and recovery

Policy assignment does not replace the Phase 2 management lifecycle. A new
session remains `CREATED` while its per-workstation policy status progresses
from `PENDING` to `APPLIED` or `FAILED`. The teacher can observe that result on
the session dashboard.

At `FINISHED`, the server creates `RESTORE_BASELINE` commands for all assigned
Agents. Restore is idempotent. The Agent keeps a local state snapshot so the
previous USB setting can be restored even after an Agent restart. The hosts
file update uses explicit begin/end markers and never removes entries outside
that block.

The pre-existing gateway pipeline continues to use its original
`DEPLOYING -> PREFLIGHT` policy acknowledgement flow. Direct management ACKs do
not move session state, preventing the two lifecycle modes from being mixed.

## Clean Architecture placement

- The domain profile catalog owns selectable business rules, not YAML formatting.
- Application policy use cases list profiles, fetch commands, and process ACKs.
- The presentation layer generates the YAML preview and exposes HTTP schemas/routes.
- SQLite remains an infrastructure adapter behind the Unit of Work ports.
- The Agent application layer depends on policy-enforcement and command-client
  protocols; Windows and HTTP implementations live under `agent/infrastructure`.
