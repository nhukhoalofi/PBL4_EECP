import { fetchApi } from "@/lib/api-client";
import type { Agent } from "@/features/workstations/types";
import type { ApiHealth, ExamSession } from "@/features/exam-sessions/types";

export async function getApiHealth(): Promise<ApiHealth | null> {
  try {
    return await fetchApi<ApiHealth>("/health");
  } catch {
    return null;
  }
}

export async function getSessions(): Promise<ExamSession[] | null> {
  try {
    return await fetchApi<ExamSession[]>("/api/v1/sessions");
  } catch {
    return null;
  }
}

export async function getAvailableAgents(): Promise<Agent[] | null> {
  try {
    return await fetchApi<Agent[]>("/api/v1/agents");
  } catch {
    return null;
  }
}

