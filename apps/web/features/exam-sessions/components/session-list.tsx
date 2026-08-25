import { StatusPill } from "@/components/ui/status-pill";
import { getSessions } from "@/features/exam-sessions/queries";
import type { SessionStatus } from "@/features/exam-sessions/types";
import { AutoRefresh } from "@/features/workstations/components/auto-refresh";
import { TransitionForm } from "./transition-form";

const nextStatus = {
  CREATED: ["READY", "Mark Ready"],
  READY: ["RUNNING", "Start Exam"],
  RUNNING: ["FINISHED", "Finish Exam"],
} as const;

function statusTone(status: SessionStatus) {
  if (status === "READY" || status === "RUNNING" || status === "FINISHED") {
    return "success" as const;
  }

  if (status === "DEGRADED") {
    return "warning" as const;
  }

  return "neutral" as const;
}

export async function SessionList() {
  const sessions = await getSessions();

  return (
    <section className="sessions-card" aria-labelledby="sessions-title">
      <AutoRefresh />
      <div className="sessions-card__header">
        <div>
          <p className="eyebrow">Live sessions</p>
          <h2 id="sessions-title">Exam sessions</h2>
        </div>
        <StatusPill
          label={sessions === null ? "API unavailable" : `${sessions.length} total`}
          tone={sessions === null ? "warning" : "neutral"}
        />
      </div>

      {sessions === null ? (
        <p className="sessions-message">
          Cannot reach the control server. The dashboard will retry automatically.
        </p>
      ) : sessions.length === 0 ? (
        <p className="sessions-message">No exam sessions have been created yet.</p>
      ) : (
        <div className="sessions-grid">
          {sessions.map((session) => {
            const transition = nextStatus[session.status as keyof typeof nextStatus];

            return (
              <article className="session-card" key={session.id}>
                <div className="session-card__heading">
                  <div>
                    <p className="session-card__room">{session.room}</p>
                    <h3>{session.name}</h3>
                  </div>
                  <StatusPill
                    label={session.status}
                    tone={statusTone(session.status)}
                  />
                </div>

                <dl className="session-card__details">
                  <div>
                    <dt>Session ID</dt>
                    <dd>{session.id}</dd>
                  </div>
                  <div>
                    <dt>Management</dt>
                    <dd>{session.gateway_id === null ? "Direct" : "Gateway"}</dd>
                  </div>
                  <div>
                    <dt>Assigned Agents</dt>
                    <dd>{session.agent_count}</dd>
                  </div>
                </dl>

                <div className="session-agents">
                  <h4>Assigned Agents</h4>
                  {session.agents.length === 0 ? (
                    <p className="session-agents__empty">No Agents assigned.</p>
                  ) : (
                    <ul className="session-agents__list">
                      {session.agents.map((agent) => (
                        <li className="session-agent" key={agent.id}>
                          <div className="session-agent__identity">
                            <strong>{agent.id}</strong>
                            <span>
                              {agent.hostname ?? "Unknown host"} ·{" "}
                              {agent.ip_address ?? "IP unavailable"}
                            </span>
                          </div>
                          <div className="session-agent__statuses">
                            <StatusPill
                              label={agent.status ?? "unavailable"}
                              tone={agent.status === "ONLINE" ? "success" : "warning"}
                            />
                            <StatusPill
                              label={session.status}
                              tone={statusTone(session.status)}
                            />
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {session.gateway_id === null && transition ? (
                  <TransitionForm
                    sessionId={session.id}
                    target={transition[0]}
                    label={transition[1]}
                  />
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
