import {
  ActionIcon,
  Button,
  Divider,
  Group,
  Modal,
  MultiSelect,
  NumberInput,
  Paper,
  SegmentedControl,
  Select,
  Stack,
  Switch,
  Text,
  TextInput,
} from "@mantine/core";
import { IconPlus, IconTrash } from "@tabler/icons-react";
import { useState } from "react";
import { useCommand } from "../../shared/api/hooks";
import type { FilterGroup } from "../../shared/api/types";
import { FieldInput } from "../../shared/fields/FieldInput";
import type { FieldCtx } from "../../shared/workspace";
import { FilterBuilder } from "../boards/FilterBuilder";

export interface Rule {
  id?: string;
  name: string;
  description?: string | null;
  enabled: boolean;
  trigger: { type: string; config: Record<string, any> };
  conditions: FilterGroup | null;
  actions: { type: string; config: Record<string, any> }[];
  board_ids: string[];
}

const TRIGGERS = [
  { value: "status_changed", label: "Status changes to…" },
  { value: "field_changed", label: "A field changes" },
  { value: "item_created", label: "An item is created" },
  { value: "date_reached", label: "A date arrives / is approaching" },
];
const ACTIONS = [
  { value: "set_status", label: "Set status" },
  { value: "advance_date", label: "Push a date forward" },
  { value: "set_field", label: "Set a field" },
  { value: "clear_field", label: "Clear a field" },
  { value: "notify_roles", label: "Notify people in a role" },
  { value: "notify_users", label: "Notify specific people" },
  { value: "create_task", label: "Create a task" },
  { value: "highlight", label: "Highlight the row" },
  { value: "clear_highlight", label: "Clear row highlight" },
  { value: "archive", label: "Archive the item" },
];
const UNITS = [
  { value: "d", label: "days" },
  { value: "w", label: "weeks" },
  { value: "m", label: "months" },
  { value: "q", label: "quarters" },
  { value: "y", label: "years" },
];
const COLORS = ["red", "orange", "yellow", "green", "blue"].map((c) => ({
  value: c,
  label: c[0].toUpperCase() + c.slice(1),
}));

