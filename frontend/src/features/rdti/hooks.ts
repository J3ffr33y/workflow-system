import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../../shared/api/client";
import type { Passage, Report, RuleElement, Workbench } from "./types";

export const rk = {
  all: (item: string) => ["rdti", item] as const,
  workbench: (item: string) => ["rdti", item, "workbench"] as const,
  report: (item: string) => ["rdti", item, "report"] as const,
  passages: (item: string, params: Record<string, unknown>) => ["rdti", item, "passages", params] as const,
};

export function useWorkbench(itemId: string | undefined) {
  return useQuery({
    queryKey: rk.workbench(itemId ?? ""),
    queryFn: () => api.get<Workbench>(`/rdti/items/${itemId}`),
    enabled: !!itemId,
  });
}

export function useReport(itemId: string) {
  return useQuery({
    queryKey: rk.report(itemId),
    queryFn: () => api.get<Report>(`/rdti/items/${itemId}/report`),
  });
}

export function usePassages(itemId: string, params: Record<string, unknown>, enabled = true) {
  return useQuery({
    queryKey: rk.passages(itemId, params),
    queryFn: () => api.get<Passage[]>(`/rdti/items/${itemId}/passages`, params),
    enabled,
  });
}

/** Everything on the workbench derives from the same few tables: refresh it all. */
export function useRefreshRdti(itemId: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: rk.all(itemId) });
}

export function useElementLabel() {
  const { i18n } = useTranslation();
  return (el: RuleElement | undefined, fallback: string) =>
    !el ? fallback : i18n.language.startsWith("zh") ? el.label_zh : el.label;
}

export function fileUrl(fileId: string, page?: number | null) {
  return `/api/rdti/files/${fileId}/content${page ? `#page=${page}` : ""}`;
}
