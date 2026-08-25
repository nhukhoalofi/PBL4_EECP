"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import {
  createSession,
  updateSessionStatus,
} from "@/features/exam-sessions/mutations";
import { ApiError } from "@/lib/api-client";

export type CreateSessionActionState = { error: string | null };

const connectionError = "Không thể kết nối đến máy chủ EECP.";

export async function createSessionAction(
  _previous: CreateSessionActionState,
  formData: FormData,
): Promise<CreateSessionActionState> {
  const name = formData.get("name")?.toString().trim() ?? "";
  const room = formData.get("room")?.toString().trim() ?? "";
  const agentIds = formData
    .getAll("agent_ids")
    .filter((value): value is string => typeof value === "string")
    .map((value) => value.trim())
    .filter(Boolean);

  if (!name || !room || agentIds.length === 0) {
    return { error: "Vui lòng nhập tên kỳ thi, phòng thi và chọn ít nhất một máy trạm." };
  }

  try {
    await createSession({ name, room, agent_ids: agentIds });
  } catch (error) {
    return {
      error: error instanceof ApiError ? error.detail : connectionError,
    };
  }

  revalidatePath("/sessions");
  redirect("/sessions");
}

export async function transitionSessionAction(
  sessionId: string,
  target: "READY" | "RUNNING" | "FINISHED",
): Promise<void> {
  try {
    await updateSessionStatus(sessionId, target);
  } catch (error) {
    throw new Error(error instanceof ApiError ? error.detail : connectionError);
  }

  revalidatePath("/sessions");
}
