import { ActionIcon, Badge, Group, Text, Tooltip } from "@mantine/core";
import { IconMessage, IconSubtask, IconArrowsMaximize } from "@tabler/icons-react";
import type { ColDef, ValueGetterParams } from "ag-grid-community";
import type { CustomCellRendererProps } from "ag-grid-react";
import type { ColumnSpec, ItemRow, ViewConfig } from "../../shared/api/types";
import { optionOf } from "../../shared/fields/Display";
import { cellValue, displayType } from "../../shared/fields/format";
import type { FieldCtx } from "../../shared/workspace";
import { EditableCell } from "./EditableCell";
import classes from "./board.module.css";

/** A comparable value for sorting: labels for references, positions for statuses. */
export function sortValue(row: ItemRow, col: ColumnSpec, ctx: FieldCtx): any {
  const v = cellValue(row, col);
  if (v === null || v === undefined) return null;
  switch (displayType(col)) {
    case "status":
      return ctx.statuses.get(v)?.position ?? 999;
    case "client":
      return row.client_name?.toLowerCase() ?? null;
    case "client_entity":
      return row.entity_name?.toLowerCase() ?? null;
    case "fiscal_year":
      return ctx.fiscalYears.get(v) ?? null;
    case "board":
      return ctx.boards.get(v) ?? null;
    case "select":
      return (col.config.options ?? []).findIndex((o: any) => o.key === v);
    case "lookup":
      return ctx.lookupValues.get(v)?.toLowerCase() ?? null;
    case "user":
      return ctx.users.get(v)?.full_name.toLowerCase() ?? null;
    case "users":
      return (
        (v as string[])
          .map((id) => ctx.users.get(id)?.full_name ?? "")
          .sort()[0]
          ?.toLowerCase() ?? null
      );
    case "multi_select":
      return (v as string[]).map((k) => optionOf(col, k)?.label ?? k).join(",");
    case "lookup_multi":
      return (v as string[]).map((id) => ctx.lookupValues.get(id) ?? "").join(",");
    case "period_grid":
      return Object.keys(v ?? {}).length;
    default:
      return typeof v === "string" ? v.toLowerCase() : v;
  }
}

function NameCell(props: CustomCellRendererProps<ItemRow> & { onOpen: (id: string) => void }) {
  const row = props.data;
  if (!row) return null;
  return (
    <Group gap={6} wrap="nowrap" className={classes.nameCell}>
      <Text size="sm" fw={500} truncate style={{ flex: 1 }}>
        {row.name}
      </Text>
      {row.open_task_count > 0 && (
        <Tooltip label={`${row.open_task_count} open of ${row.task_count} tasks`} withArrow>
          <Badge size="xs" variant="light" color="gray" leftSection={<IconSubtask size={10} />}>
            {row.open_task_count}
          </Badge>
        </Tooltip>
      )}
      {row.comment_count > 0 && (
        <Tooltip label={row.last_comment?.body.slice(0, 200)} multiline w={280} withArrow>
          <Badge size="xs" variant="light" color="teal" leftSection={<IconMessage size={10} />}>
            {row.comment_count}
          </Badge>
        </Tooltip>
      )}
      <ActionIcon
        size="sm"
        variant="subtle"
        className={classes.openBtn}
        aria-label={`Open ${row.name}`}
        onClick={(e) => {
          e.stopPropagation();
          props.onOpen(row.id);
        }}
      >
        <IconArrowsMaximize size={14} />
      </ActionIcon>
    </Group>
  );
}

const DEFAULT_WIDTH: Record<string, number> = {
  status: 190,
  name: 280,
  client: 220,
  long_text: 240,
  period_grid: 170,
  users: 160,
  date: 118,
  checkbox: 90,
  month: 110,
  money: 110,
};

export function buildColumnDefs(
  columns: ColumnSpec[],
  view: ViewConfig,
  ctx: FieldCtx,
  opts: { onOpen: (id: string) => void; pinnedLeft: string[]; boardFields?: string[] | null },
): ColDef<ItemRow>[] {
  const byKey = new Map(columns.map((c) => [c.key, c]));
  const enabled = (c: ColumnSpec) =>
    !opts.boardFields?.length || opts.boardFields.includes(c.key) || c.key === "name";
  const viewOrder = view.columns.map((c) => c.key).filter((k) => byKey.has(k));
  const rest = columns.filter((c) => !viewOrder.includes(c.key)).map((c) => c.key);
  const ordered = [...viewOrder, ...rest].map((k) => byKey.get(k)!).filter(enabled);
  const vc = new Map(view.columns.map((c) => [c.key, c]));

  return ordered.map((col): ColDef<ItemRow> => {
    const saved = vc.get(col.key);
    const hidden = saved ? !!saved.hidden : col.hidden_by_default;
    const pinned = saved?.pinned ?? (opts.pinnedLeft.includes(col.key) || col.key === "name" ? "left" : null);
    const sort = view.sort.find((s) => s.field === col.key);
    const base: ColDef<ItemRow> = {
      colId: col.key,
      headerName: col.label,
      headerTooltip: col.source === "mirror" ? `${col.label} (from the client record)` : col.label,
      hide: hidden,
      pinned,
      width: saved?.width ?? DEFAULT_WIDTH[col.key] ?? DEFAULT_WIDTH[displayType(col)] ?? 150,
      sortable: col.type !== "period_grid",
      sort: sort?.dir ?? null,
      resizable: true,
      valueGetter: (p: ValueGetterParams<ItemRow>) => (p.data ? sortValue(p.data, col, ctx) : null),
      comparator: (a, b) => (a === b ? 0 : a === null ? 1 : b === null ? -1 : a < b ? -1 : 1),
    };
    if (col.key === "name") {
      return {
        ...base,
        cellRenderer: NameCell,
        cellRendererParams: { onOpen: opts.onOpen },
        lockPinned: true,
      };
    }
    return {
      ...base,
      cellRenderer: EditableCell,
      cellRendererParams: { col },
      cellClass: col.type === "status" ? "cell-flush" : undefined,
    };
  });
}

/** Column layout + sort from the grid, in view-config form. */
export function readGridState(
  api: import("ag-grid-community").GridApi<ItemRow>,
): Pick<ViewConfig, "columns" | "sort"> {
  const state = api.getColumnState();
  return {
    columns: state.map((s) => ({
      key: s.colId,
      width: s.width ?? null,
      hidden: !!s.hide,
      pinned: (s.pinned as "left" | "right" | null) ?? null,
    })),
    sort: state
      .filter((s) => s.sort)
      .sort((a, b) => (a.sortIndex ?? 0) - (b.sortIndex ?? 0))
      .map((s) => ({ field: s.colId, dir: s.sort as "asc" | "desc" })),
  };
}
