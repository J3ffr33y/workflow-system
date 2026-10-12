import {
  Button,
  Checkbox,
  CloseButton,
  Group,
  Modal,
  ScrollArea,
  SegmentedControl,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useDisclosure } from "@mantine/hooks";
import { modals } from "@mantine/modals";
import {
  IconArchive,
  IconArrowForward,
  IconCopy,
  IconPencil,
  IconSubtask,
  IconTrash,
} from "@tabler/icons-react";
import dayjs from "dayjs";
import { useState } from "react";
import { useCommand } from "../../shared/api/hooks";
import type { ColumnSpec, ItemRow } from "../../shared/api/types";
import { FieldInput } from "../../shared/fields/FieldInput";
import { grouped } from "../../shared/fields/format";
import type { FieldCtx } from "../../shared/workspace";
import classes from "./board.module.css";

interface Props {
  selected: ItemRow[];
  ctx: FieldCtx;
  boardId: string;
  onClear: () => void;
}

export function BulkBar({ selected, ctx, boardId, onClear }: Props) {
  const ids = selected.map((r) => r.id);
  const inv = { invalidate: [["items"]] as unknown[][] };
  const archive = useCommand("items.archive", { ...inv, success: `Archived ${ids.length} item(s)` });
  const del = useCommand("items.delete", { ...inv, success: `Moved ${ids.length} item(s) to the trash` });
  const [edit, editH] = useDisclosure();
  const [move, moveH] = useDisclosure();
  const [roll, rollH] = useDisclosure();
  const [task, taskH] = useDisclosure();
  const can = ctx.can;

  return (
    <div className={classes.bulk} role="region" aria-label="Bulk actions">
      <Text size="sm" fw={600}>
        {ids.length} selected
      </Text>
      <Group gap={6}>
        {can("items.update") && (
          <Button
            size="compact-sm"
            variant="white"
            leftSection={<IconPencil size={14} />}
            onClick={editH.open}
          >
            Edit field
          </Button>
        )}
        {can("tasks.write") && (
          <Button
            size="compact-sm"
            variant="white"
            leftSection={<IconSubtask size={14} />}
            onClick={taskH.open}
          >
            Add task
          </Button>
        )}
        {can("items.update") && (
          <Button
            size="compact-sm"
            variant="white"
            leftSection={<IconArrowForward size={14} />}
            onClick={moveH.open}
          >
            Move
          </Button>
        )}
        {can("items.rollover") && (
          <Button size="compact-sm" variant="white" leftSection={<IconCopy size={14} />} onClick={rollH.open}>
            Roll over
          </Button>
        )}
        {can("items.archive") && (
          <Button
            size="compact-sm"
            variant="white"
            leftSection={<IconArchive size={14} />}
            onClick={() =>
              modals.openConfirmModal({
                title: `Archive ${ids.length} item(s)?`,
                children: <Text size="sm">They leave this board and can be restored from Archived.</Text>,
                labels: { confirm: "Archive", cancel: "Cancel" },
                onConfirm: () => archive.mutate({ item_ids: ids }, { onSuccess: onClear }),
              })
            }
          >
            Archive
          </Button>
        )}
        {can("items.delete") && (
          <Button
            size="compact-sm"
            variant="white"
            color="red"
            leftSection={<IconTrash size={14} />}
            onClick={() =>
              modals.openConfirmModal({
                title: `Delete ${ids.length} item(s)?`,
                children: (
                  <Text size="sm">
                    The items and their tasks move to the trash. An administrator can restore them from
                    Activity.
                  </Text>
                ),
                labels: { confirm: "Delete", cancel: "Cancel" },
                confirmProps: { color: "red" },
                onConfirm: () => del.mutate({ item_ids: ids }, { onSuccess: onClear }),
              })
            }
          >
            Delete
          </Button>
        )}
      </Group>
      <CloseButton onClick={onClear} aria-label="Clear selection" variant="transparent" c="white" />
      <BulkEditModal opened={edit} onClose={editH.close} ids={ids} ctx={ctx} boardId={boardId} />
      <MoveModal opened={move} onClose={moveH.close} ids={ids} ctx={ctx} onDone={onClear} />
      <RolloverModal opened={roll} onClose={rollH.close} rows={selected} ctx={ctx} onDone={onClear} />
      <AddTaskModal opened={task} onClose={taskH.close} ids={ids} />
    </div>
  );
}

