/**
 * Controlled input for any field type. Used by grid cell editors, the item
 * drawer, bulk edit, automation actions and migration value maps.
 */
import {
  Checkbox,
  Group,
  MultiSelect,
  NumberInput,
  Select,
  Text,
  TextInput,
  Textarea,
  UnstyledButton,
} from "@mantine/core";
import { DateInput, MonthPickerInput } from "@mantine/dates";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import { api } from "../api/client";
import type { ColumnSpec } from "../api/types";
import type { FieldCtx } from "../workspace";
import { optionOf } from "./Display";
import { MONTHS } from "./format";
import classes from "./fields.module.css";

export interface FieldInputProps {
  col: ColumnSpec;
  type?: string;
  value: any;
  onChange: (v: any) => void;
  ctx: FieldCtx;
  clientId?: string | null;
  boardId?: string;
  autoFocus?: boolean;
  label?: string;
  onEnter?: () => void;
  size?: "xs" | "sm";
}

function userOptions(ctx: FieldCtx) {
  return ctx.userList.map((u) => ({
    value: u.id,
    label: u.is_placeholder ? `${u.full_name} (no login)` : u.full_name,
  }));
}

function lookupOptions(ctx: FieldCtx, list: string) {
  const l = ctx.schema.lookups.find((x) => x.key === list);
  return (l?.values ?? []).filter((v) => v.is_active).map((v) => ({ value: v.id, label: v.label }));
}

export function allowedStatuses(ctx: FieldCtx, boardId?: string) {
  const board = ctx.schema.boards.find((b) => b.id === boardId);
  const allowed = board?.settings?.statuses;
  return ctx.schema.statuses.filter((s) => !s.is_archived && (!allowed?.length || allowed.includes(s.key)));
}

export function ClientSelect({
  value,
  onChange,
  label,
  autoFocus,
  size,
}: {
  value: string | null;
  onChange: (v: string | null) => void;
  label?: string;
  autoFocus?: boolean;
  size?: "xs" | "sm";
}) {
  const [search, setSearch] = useState("");
  const q = useQuery({
    queryKey: ["clients-pick", search],
    queryFn: () => api.get<{ rows: { id: string; name: string }[] }>("/clients", { search, limit: 30 }),
    staleTime: 30_000,
  });
  const current = useQuery({
    queryKey: ["client", value],
    queryFn: () => api.get<{ id: string; name: string }>(`/clients/${value}`),
    enabled: !!value,
    staleTime: 60_000,
  });
  const data = [...(q.data?.rows ?? []).map((c) => ({ value: c.id, label: c.name }))];
  if (value && current.data && !data.some((d) => d.value === value))
    data.unshift({ value, label: current.data.name });
  return (
    <Select
      label={label}
      size={size}
      searchable
      clearable
      autoFocus={autoFocus}
      data={data}
      value={value}
      onChange={onChange}
      searchValue={search}
      onSearchChange={setSearch}
      filter={({ options }) => options}
      nothingFoundMessage={q.isFetching ? "Searching…" : "No client matches"}
      placeholder="Search clients"
      comboboxProps={{ withinPortal: true }}
    />
  );
}

export function EntitySelect({
  clientId,
  value,
  onChange,
  label,
  size,
}: {
  clientId?: string | null;
  value: string | null;
  onChange: (v: string | null) => void;
  label?: string;
  size?: "xs" | "sm";
}) {
  const q = useQuery({
    queryKey: ["entities", clientId],
    queryFn: () =>
      api.get<{ id: string; name: string; entity_type: string }[]>(`/clients/${clientId}/entities`),
    enabled: !!clientId,
  });
  return (
    <Select
      label={label}
      size={size}
      clearable
      disabled={!clientId}
      placeholder={clientId ? "Choose entity" : "Choose a client first"}
      data={(q.data ?? []).map((e) => ({ value: e.id, label: `${e.name} (${e.entity_type})` }))}
      value={value}
      onChange={onChange}
      comboboxProps={{ withinPortal: true }}
    />
  );
}

