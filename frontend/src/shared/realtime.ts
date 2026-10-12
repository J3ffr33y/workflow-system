import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

/**
 * Listens to the server's change feed and refreshes affected queries, so
 * edits made by colleagues (or automations) appear without reloading.
 * Bursts are coalesced into one refresh per 400 ms.
 */
export function useRealtime(enabled: boolean) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!enabled || typeof EventSource === "undefined") return;
    const es = new EventSource("/api/realtime");
    let pending = new Set<string>();
    let timer: number | undefined;
    const flush = () => {
      const types = pending;
      pending = new Set();
      timer = undefined;
      const all = types.has("*");
      if (all || types.has("item") || types.has("item_member") || types.has("task") || types.has("comment")) {
        qc.invalidateQueries({ queryKey: ["items"] });
        qc.invalidateQueries({ queryKey: ["item"] });
        qc.invalidateQueries({ queryKey: ["home"] });
      }
      if (all || types.has("task") || types.has("task_member")) {
        qc.invalidateQueries({ queryKey: ["tasks"] });
        qc.invalidateQueries({ queryKey: ["home"] });
      }
      if (all || types.has("comment")) qc.invalidateQueries({ queryKey: ["comments"] });
      if (all || types.has("client") || types.has("client_entity") || types.has("contact"))
        qc.invalidateQueries({ queryKey: ["clients"] });
      if (
        all ||
        [...types].some((t) =>
          ["board", "field_definition", "status", "member_role", "lookup_value"].includes(t),
        )
      )
        qc.invalidateQueries({ queryKey: ["schema"] });
      qc.invalidateQueries({ queryKey: ["notifications"] });
    };
    es.addEventListener("change", (ev) => {
      try {
        const data = JSON.parse((ev as MessageEvent).data) as { types: string[] };
        data.types.forEach((t) => pending.add(t));
      } catch {
        pending.add("*");
      }
      if (timer === undefined) timer = window.setTimeout(flush, 400);
    });
    return () => {
      es.close();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [enabled, qc]);
}
