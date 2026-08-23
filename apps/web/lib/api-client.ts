import { config } from "@/lib/config";

export async function fetchApi<T>(path: string): Promise<T> {
  const response = await fetch(`${config.apiBaseUrl}${path}`, {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`EECP API returned ${response.status} for ${path}`);
  }
  return (await response.json()) as T;
}

