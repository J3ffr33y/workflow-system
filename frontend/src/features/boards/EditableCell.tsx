import { Button, Group, Popover, Stack, Text } from "@mantine/core";
import type { CustomCellRendererProps } from "ag-grid-react";
import { useEffect, useState } from "react";
import { command } from "../../shared/api/client";
import { notifyError } from "../../shared/api/hooks";
import type { ColumnSpec, ItemRow } from "../../shared/api/types";
import { renderValue } from "../../shared/fields/Display";
import { FieldInput, allowedStatuses } from "../../shared/fields/FieldInput";
import { applyValue, cellValue, displayType } from "../../shared/fields/format";
import { StatusMenu } from "../../shared/ui/StatusPill";
import type { FieldCtx } from "../../shared/workspace";
import { editStore, useIsEditing } from "./editStore";
import classes from "./board.module.css";

export interface CellContext {
  ctx: FieldCtx;
  canEdit: boolean;
  update: (
    row: ItemRow,
    field: string,
    value: any,
    expected: any,
    patch: (r: ItemRow) => ItemRow,
    sharedByClient?: boolean,
  ) => Promise<void>;
}

type Props = CustomCellRendererProps<ItemRow> & { col: ColumnSpec };

// Types whose editor is a list: picking a value saves immediately.
const INSTANT = new Set(["select", "lookup", "user", "month", "fiscal_year", "client", "client_entity"]);

export function EditableCell(props: Props) {
  const { col, data: row } = props;
  const cc = props.context as CellContext;
  const editing = useIsEditing(row?.id ?? "", col.key);
  if (!row) return null;
  const value = cellValue(row, col);
  const type = displayType(col);
  // Mirror columns (client facts such as ABN or State) are editable too: the
  // server writes them to the client, so every board and the client page agree.
  const editable = cc.canEdit && col.editable && !row.is_archived;

  if (col.type === "status") {
    return (
      <StatusMenu
        statuses={allowedStatuses(cc.ctx, row.board_id)}
        value={row.status}
        disabled={!editable}
        onChange={(v) => cc.update(row, "status", v, row.status, (r) => ({ ...r, status: v }))}
      />
    );
  }
  if (type === "checkbox" && editable) {
    return (
      <button
        type="button"
        className={classes.checkCell}
        aria-label={`${col.label}: ${value ? "yes" : "no"}`}
        onClick={() =>
          cc.update(
            row,
            col.key,
            !value,
            value ?? false,
            (r) => applyValue(r, col, !value),
            col.source === "mirror",
          )
        }
      >
        {renderValue(type, value, col, cc.ctx, row) ?? <span className={classes.checkEmpty} />}
      </button>
    );
  }

  const display = <div className={classes.cellInner}>{renderValue(type, value, col, cc.ctx, row)}</div>;
  if (!editable) return display;
  return (
    <Popover
      opened={editing}
      onChange={(o) => !o && editStore.set(null)}
      // Option lists and date pickers render in their own portal, outside this
      // dropdown; Mantine's own outside-click check closed the editor on mousedown
      // before the option click landed, so picking with the mouse never saved.
      closeOnClickOutside={false}
      position="bottom-start"
      offset={0}
      width={type === "long_text" ? 420 : type === "period_grid" ? 360 : 300}
      shadow="lg"
      withinPortal
      trapFocus
      returnFocus
    >
      <Popover.Target>{display}</Popover.Target>
      <Popover.Dropdown p="xs" onKeyDown={(e) => e.key === "Escape" && editStore.set(null)}>
        {editing && <CellEditor row={row} col={col} cc={cc} />}
      </Popover.Dropdown>
    </Popover>
  );
}

/** Close the cell editor on a click outside it and outside any Mantine portal
 * (option lists, date pickers) that the editor opened. */
function useCloseOnOutsideClick() {
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      const t = e.target as Element | null;
      if (t?.closest?.("[data-portal]")) return;
      editStore.set(null);
    };
    document.addEventListener("mousedown", onDown, true);
    return () => document.removeEventListener("mousedown", onDown, true);
  }, []);
}

function CellEditor({ row, col, cc }: { row: ItemRow; col: ColumnSpec; cc: CellContext }) {
  useCloseOnOutsideClick();
  const initial = cellValue(row, col);
  const [draft, setDraft] = useState<any>(initial);
  useEffect(() => setDraft(initial), [initial]);

  const save = (v: any = draft) => {
    editStore.set(null);
    if (JSON.stringify(v ?? null) === JSON.stringify(initial ?? null)) return;
    cc.update(row, col.key, v, initial ?? null, (r) => applyValue(r, col, v), col.source === "mirror");
  };

  if (col.type === "period_grid") {
    return (
      <FieldInput
        col={col}
        ctx={cc.ctx}
        value={draft ?? {}}
        label={col.label}
        onChange={async (next: Record<string, string>) => {
          const changed = Array.from({ length: col.config.periods ?? 12 }, (_, i) => String(i + 1)).find(
            (p) => (next[p] ?? null) !== ((draft ?? {})[p] ?? null),
          );
          setDraft(next);
          if (!changed) return;
          try {
            await command("items.set_period", {
              item_id: row.id,
              field: col.key,
              period: Number(changed),
              value: next[changed] ?? null,
            });
          } catch (e) {
            notifyError(e);
          }
        }}
      />
    );
  }

  const type = displayType(col);
  const instant = INSTANT.has(type);
  return (
    <Stack gap="xs">
      <FieldInput
        col={col}
        type={type}
        ctx={cc.ctx}
        value={draft}
        autoFocus
        clientId={row.client}
        boardId={row.board_id}
        onChange={(v) => (instant ? save(v) : setDraft(v))}
        onEnter={() => save()}
      />
      {!instant && (
        <Group justify="space-between">
          <Text size="xs" c="dimmed">
            {type === "long_text" ? "Ctrl+Enter to save" : "Enter to save, Esc to cancel"}
          </Text>
          <Button size="compact-sm" onClick={() => save()}>
            Save
          </Button>
        </Group>
      )}
    </Stack>
  );
}