export function FieldInput(p: FieldInputProps) {
  const { col, value, onChange, ctx, autoFocus, label, size = "sm" } = p;
  const type = p.type ?? col.type;
  const enter = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey && p.onEnter) {
      e.preventDefault();
      p.onEnter();
    }
  };
  const common = { label, size, autoFocus, comboboxProps: { withinPortal: true } } as const;
  switch (type) {
    case "text":
    case "email":
    case "phone":
    case "url":
      return (
        <TextInput
          label={label}
          size={size}
          autoFocus={autoFocus}
          value={value ?? ""}
          onChange={(e) => onChange(e.currentTarget.value)}
          onKeyDown={enter}
          type={type === "email" ? "email" : type === "url" ? "url" : "text"}
        />
      );
    case "long_text":
      return (
        <Textarea
          label={label}
          size={size}
          autoFocus={autoFocus}
          autosize
          minRows={3}
          maxRows={12}
          value={value ?? ""}
          onChange={(e) => onChange(e.currentTarget.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && p.onEnter) p.onEnter();
          }}
        />
      );
    case "number":
    case "money":
    case "percent":
      return (
        <NumberInput
          label={label}
          size={size}
          autoFocus={autoFocus}
          value={value ?? ""}
          onChange={(v) => onChange(v === "" ? null : v)}
          onKeyDown={enter}
          prefix={type === "money" ? "$" : undefined}
          suffix={type === "percent" ? "%" : undefined}
          thousandSeparator={type === "money" ? "," : undefined}
          decimalScale={type === "money" ? 2 : undefined}
        />
      );
    case "date":
      return (
        <DateInput
          label={label}
          size={size}
          autoFocus={autoFocus}
          clearable
          valueFormat="DD/MM/YYYY"
          value={value ? dayjs(value).toDate() : null}
          onChange={(d) => onChange(d ? dayjs(d).format("YYYY-MM-DD") : null)}
          popoverProps={{ withinPortal: true }}
          placeholder="dd/mm/yyyy"
        />
      );
    case "year_month":
      return (
        <MonthPickerInput
          label={label}
          size={size}
          clearable
          value={value ? dayjs(`${value}-01`).toDate() : null}
          onChange={(d) => onChange(d ? dayjs(d).format("YYYY-MM") : null)}
          popoverProps={{ withinPortal: true }}
        />
      );
    case "month":
      return (
        <Select
          {...common}
          clearable
          data={MONTHS.map((m, i) => ({ value: String(i + 1), label: m }))}
          value={value ? String(value) : null}
          onChange={(v) => onChange(v ? Number(v) : null)}
        />
      );
    case "checkbox":
      return <Checkbox label={label} checked={!!value} onChange={(e) => onChange(e.currentTarget.checked)} />;
    case "select":
      return (
        <Select
          {...common}
          clearable
          searchable
          data={(col.config.options ?? []).map((o: any) => ({ value: o.key, label: o.label }))}
          value={value ?? null}
          onChange={onChange}
        />
      );
    case "multi_select":
      return (
        <MultiSelect
          {...common}
          searchable
          clearable
          data={(col.config.options ?? []).map((o: any) => ({ value: o.key, label: o.label }))}
          value={value ?? []}
          onChange={onChange}
        />
      );
    case "status":
      return (
        <Select
          {...common}
          data={allowedStatuses(ctx, p.boardId).map((s) => ({ value: s.key, label: s.label }))}
          value={value ?? null}
          onChange={onChange}
        />
      );
    case "fiscal_year":
      return (
        <Select
          {...common}
          clearable
          data={ctx.schema.fiscal_years.map((f) => ({ value: f.id, label: f.label }))}
          value={value ?? null}
          onChange={onChange}
        />
      );
    case "lookup":
      return (
        <Select
          {...common}
          clearable
          searchable
          data={lookupOptions(ctx, col.config.list)}
          value={value ?? null}
          onChange={onChange}
        />
      );
    case "lookup_multi":
      return (
        <MultiSelect
          {...common}
          clearable
          searchable
          data={lookupOptions(ctx, col.config.list)}
          value={value ?? []}
          onChange={onChange}
        />
      );
    case "user":
      return (
        <Select
          {...common}
          clearable
          searchable
          data={userOptions(ctx)}
          value={value ?? null}
          onChange={onChange}
        />
      );
    case "users":
      return (
        <MultiSelect
          {...common}
          clearable
          searchable
          data={userOptions(ctx)}
          value={value ?? []}
          onChange={onChange}
          maxValues={col.config.allow_multiple === false ? 1 : undefined}
        />
      );
    case "client":
      return (
        <ClientSelect
          label={label}
          size={size}
          autoFocus={autoFocus}
          value={value ?? null}
          onChange={onChange}
        />
      );
    case "client_entity":
      return (
        <EntitySelect
          label={label}
          size={size}
          clientId={p.clientId}
          value={value ?? null}
          onChange={onChange}
        />
      );
    case "period_grid":
      return <PeriodGridInput col={col} value={value ?? {}} onChange={onChange} label={label} />;
    default:
      return (
        <Text size="sm" c="dimmed">
          Not editable
        </Text>
      );
  }
}

function PeriodGridInput({
  col,
  value,
  onChange,
  label,
}: {
  col: ColumnSpec;
  value: Record<string, string>;
  onChange: (v: Record<string, string>) => void;
  label?: string;
}) {
  const options: { key: string; label: string; color: string }[] = col.config.options ?? [];
  const cycle = (period: number) => {
    const cur = value[String(period)];
    const idx = options.findIndex((o) => o.key === cur);
    const next = idx + 1 >= options.length ? undefined : options[idx + 1];
    const out = { ...value };
    if (next) out[String(period)] = next.key;
    else delete out[String(period)];
    onChange(out);
  };
  return (
    <div>
      {label && (
        <Text size="sm" fw={500} mb={4}>
          {label}
        </Text>
      )}
      <div className={classes.periods} style={{ gap: 4 }}>
        {Array.from({ length: col.config.periods ?? 12 }, (_, i) => {
          const o = optionOf(col, value[String(i + 1)]);
          return (
            <UnstyledButton
              key={i}
              onClick={() => cycle(i + 1)}
              title={`Period ${i + 1}: ${o?.label ?? "not set"} (click to change)`}
              className={classes.period}
              style={{ height: 26, background: o ? `var(--mantine-color-${o.color}-5)` : undefined }}
            >
              <Text size="10px" ta="center" c={o ? "white" : "dimmed"}>
                {i + 1}
              </Text>
            </UnstyledButton>
          );
        })}
      </div>
      <Group gap={10} mt={6}>
        {options.map((o) => (
          <Group key={o.key} gap={4}>
            <span
              className={classes.period}
              style={{ width: 10, height: 10, background: `var(--mantine-color-${o.color}-5)` }}
            />
            <Text size="xs">{o.label}</Text>
          </Group>
        ))}
      </Group>
    </div>
  );
}
