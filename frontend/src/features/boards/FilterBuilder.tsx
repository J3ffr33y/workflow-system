import {
  ActionIcon,
  Button,
  Group,
  MultiSelect,
  NumberInput,
  SegmentedControl,
  Select,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { IconPlus, IconTrash } from "@tabler/icons-react";
import type { ColumnSpec, FilterGroup, FilterRule } from "../../shared/api/types";
import { MONTHS, displayType } from "../../shared/fields/format";
import type { FieldCtx } from "../../shared/workspace";

const OPS: Record<string, [string, string][]> = {
  text: [["contains", "contains"], ["not_contains", "does not contain"], ["eq", "is"], ["neq", "is not"], ["starts_with", "starts with"], ["empty", "is empty"], ["not_empty", "is not empty"]],
  number: [["eq", "="], ["neq", "≠"], ["gt", ">"], ["gte", "≥"], ["lt", "<"], ["lte", "≤"], ["empty", "is empty"], ["not_empty", "is not empty"]],
  date: [["eq", "is on"], ["before", "is before"], ["after", "is after"], ["on_or_before", "on or before"], ["on_or_after", "on or after"], ["empty", "is empty"], ["not_empty", "is not empty"]],
  datetime: [["before", "is before"], ["after", "is after"], ["on_or_before", "on or before"], ["on_or_after", "on or after"], ["empty", "is empty"], ["not_empty", "is not empty"]],
  bool: [["is_true", "is checked"], ["is_false", "is not checked"]],
  ref: [["in", "is any of"], ["not_in", "is none of"], ["empty", "is empty"], ["not_empty", "is not empty"]],
  multi: [["has_any", "has any of"], ["has_all", "has all of"], ["has_none", "has none of"], ["empty", "is empty"], ["not_empty", "is not empty"]],
  json: [["empty", "is empty"], ["not_empty", "is not empty"]],
}; // prettier-ignore

const NO_VALUE = new Set(["empty", "not_empty", "is_true", "is_false"]);

const RELATIVE = [
  { value: "today", label: "Today" },
  { value: "today+7d", label: "In 7 days" },
  { value: "today+14d", label: "In 14 days" },
  { value: "today+1m", label: "In 1 month" },
  { value: "today-7d", label: "7 days ago" },
  { value: "today-1m", label: "1 month ago" },
];

export function optionsFor(
  col: ColumnSpec,
  ctx: FieldCtx,
  withMe = true,
): { value: string; label: string }[] {
  const type = displayType(col);
  switch (type) {
    case "status":
      return ctx.schema.statuses.map((s) => ({ value: s.key, label: s.label }));
    case "select":
    case "multi_select":
      return (col.config.options ?? []).map((o: any) => ({ value: o.key, label: o.label }));
    case "lookup":
    case "lookup_multi":
      return (ctx.schema.lookups.find((l) => l.key === col.config.list)?.values ?? []).map((v) => ({
        value: v.id,
        label: v.label,
      }));
    case "user":
    case "users":
      return [
        ...(withMe ? [{ value: "$me", label: "Me (whoever is viewing)" }] : []),
        ...ctx.userList.map((u) => ({ value: u.id, label: u.full_name })),
      ];
    case "fiscal_year":
      return ctx.schema.fiscal_years.map((f) => ({ value: f.id, label: f.label }));
    case "board":
      return ctx.schema.boards.map((b) => ({ value: b.id, label: b.name }));
    case "month":
      return MONTHS.map((m, i) => ({ value: String(i + 1), label: m }));
    default:
      return [];
  }
}

function RuleValue({
  rule,
  col,
  ctx,
  onChange,
}: {
  rule: FilterRule;
  col: ColumnSpec;
  ctx: FieldCtx;
  onChange: (v: any) => void;
}) {
  if (NO_VALUE.has(rule.operator)) return null;
  const kind = col.kind;
  if (kind === "ref" || kind === "multi" || col.type === "month") {
    const data = optionsFor(col, ctx);
    if (data.length) {
      return (
        <MultiSelect
          size="xs"
          searchable
          data={data}
          value={(Array.isArray(rule.value) ? rule.value : rule.value ? [rule.value] : []).map(String)}
          onChange={(v) => onChange(col.type === "month" ? v.map(Number) : v)}
          style={{ flex: 1, minWidth: 160 }}
          comboboxProps={{ withinPortal: true }}
        />
      );
    }
  }
  if (kind === "number") {
    return <NumberInput size="xs" value={rule.value ?? ""} onChange={onChange} style={{ width: 120 }} />;
  }
  if (kind === "date" || kind === "datetime") {
    return (
      <Select
        size="xs"
        searchable
        data={RELATIVE}
        value={rule.value ?? null}
        onChange={onChange}
        placeholder="YYYY-MM-DD or pick"
        style={{ width: 170 }}
        comboboxProps={{ withinPortal: true }}
        // Allow typing an exact date as well as picking a relative one.
        onSearchChange={(s) => /^\d{4}-\d{2}-\d{2}$/.test(s) && onChange(s)}
      />
    );
  }
  return (
    <TextInput
      size="xs"
      value={rule.value ?? ""}
      onChange={(e) => onChange(e.currentTarget.value)}
      style={{ flex: 1, minWidth: 140 }}
    />
  );
}

export function FilterBuilder({
  value,
  onChange,
  columns,
  ctx,
  title = "Show items where",
}: {
  title?: string;
  value: FilterGroup;
  onChange: (f: FilterGroup) => void;
  columns: ColumnSpec[];
  ctx: FieldCtx;
}) {
  const filterable = columns.filter((c) => c.kind !== "json" || c.type === "mirror");
  const byKey = new Map(filterable.map((c) => [c.key, c]));
  const rules = value.rules as FilterRule[];
  const set = (i: number, r: FilterRule) =>
    onChange({ ...value, rules: rules.map((x, j) => (j === i ? r : x)) });
  const add = () => {
    const first = filterable.find((c) => c.key === "status") ?? filterable[0];
    onChange({
      ...value,
      rules: [...rules, { field: first.key, operator: OPS[first.kind][0][0], value: null }],
    });
  };

  return (
    <Stack gap="xs" miw={520}>
      <Group justify="space-between">
        <Text size="sm" fw={600}>
          {title}
        </Text>
        {rules.length > 1 && (
          <SegmentedControl
            size="xs"
            value={value.op}
            onChange={(op) => onChange({ ...value, op: op as "and" | "or" })}
            data={[
              { value: "and", label: "all match" },
              { value: "or", label: "any matches" },
            ]}
          />
        )}
      </Group>
      {rules.length === 0 && (
        <Text size="sm" c="dimmed">
          {title === "Show items where"
            ? "No filters. Every item on the board is shown."
            : "No conditions: applies to every item."}
        </Text>
      )}
      {rules.map((r, i) => {
        const col = byKey.get(r.field) ?? filterable[0];
        return (
          <Group key={i} gap={6} wrap="nowrap" align="flex-start">
            <Select
              size="xs"
              searchable
              w={170}
              data={filterable.map((c) => ({ value: c.key, label: c.label }))}
              value={col.key}
              onChange={(k) => {
                const c = byKey.get(k ?? "")!;
                set(i, { field: c.key, operator: OPS[c.kind][0][0], value: null });
              }}
              comboboxProps={{ withinPortal: true }}
            />
            <Select
              size="xs"
              w={140}
              data={OPS[col.kind].map(([v, l]) => ({ value: v, label: l }))}
              value={r.operator}
              onChange={(op) => set(i, { ...r, operator: op ?? r.operator })}
              comboboxProps={{ withinPortal: true }}
            />
            <RuleValue rule={r} col={col} ctx={ctx} onChange={(v) => set(i, { ...r, value: v })} />
            <ActionIcon
              variant="subtle"
              color="gray"
              aria-label="Remove filter"
              onClick={() => onChange({ ...value, rules: rules.filter((_, j) => j !== i) })}
            >
              <IconTrash size={15} />
            </ActionIcon>
          </Group>
        );
      })}
      <Group>
        <Button size="compact-sm" variant="light" leftSection={<IconPlus size={14} />} onClick={add}>
          Add filter
        </Button>
        {rules.length > 0 && (
          <Button
            size="compact-sm"
            variant="subtle"
            color="gray"
            onClick={() => onChange({ op: "and", rules: [] })}
          >
            Clear all
          </Button>
        )}
      </Group>
    </Stack>
  );
}
