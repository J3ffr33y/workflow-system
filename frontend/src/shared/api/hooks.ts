import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { ApiError, api, command, setCsrf, type CommandBody, type CommandName } from "./client";
import type { DirectoryUser, Me, WorkspaceSchema } from "./types";

export const qk = {
  me: ["me"] as const,
  schema: (ws: string) => ["schema", ws] as const,
  items: (ws: string) => ["items", ws] as const,
  item: (id: string) => ["item", id] as const,
  directory: ["directory"] as const,
};

export function useMe() {
  return useQuery({
    queryKey: qk.me,
    queryFn: async () => {
      const me = await api.get<Me>("/auth/me");
      setCsrf(me.csrf);
      return me;
    },
    retry: false,
    staleTime: 60_000,
  });
}

export function useSchema(workspaceId: string | undefined) {
  return useQuery({
    queryKey: qk.schema(workspaceId ?? ""),
    queryFn: () => api.get<WorkspaceSchema>(`/workspaces/${workspaceId}/schema`),
    enabled: !!workspaceId,
    staleTime: 5 * 60_000,
  });
}

export function useDirectory() {
  const q = useQuery({
    queryKey: qk.directory,
    queryFn: () => api.get<DirectoryUser[]>("/users/directory"),
    staleTime: 5 * 60_000,
  });
  const byId = useMemo(() => new Map((q.data ?? []).map((u) => [u.id, u])), [q.data]);
  return { ...q, users: q.data ?? [], byId };
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    const fields = e.details?.fields as Record<string, string> | undefined;
    if (fields) return `${e.message}: ${Object.values(fields).join("; ")}`;
    return e.message;
  }
  return e instanceof Error ? e.message : String(e);
}

export function notifyError(e: unknown, title = "Could not save") {
  notifications.show({ color: "red", title, message: errorMessage(e) });
}

/**
 * Run a command; on success invalidate the given query prefixes.
 * Errors are shown as a toast unless `silent` is set.
 */
export function useCommand<N extends CommandName>(
  name: N,
  opts: { invalidate?: (readonly unknown[])[]; silent?: boolean; success?: string } = {},
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CommandBody<N>) => command(name, body),
    onSuccess: () => {
      for (const key of opts.invalidate ?? []) qc.invalidateQueries({ queryKey: key });
      if (opts.success) notifications.show({ color: "teal", message: opts.success });
    },
    onError: (e) => {
      if (!opts.silent) notifyError(e);
    },
  });
}
