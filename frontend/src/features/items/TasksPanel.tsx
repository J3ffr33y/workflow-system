import { ActionIcon, Button, Group, Menu, Paper, Select, Stack, Text, TextInput } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { modals } from "@mantine/modals";
import { IconCornerDownRight, IconPlus, IconTrash } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import { api } from "../../shared/api/client";
import { useCommand } from "../../shared/api/hooks";
import type { ItemRow, Task } from "../../shared/api/types";
import { People } from "../../shared/fields/Display";
import { StatusPill } from "../../shared/ui/StatusPill";
import type { FieldCtx } from "../../shared/workspace";

export function TasksPanel({ item, ctx }: { item: ItemRow; ctx: FieldCtx }) {
  const key = ["tasks", item.id];
  const q = useQuery({ queryKey: key, queryFn: () => api.get<Task[]>(`/items/${item.id}/tasks`) });
  const inv = { invalidate: [key, ["items"], ["item", item.id]] };
  const create = useCommand("tasks.create", inv);
  const update = useCommand("tasks.update", inv);
  const del = useCommand("tasks.delete", inv);
  const [title, setTitle] = useState("");
  const [parent, setParent] = useState<string | null>(null);
  const canWrite = ctx.can("tasks.write") && !item.is_archived;
  const tasks = q.data ?? [];
  const roots = tasks.filter((t) => !t.parent_task_id);
  const children = (id: string) => tasks.filter((t) => t.parent_task_id === id);

  const add = () =>
    create.mutate(
      { item_id: item.id, title, parent_task_id: parent },
      { onSuccess: () => (setTitle(""), setParent(null)) },
    );

  const TaskRow = ({ t, depth }: { t: Task; depth: number }) => (
    <>
      <Paper withBorder p={8} ml={depth * 24} radius="sm">
        <Group wrap="nowrap" gap="sm">
          {depth > 0 && <IconCornerDownRight size={14} color="var(--ink-soft)" />}
          <Menu shadow="md" withinPortal disabled={!canWrite}>
            <Menu.Target>
              <div
                style={{
                  width: 130,
                  height: 26,
                  borderRadius: 4,
                  overflow: "hidden",
                  cursor: canWrite ? "pointer" : undefined,
                }}
              >
                <StatusPill status={ctx.taskStatuses.get(t.status ?? "")} fill />
              </div>
            </Menu.Target>
            <Menu.Dropdown>
              {ctx.schema.task_statuses.map((s) => (
                <Menu.Item key={s.key} onClick={() => update.mutate({ task_id: t.id, status: s.key })}>
                  {s.label}
                </Menu.Item>
              ))}
            </Menu.Dropdown>
          </Menu>
          <Text
            size="sm"
            style={{ flex: 1 }}
            td={ctx.taskStatuses.get(t.status ?? "")?.category === "done" ? "line-through" : undefined}
          >
            {t.title}
          </Text>
          <People ids={Object.values(t.members).flat()} ctx={ctx} compact />
          <DateInput
            size="xs"
            w={120}
            clearable
            placeholder="Due"
            valueFormat="DD/MM/YYYY"
            disabled={!canWrite}
            value={t.due_date ? dayjs(t.due_date).toDate() : null}
            onChange={(d) =>
              update.mutate({ task_id: t.id, due_date: d ? dayjs(d).format("YYYY-MM-DD") : null })
            }
          />
          <Select
            size="xs"
            w={150}
            placeholder="Assignee"
            clearable
            searchable
            disabled={!canWrite}
            data={ctx.userList.map((u) => ({ value: u.id, label: u.full_name }))}
            value={t.members.assigned?.[0] ?? null}
            onChange={(v) => update.mutate({ task_id: t.id, members: { assigned: v ? [v] : [] } })}
            comboboxProps={{ withinPortal: true }}
          />
          {canWrite && (
            <ActionIcon
              variant="subtle"
              color="gray"
              aria-label="Add subtask"
              onClick={() => setParent(t.id)}
            >
              <IconPlus size={14} />
            </ActionIcon>
          )}
          {canWrite && (
            <ActionIcon
              variant="subtle"
              color="red"
              aria-label="Delete task"
              onClick={() =>
                modals.openConfirmModal({
                  title: `Delete “${t.title}”?`,
                  children: children(t.id).length ? (
                    <Text size="sm">Its subtasks are deleted too.</Text>
                  ) : undefined,
                  labels: { confirm: "Delete", cancel: "Cancel" },
                  confirmProps: { color: "red" },
                  onConfirm: () => del.mutate({ task_id: t.id, include_subtasks: true }),
                })
              }
            >
              <IconTrash size={14} />
            </ActionIcon>
          )}
        </Group>
      </Paper>
      {children(t.id).map((c) => (
        <TaskRow key={c.id} t={c} depth={depth + 1} />
      ))}
    </>
  );

  return (
    <Stack gap="xs">
      {canWrite && (
        <Group gap="xs" wrap="nowrap">
          <TextInput
            style={{ flex: 1 }}
            placeholder={parent ? `Subtask of “${tasks.find((t) => t.id === parent)?.title}”` : "Add a task"}
            value={title}
            onChange={(e) => setTitle(e.currentTarget.value)}
            onKeyDown={(e) => e.key === "Enter" && title.trim() && add()}
          />
          {parent && (
            <Button variant="subtle" color="gray" onClick={() => setParent(null)}>
              Not a subtask
            </Button>
          )}
          <Button onClick={add} disabled={!title.trim()} loading={create.isPending}>
            Add
          </Button>
        </Group>
      )}
      {!tasks.length && !q.isLoading && (
        <Text size="sm" c="dimmed">
          No tasks yet.
        </Text>
      )}
      {roots.map((t) => (
        <TaskRow key={t.id} t={t} depth={0} />
      ))}
    </Stack>
  );
}
