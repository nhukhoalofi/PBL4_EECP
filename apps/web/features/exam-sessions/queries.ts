import { fetchApi } from "@/lib/api-client";
import type { ApiHealth } from "@/features/exam-sessions/types";

export async function getApiHealth(): Promise<ApiHealth | null> {
  try {
    return await fetchApi<ApiHealth>("/health");
  } catch {
    return null;
  }
}

