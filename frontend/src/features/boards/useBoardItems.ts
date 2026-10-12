import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { api, command } from "../../shared/api/client";
import { notifyError } from "../../shared/api/hooks";
import type { FilterGroup, ItemRow } from "../../shared/api/types";
import { ApiError } from "../../shared/api/client";
import { notifications } from "@mantine/notifications";

export interface ItemsQuery {
  workspaceId: string;
  boardIds?: string[];
  archived?: boolean;
  filter?: FilterGroup | null;
  search?: string | null;
  clientId?: string;
}

const PAGE = 500;

export function itemsKey(q: ItemsQuery) {
  return [
    "items",
    q.workspaceId,
    q.boardIds ?? null,
    !!q.archived,
    q.filter ?? null,
    q.search ?? "",
    q.clientId ?? null,
  ];
}

/** Loads every matching row (in pages); sorting happens in the grid. */
export function useBoardItems(q: ItemsQuery, enabled = true) {
  return useQuery({
    queryKey: itemsKey(q),
    enabled: enabled && !!q.workspaceId,
    placeholderData: (prev) => prev,
    queryFn: async () => {
      const rows: ItemRow[] = [];
      let total = 0;
      do {
        const page = await api.post<{ total: number; rows: ItemRow[] }>("/items/query", {
          workspace_id: q.workspaceId,
          board_ids: q.boardIds,
          archived: !!q.archived,
          filter: q.filter && q.filter.rules.length ? q.filter : null,
          search: q.search || null,
          client_id: q.clientId,
          offset: rows.length,
          limit: PAGE,
        });
        total = page.total;
        rows.push(...page.rows);
        if (!page.rows.length) break;
      } while (rows.length < total);
      return rows;
    },
  });
}

/**
 * Optimistic single-field update with conflict detection: the value the user
 * saw is sent as `expected`; if someone else changed it first, the server
 * answers 409, we roll back and show who-changed-what instead of overwriting.
 */
export function useUpdateField() {
  const qc = useQueryClient();
  return useCallback(
    async (row: ItemRow, field: string, value: any, expected: any, patch: (r: ItemRow) => ItemRow) => {
      const snapshots = qc.getQueriesData<ItemRow[]>({ queryKey: ["items"] });
      for (const [key, data] of snapshots) {
        if (data)
          qc.setQueryData(
            key,
            data.map((r) => (r.id === row.id ? patch(r) : r)),
          );
      }
      try {
        await command("items.update_field", {
          item_id: row.id,
          field,
          value,
          expected,
          check_expected: true,
        });
        qc.invalidateQueries({ queryKey: ["item", row.id] });
      } catch (e) {
        for (const [key, data] of snapshots) qc.setQueryData(key, data);
        if (e instanceof ApiError && e.code === "stale_value") {
          notifications.show({
            color: "orange",
            title: "Changed by someone else",
            message: `${e.message}. The latest value is now shown; please try again if needed.`,
          });
        } else {
          notifyError(e);
        }
        qc.invalidateQueries({ queryKey: ["items"] });
      }
    },
    [qc],
  );
}
