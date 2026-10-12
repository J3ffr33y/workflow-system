/**
 * Thin fetch wrapper. All writes go through `command()` which maps to
 * POST /api/commands/<name>; types come from the generated OpenAPI schema,
 * so a backend change to a command's payload breaks the frontend build.
 */
import type { paths } from "./schema";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: any,
  ) {
    super(message);
  }
}

let csrfToken: string | null = null;
export function setCsrf(token: string | null) {
  csrfToken = token;
}

async function request<T>(method: string, url: string, body?: unknown, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined && !(body instanceof FormData)) headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;
  const res = await fetch(url, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
    ...init,
  });
  if (!res.ok) {
    let err: any = null;
    try {
      err = (await res.json())?.error;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, err?.code ?? "http_error", err?.message ?? res.statusText, err?.details);
  }
  const type = res.headers.get("content-type") ?? "";
  return (type.includes("application/json") ? res.json() : res.blob()) as Promise<T>;
}

export const api = {
  get: <T>(url: string, params?: Record<string, unknown>) => {
    const q = params
      ? "?" +
        new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== null && v !== "")
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : "";
    return request<T>("GET", `/api${url}${q}`);
  },
  post: <T>(url: string, body?: unknown) => request<T>("POST", `/api${url}`, body),
  download: async (url: string, body: unknown, filename: string) => {
    const blob = await request<Blob>("POST", `/api${url}`, body);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  },
};

type CommandPath = Extract<keyof paths, `/api/commands/${string}`>;
export type CommandName = CommandPath extends `/api/commands/${infer N}` ? N : never;
export type CommandBody<N extends CommandName> = paths[`/api/commands/${N}`] extends {
  post: { requestBody: { content: { "application/json": infer B } } };
}
  ? B
  : never;

export interface CommandResponse<R = any> {
  command_id: string;
  result: R;
  replayed: boolean;
}

export function command<R = any, N extends CommandName = CommandName>(
  name: N,
  body: CommandBody<N>,
): Promise<CommandResponse<R>> {
  return request<CommandResponse<R>>("POST", `/api/commands/${name}`, body);
}