function BulkEditModal({
  opened,
  onClose,
  ids,
  ctx,
  boardId,
}: {
  opened: boolean;
  onClose: () => void;
  ids: string[];
  ctx: FieldCtx;
  boardId: string;
}) {
  const editable = ctx.schema.columns.filter(
    (c) => c.editable && c.source !== "mirror" && c.key !== "name" && c.type !== "period_grid",
  );
  const [key, setKey] = useState<string | null>(null);
  const [value, setValue] = useState<any>(null);
  const [mode, setMode] = useState<"set" | "add" | "remove">("set");
  const col = editable.find((c) => c.key === key);
  const run = useCommand("items.bulk_update_field", { invalidate: [["items"]] });
  const submit = async () => {
    const res = await run.mutateAsync({ item_ids: ids, field: key!, value, mode });
    const failed = Object.keys(res.result.failed ?? {}).length;
    modals.closeAll();
    onClose();
    if (failed) {
      modals.open({
        title: `${res.result.updated} updated, ${failed} skipped`,
        children: <Text size="sm">{Object.values(res.result.failed).join("; ")}</Text>,
      });
    }
  };
  return (
    <Modal opened={opened} onClose={onClose} title={`Edit ${ids.length} item(s)`}>
      <Stack>
        <Select
          label="Field"
          searchable
          data={grouped(editable.map((c) => ({ value: c.key, label: c.label, group: c.group ?? "Fields" })))}
          value={key}
          onChange={(k) => {
            setKey(k);
            setValue(null);
            setMode("set");
          }}
        />
        {col && col.kind === "multi" && (
          <SegmentedControl
            value={mode}
            onChange={(m) => setMode(m as any)}
            data={[
              { value: "add", label: "Add" },
              { value: "remove", label: "Remove" },
              { value: "set", label: "Replace" },
            ]}
          />
        )}
        {col && (
          <FieldInput
            col={col}
            ctx={ctx}
            value={value}
            onChange={setValue}
            label="New value"
            boardId={boardId}
          />
        )}
        <Button onClick={submit} disabled={!col} loading={run.isPending}>
          Apply to {ids.length} item(s)
        </Button>
      </Stack>
    </Modal>
  );
}

function MoveModal({
  opened,
  onClose,
  ids,
  ctx,
  onDone,
}: {
  opened: boolean;
  onClose: () => void;
  ids: string[];
  ctx: FieldCtx;
  onDone: () => void;
}) {
  const [board, setBoard] = useState<string | null>(null);
  const run = useCommand("items.move", { invalidate: [["items"]], success: "Moved" });
  return (
    <Modal opened={opened} onClose={onClose} title={`Move ${ids.length} item(s)`}>
      <Stack>
        <Select
          label="To board"
          data={ctx.schema.boards.filter((b) => !b.archived).map((b) => ({ value: b.id, label: b.name }))}
          value={board}
          onChange={setBoard}
        />
        <Text size="xs" c="dimmed">
          Statuses that the target board does not use are reset to its default status.
        </Text>
        <Button
          disabled={!board}
          loading={run.isPending}
          onClick={() =>
            run.mutate({ item_ids: ids, board_id: board! }, { onSuccess: () => (onClose(), onDone()) })
          }
        >
          Move
        </Button>
      </Stack>
    </Modal>
  );
}

function AddTaskModal({ opened, onClose, ids }: { opened: boolean; onClose: () => void; ids: string[] }) {
  const [title, setTitle] = useState("");
  const [due, setDue] = useState<Date | null>(null);
  const run = useCommand("tasks.create_for_items", {
    invalidate: [["items"], ["tasks"]],
    success: "Tasks added",
  });
  return (
    <Modal opened={opened} onClose={onClose} title={`Add a task to ${ids.length} item(s)`}>
      <Stack>
        <TextInput
          label="Task"
          value={title}
          onChange={(e) => setTitle(e.currentTarget.value)}
          data-autofocus
        />
        <DateInput label="Due date" clearable valueFormat="DD/MM/YYYY" value={due} onChange={setDue} />
        <Button
          disabled={!title.trim()}
          loading={run.isPending}
          onClick={() =>
            run.mutate(
              { item_ids: ids, title, due_date: due ? dayjs(due).format("YYYY-MM-DD") : null },
              { onSuccess: () => (setTitle(""), onClose()) },
            )
          }
        >
          Add task
        </Button>
      </Stack>
    </Modal>
  );
}