export function RuleEditor({ rule, ctx, onClose }: { rule: Rule; ctx: FieldCtx; onClose: () => void }) {
  const [r, setR] = useState<Rule>(rule);
  const save = useCommand("automations.save_rule", { invalidate: [["rules"]], success: "Rule saved" });
  const cols = ctx.schema.columns;
  const editable = cols.filter((c) => c.editable && c.source !== "mirror");
  const dateCols = cols.filter((c) => c.kind === "date");
  const statuses = ctx.schema.statuses.map((s) => ({ value: s.key, label: s.label }));
  const tc = r.trigger.config;
  const setTrigger = (config: Record<string, any>) =>
    setR({ ...r, trigger: { ...r.trigger, config: { ...tc, ...config } } });
  const setAction = (i: number, a: Rule["actions"][number]) =>
    setR({ ...r, actions: r.actions.map((x, j) => (j === i ? a : x)) });

  const submit = () =>
    save.mutate(
      {
        rule_id: r.id ?? null,
        workspace_id: ctx.schema.workspace.id,
        name: r.name,
        description: r.description ?? null,
        enabled: r.enabled,
        trigger: r.trigger,
        conditions: r.conditions?.rules.length ? (r.conditions as unknown as Record<string, unknown>) : null,
        actions: r.actions,
        board_ids: r.board_ids,
      },
      { onSuccess: onClose },
    );

  return (
    <Modal opened onClose={onClose} title={r.id ? "Edit automation" : "New automation"} size="xl">
      <Stack>
        <Group grow align="flex-end">
          <TextInput
            label="Name"
            value={r.name}
            onChange={(e) => setR({ ...r, name: e.currentTarget.value })}
            data-autofocus
          />
          <MultiSelect
            label="Boards"
            placeholder="All boards"
            data={ctx.schema.boards.filter((b) => !b.archived).map((b) => ({ value: b.id, label: b.name }))}
            value={r.board_ids}
            onChange={(v) => setR({ ...r, board_ids: v })}
          />
        </Group>

        <Paper withBorder p="sm">
          <Text fw={600} size="sm" mb="xs">
            When
          </Text>
          <Stack gap="xs">
            <Select
              data={TRIGGERS}
              value={r.trigger.type}
              onChange={(t) => setR({ ...r, trigger: { type: t ?? "status_changed", config: {} } })}
            />
            {r.trigger.type === "status_changed" && (
              <MultiSelect
                label="Status becomes"
                data={statuses}
                value={tc.to ?? []}
                onChange={(to) => setTrigger({ to })}
              />
            )}
            {r.trigger.type === "field_changed" && (
              <Group grow>
                <Select
                  label="Field"
                  searchable
                  data={cols.map((c) => ({ value: c.key, label: c.label }))}
                  value={tc.field ?? null}
                  onChange={(field) => setTrigger({ field, to: [] })}
                />
              </Group>
            )}
            {r.trigger.type === "date_reached" && (
              <Group align="flex-end" wrap="wrap">
                <Select
                  label="Date field"
                  data={dateCols.map((c) => ({ value: c.key, label: c.label }))}
                  value={tc.field ?? null}
                  onChange={(field) => setTrigger({ field })}
                  w={200}
                />
                <NumberInput
                  label="Offset"
                  min={0}
                  w={90}
                  value={tc.offset?.amount ?? 0}
                  onChange={(v) =>
                    setTrigger({
                      offset: {
                        ...(tc.offset ?? { unit: "d", direction: "before" }),
                        amount: Number(v) || 0,
                      },
                    })
                  }
                />
                <Select
                  data={UNITS}
                  w={110}
                  value={tc.offset?.unit ?? "d"}
                  onChange={(unit) =>
                    setTrigger({ offset: { ...(tc.offset ?? { amount: 0, direction: "before" }), unit } })
                  }
                />
                <SegmentedControl
                  data={[
                    { value: "before", label: "before" },
                    { value: "after", label: "after" },
                  ]}
                  value={tc.offset?.direction ?? "before"}
                  onChange={(direction) =>
                    setTrigger({ offset: { ...(tc.offset ?? { amount: 0, unit: "d" }), direction } })
                  }
                />
                <Select
                  label="Fire"
                  w={220}
                  data={[
                    { value: "on_or_after", label: "on that day or any later day" },
                    { value: "on", label: "only on that exact day" },
                  ]}
                  value={tc.mode ?? "on_or_after"}
                  onChange={(mode) => setTrigger({ mode })}
                />
              </Group>
            )}
            {r.trigger.type === "date_reached" && (
              <Text size="xs" c="dimmed">
                Checked every hour. Fires once per item for each date value; moving the date later re-arms the
                rule.
              </Text>
            )}
          </Stack>
        </Paper>

        <Paper withBorder p="sm">
          <FilterBuilder
            title="Only if"
            value={r.conditions ?? { op: "and", rules: [] }}
            onChange={(conditions) => setR({ ...r, conditions })}
            columns={cols}
            ctx={ctx}
          />
        </Paper>

        <Paper withBorder p="sm">
          <Text fw={600} size="sm" mb="xs">
            Then
          </Text>
          <Stack gap="xs">
            {r.actions.map((a, i) => (
              <Group key={i} align="flex-end" wrap="wrap" gap="xs">
                <Select
                  w={210}
                  data={ACTIONS}
                  value={a.type}
                  onChange={(t) => setAction(i, { type: t ?? "set_status", config: {} })}
                />
                {a.type === "set_status" && (
                  <Select
                    w={220}
                    data={statuses}
                    value={a.config.status ?? null}
                    onChange={(status) => setAction(i, { ...a, config: { status } })}
                  />
                )}
                {(a.type === "set_field" || a.type === "clear_field") && (
                  <Select
                    w={200}
                    searchable
                    data={editable
                      .filter((c) => c.key !== "name")
                      .map((c) => ({ value: c.key, label: c.label }))}
                    value={a.config.field ?? null}
                    onChange={(field) => setAction(i, { ...a, config: { field } })}
                  />
                )}
                {a.type === "set_field" && a.config.field && ctx.columns.get(a.config.field) && (
                  <div style={{ minWidth: 220 }}>
                    <FieldInput
                      col={ctx.columns.get(a.config.field)!}
                      ctx={ctx}
                      value={a.config.value ?? null}
                      onChange={(value) => setAction(i, { ...a, config: { ...a.config, value } })}
                    />
                  </div>
                )}
                {a.type === "advance_date" && (
                  <>
                    <Select
                      w={200}
                      data={cols
                        .filter((c) => ["date", "month", "year_month"].includes(c.type))
                        .map((c) => ({ value: c.key, label: c.label }))}
                      value={a.config.field ?? null}
                      onChange={(field) =>
                        setAction(i, { ...a, config: { ...a.config, field, by: a.config.by ?? "frequency" } })
                      }
                    />
                    <SegmentedControl
                      data={[
                        { value: "frequency", label: "by frequency" },
                        { value: "fixed", label: "fixed" },
                      ]}
                      value={a.config.by === "frequency" || !a.config.by ? "frequency" : "fixed"}
                      onChange={(v) =>
                        setAction(i, {
                          ...a,
                          config: {
                            ...a.config,
                            by: v === "frequency" ? "frequency" : { amount: 1, unit: "m" },
                          },
                        })
                      }
                    />
                    {typeof a.config.by === "object" && (
                      <>
                        <NumberInput
                          w={80}
                          min={1}
                          value={a.config.by.amount}
                          onChange={(v) =>
                            setAction(i, {
                              ...a,
                              config: { ...a.config, by: { ...a.config.by, amount: Number(v) || 1 } },
                            })
                          }
                        />
                        <Select
                          w={110}
                          data={UNITS}
                          value={a.config.by.unit}
                          onChange={(unit) =>
                            setAction(i, { ...a, config: { ...a.config, by: { ...a.config.by, unit } } })
                          }
                        />
                      </>
                    )}
                  </>
                )}
                {a.type === "notify_roles" && (
                  <>
                    <MultiSelect
                      w={240}
                      data={ctx.schema.roles.map((x) => ({ value: x.key, label: x.label }))}
                      value={a.config.roles ?? []}
                      onChange={(roles) => setAction(i, { ...a, config: { ...a.config, roles } })}
                    />
                    <TextInput
                      w={260}
                      placeholder="Message (optional)"
                      value={a.config.message ?? ""}
                      onChange={(e) =>
                        setAction(i, { ...a, config: { ...a.config, message: e.currentTarget.value } })
                      }
                    />
                  </>
                )}
                {a.type === "notify_users" && (
                  <>
                    <MultiSelect
                      w={240}
                      searchable
                      data={ctx.userList.map((u) => ({ value: u.id, label: u.full_name }))}
                      value={a.config.user_ids ?? []}
                      onChange={(user_ids) => setAction(i, { ...a, config: { ...a.config, user_ids } })}
                    />
                    <TextInput
                      w={260}
                      placeholder="Message (optional)"
                      value={a.config.message ?? ""}
                      onChange={(e) =>
                        setAction(i, { ...a, config: { ...a.config, message: e.currentTarget.value } })
                      }
                    />
                  </>
                )}
                {a.type === "highlight" && (
                  <Select
                    w={140}
                    data={COLORS}
                    value={a.config.color ?? "yellow"}
                    onChange={(color) => setAction(i, { ...a, config: { color } })}
                  />
                )}
                {a.type === "create_task" && (
                  <>
                    <TextInput
                      w={240}
                      placeholder="Task title"
                      value={a.config.title ?? ""}
                      onChange={(e) =>
                        setAction(i, { ...a, config: { ...a.config, title: e.currentTarget.value } })
                      }
                    />
                    <NumberInput
                      w={140}
                      placeholder="Due in days"
                      value={a.config.due_in_days ?? ""}
                      onChange={(v) =>
                        setAction(i, {
                          ...a,
                          config: { ...a.config, due_in_days: v === "" ? null : Number(v) },
                        })
                      }
                    />
                  </>
                )}
                <ActionIcon
                  variant="subtle"
                  color="gray"
                  aria-label="Remove action"
                  onClick={() => setR({ ...r, actions: r.actions.filter((_, j) => j !== i) })}
                  mb={4}
                >
                  <IconTrash size={15} />
                </ActionIcon>
              </Group>
            ))}
            <Button
              size="compact-sm"
              variant="light"
              leftSection={<IconPlus size={14} />}
              w="fit-content"
              onClick={() => setR({ ...r, actions: [...r.actions, { type: "set_status", config: {} }] })}
            >
              Add action
            </Button>
          </Stack>
        </Paper>
        <Divider />
        <Group justify="space-between">
          <Switch
            label="Enabled"
            checked={r.enabled}
            onChange={(e) => setR({ ...r, enabled: e.currentTarget.checked })}
          />
          <Button onClick={submit} loading={save.isPending} disabled={!r.name.trim() || !r.actions.length}>
            Save rule
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
