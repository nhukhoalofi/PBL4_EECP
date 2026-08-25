export type ApiHealth = {
  status: "ok";
};

export type PipelineStage = {
  state: string;
  label: string;
  description: string;
};

export type SessionStatus =
  | "CREATED"
  | "DEPLOYING"
  | "PREFLIGHT"
  | "READY"
  | "DEGRADED"
  | "RUNNING"
  | "RESTORING"
  | "NORMAL"
  | "FINISHED";

export type AssignedAgent = {
  id: string;
  hostname: string | null;
  ip_address: string | null;
  status: "ONLINE" | "OFFLINE" | null;
  last_seen: string | null;
  assigned_at: string | null;
};

export type ExamSession = {
  id: string;
  name: string;
  room: string;
  status: SessionStatus;
  gateway_id: string | null;
  created_at: string;
  updated_at: string;
  agent_count: number;
  agents: AssignedAgent[];
};

export type CreateSessionPayload = {
  name: string;
  room: string;
  agent_ids: string[];
};

