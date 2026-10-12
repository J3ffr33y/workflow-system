import { useSyncExternalStore } from "react";

/**
 * Which grid cell is being edited. A tiny external store so that opening an
 * editor re-renders exactly two cells, not the whole grid.
 */
type Cell = { rowId: string; colKey: string } | null;

let current: Cell = null;
const listeners = new Set<() => void>();

export const editStore = {
  get: () => current,
  set(cell: Cell) {
    current = cell;
    listeners.forEach((l) => l());
  },
  subscribe(l: () => void) {
    listeners.add(l);
    return () => listeners.delete(l);
  },
};

export function useIsEditing(rowId: string, colKey: string): boolean {
  return useSyncExternalStore(
    editStore.subscribe,
    () => current?.rowId === rowId && current?.colKey === colKey,
  );
}