type Action = "carry" | "clear" | "set" | "add_year";

function RolloverModal({
  opened,
  onClose,
  rows,
  ctx,
  onDone,
}: {
  opened: boolean;
  onClose: () => void;
  rows: ItemRow[];
  ctx: FieldCtx;
  onDone: () => void;
}) {
  const fields = ctx.schema.columns.filter(
    (c) =>
      c.editable &&
      !["name", "client", "board"].includes(c.key) &&
      c.source !== "mirror" &&
      !(c.source === "core" && c.hidden_by_default),
  );
  const [target, setTarget] = useState<string | null>(null);
  const [actions, setActions] = useState<Record<string, Action>>({});
  const [values, setValues] = useState<Record<string, any>>({});
  const [suffix, setSuffix] = useState("");
  const [archiveSource, setArchiveSource] = useState(false);
  const run = useCommand("items.rollover", { invalidate: [["items"]] });

  const defaultTarget =
    ctx.schema.workspace.settings?.rollover?.default_target === "next_period"
      ? "Next year's board"
      : "Same board";
  const actionOf = (c: ColumnSpec): Action => actions[c.key] ?? c.rollover;
  const supportsYear = (c: ColumnSpec) => ["date", "year_month", "fiscal_year"].includes(c.type);

  const submit = async () => {
    const field_actions: Record<string, { action: Action; value?: any }> = {};
    for (const c of fields) {
      const a = actionOf(c);
      if (a === "set" || a !== (c.rollover as Action))
        field_actions[c.key] = { action: a, value: a === "set" ? values[c.key] : undefined };
    }
    const res = await run.mutateAsync({
      item_ids: rows.map((r) => r.id),
      target_board_id: target,
      field_actions: field_actions as any,
      name_suffix: suffix || null,
      archive_source_items: archiveSource,
    });
    const failed = Object.keys(res.result.failed ?? {}).length;
    modals.open({
      title: "Roll over finished",
      children: (
        <Text size="sm">
          Created {res.result.created.length} item(s).
          {failed ? ` ${failed} could not be copied: ${Object.values(res.result.failed).join("; ")}` : ""}
        </Text>
      ),
    });
    onClose();
    onDone();
  };

  return (
    <Modal opened={opened} onClose={onClose} title={`Roll over ${rows.length} item(s)`} size="xl">
      <Stack>
        <Group grow align="flex-end">
          <Select
            label="Target board"
            placeholder={defaultTarget}
            clearable
            data={ctx.schema.boards.filter((b) => !b.archived).map((b) => ({ value: b.id, label: b.name }))}
            value={target}
            onChange={setTarget}
          />
          <TextInput
            label="Name suffix (optional)"
            placeholder="Defaults to the new board or fiscal year"
            value={suffix}
            onChange={(e) => setSuffix(e.currentTarget.value)}
          />
        </Group>
        <Text size="sm" c="dimmed">
          Client and company are always copied, the name gets the new period, and status starts at the board's
          default. Choose what happens to every other field.
        </Text>
        <ScrollArea h={340} offsetScrollbars>
          <Table verticalSpacing={4} striped>
            <Table.Tbody>
              {fields.map((c) => (
                <Table.Tr key={c.key}>
                  <Table.Td w={200}>
                    <Text size="sm">{c.label}</Text>
                  </Table.Td>
                  <Table.Td w={300}>
                    <SegmentedControl
                      size="xs"
                      value={actionOf(c)}
                      onChange={(a) => setActions({ ...actions, [c.key]: a as Action })}
                      data={[
                        { value: "carry", label: "Copy" },
                        { value: "clear", label: "Clear" },
                        { value: "set", label: "Set" },
                        ...(supportsYear(c) ? [{ value: "add_year", label: "+1 year" }] : []),
                      ]}
                    />
                  </Table.Td>
                  <Table.Td>
                    {actionOf(c) === "set" && (
                      <FieldInput
                        col={c}
                        ctx={ctx}
                        size="xs"
                        value={values[c.key] ?? null}
                        onChange={(v) => setValues({ ...values, [c.key]: v })}
                      />
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea>
        <Checkbox
          label="Archive the original items after copying"
          checked={archiveSource}
          onChange={(e) => setArchiveSource(e.currentTarget.checked)}
        />
        <Group justify="flex-end">
          <Button onClick={submit} loading={run.isPending}>
            Roll over {rows.length} item(s)
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
