import { Badge, Button, Group, Stack, Text, Timeline } from "@mantine/core";
import { IconArrowBackUp } from "@tabler/icons-react";
import dayjs from "dayjs";
import { useCommand } from "../../shared/api/hooks";
import type { AuditEntry } from "../../shared/api/types";
import { fmtDate } from "../../shared/fields/format";
import type { FieldCtx } from "../../shared/workspace";

const OP_LABEL: Record<string, string> = { create: "created", update: "changed", delete: "deleted" };
const ENTITY_LABEL: Record<string, string> = {
  item: "item",
  item_member: "team",
  task: "task",
  task_member: "task team",
  client: "client",
  client_entity: "entity",
  contact: "contact",
  comment: "update",
  board: "board",
  automation_rule: "automation",
};

function fieldLabel(field: string, ctx?: FieldCtx) {
  const key = field.startsWith("data.") ? field.slice(5) : field;
  const alias: Record<string, string> = {
    client_id: "client",
    entity_id: "entity",
    board_id: "board",
    fiscal_year_id: "fiscal_year",
  };
  return ctx?.columns.get(alias[key] ?? key)?.label ?? key.replace(/_/g, " ");
}

function fmt(v: any, field: string, ctx?: FieldCtx): string {
  if (v === null || v === undefined || v === "") return "empty";
  const key = field.replace(/^data\./, "");
  if (key === "status") return ctx?.statuses.get(v)?.label ?? String(v);
  if (key === "user_id") return ctx?.users.get(v)?.full_name ?? String(v);
  if (key === "board_id") return ctx?.boards.get(v) ?? String(v);
  if (key === "fiscal_year_id") return ctx?.fiscalYears.get(v) ?? String(v);
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v)) return fmtDate(v);
  if (Array.isArray(v))
    return v.map((x) => ctx?.users.get(x)?.full_name ?? ctx?.lookupValues.get(x) ?? x).join(", ");
  if (typeof v === "object") return JSON.stringify(v);
  const col = ctx?.columns.get(key);
  const opt = col?.config?.options?.find((o: any) => o.key === v);
  if (opt) return opt.label;
  if (col?.type === "lookup") return ctx?.lookupValues.get(v) ?? String(v);
  return String(v);
}

const HIDDEN_FIELDS = new Set([
  "id",
  "workspace_id",
  "item_id",
  "task_id",
  "position",
  "deleted_at",
  "archived_at",
  "highlight_rule_id",
  "rolled_from_id",
]);

export function ActivityList({
  entries,
  ctx,
  ctxFor,
  showEntity = false,
  canRevert = false,
}: {
  entries: AuditEntry[];
  ctx?: FieldCtx;
  /** Per-workspace lookups when entries span product lines. */
  ctxFor?: (workspaceId: string | null) => FieldCtx | undefined;
  showEntity?: boolean;
  canRevert?: boolean;
}) {
  const revert = useCommand("activity.revert", {
    invalidate: [["activity"], ["items"], ["item"]],
    success: "Change undone",
  });
  if (!entries.length) {
    return (
      <Text size="sm" c="dimmed">
        No recorded changes yet.
      </Text>
    );
  }
  return (
    <Timeline bulletSize={10} lineWidth={1}>
      {entries.map((e) => {
        const changes = e.changes.filter((c) => !HIDDEN_FIELDS.has(c.field));
        const ectx = ctxFor?.(e.workspace_id) ?? ctx;
        const revertible =
          canRevert &&
          !e.reverted &&
          ["item", "item_member", "task", "client", "client_entity", "contact"].includes(e.entity_type);
        return (
          <Timeline.Item
            key={e.id}
            title={
              <Group gap={6} wrap="nowrap" justify="space-between">
                <Text size="sm">
                  <b>{e.actor}</b> {OP_LABEL[e.op]} {ENTITY_LABEL[e.entity_type] ?? e.entity_type}
                  {showEntity && e.entity_name ? ` · ${e.entity_name}` : ""}
                </Text>
                {e.origin !== "ui" && (
                  <Badge size="xs" variant="light" color={e.origin === "automation" ? "grape" : "gray"}>
                    {e.origin}
                  </Badge>
                )}
              </Group>
            }
          >
            <Stack gap={2} mt={2}>
              {e.op === "update" &&
                changes.slice(0, 8).map((c) => (
                  <Text key={c.field} size="xs" c="dimmed">
                    {fieldLabel(c.field, ectx)}:{" "}
                    {c.hidden ? (
                      <i>value hidden</i>
                    ) : (
                      <>
                        <s>{fmt(c.before, c.field, ectx)}</s> → <b>{fmt(c.after, c.field, ectx)}</b>
                      </>
                    )}
                  </Text>
                ))}
              <Group gap="xs">
                <Text size="xs" c="dimmed">
                  {dayjs(e.created_at).format("DD/MM/YYYY HH:mm")}
                </Text>
                {e.reverted && (
                  <Badge size="xs" color="gray" variant="outline">
                    undone
                  </Badge>
                )}
                {revertible && (
                  <Button
                    size="compact-xs"
                    variant="subtle"
                    leftSection={<IconArrowBackUp size={12} />}
                    onClick={() => revert.mutate({ entry_ids: [e.id] })}
                  >
                    Undo
                  </Button>
                )}
                {revertible && e.batch_id && (
                  <Button
                    size="compact-xs"
                    variant="subtle"
                    color="gray"
                    onClick={() => revert.mutate({ batch_id: e.batch_id })}
                  >
                    Undo whole batch
                  </Button>
                )}
              </Group>
            </Stack>
          </Timeline.Item>
        );
      })}
    </Timeline>
  );
}
