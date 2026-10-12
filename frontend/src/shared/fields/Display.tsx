/**
 * Read-only rendering for every field type. Mirrors the backend field-type
 * registry: adding a type there means adding a case here and in Editor.tsx.
 */
import { Anchor, Avatar, Badge, Group, Text, Tooltip } from "@mantine/core";
import { IconCheck } from "@tabler/icons-react";
import dayjs from "dayjs";
import type { ReactNode } from "react";
import type { ColumnSpec, ItemRow } from "../api/types";
import { StatusPill } from "../ui/StatusPill";
import type { FieldCtx } from "../workspace";
import {
  MONTHS,
  cellValue,
  displayType,
  fmtDate,
  fmtDateTime,
  fmtMoney,
  fmtYearMonth,
  initials,
} from "./format";
import classes from "./fields.module.css";

export function optionOf(col: ColumnSpec, key: string) {
  return (col.config.options ?? []).find((o: any) => o.key === key);
}

function OptionBadge({ label, color }: { label: string; color?: string }) {
  return (
    <Badge variant="light" color={color ?? "gray"} radius="sm" size="sm" className={classes.badge}>
      {label}
    </Badge>
  );
}

export function People({ ids, ctx, compact = false }: { ids: string[]; ctx: FieldCtx; compact?: boolean }) {
  if (!ids?.length) return null;
  const users = ids.map((id) => ctx.users.get(id));
  if (compact || ids.length > 1) {
    return (
      <Tooltip label={users.map((u) => u?.full_name ?? "Unknown").join(", ")} withArrow openDelay={300}>
        <Group gap={4} wrap="nowrap">
          <Avatar.Group spacing={6}>
            {users.slice(0, 3).map((u, i) => (
              <Avatar key={ids[i]} size={22} radius="xl" color={u?.is_placeholder ? "gray" : "teal"}>
                {initials(u?.full_name ?? "?")}
              </Avatar>
            ))}
          </Avatar.Group>
          {ids.length === 1 || !compact ? (
            <Text size="sm" truncate>
              {users.length === 1 ? users[0]?.full_name : `${users[0]?.full_name} +${users.length - 1}`}
            </Text>
          ) : null}
        </Group>
      </Tooltip>
    );
  }
  return (
    <Group gap={6} wrap="nowrap">
      <Avatar size={22} radius="xl" color={users[0]?.is_placeholder ? "gray" : "teal"}>
        {initials(users[0]?.full_name ?? "?")}
      </Avatar>
      <Text size="sm" truncate>
        {users[0]?.full_name ?? "Unknown"}
      </Text>
    </Group>
  );
}

export function renderValue(
  type: string,
  value: any,
  col: ColumnSpec,
  ctx: FieldCtx,
  row?: ItemRow,
): ReactNode {
  if (value === null || value === undefined || value === "" || (Array.isArray(value) && !value.length)) {
    return type === "checkbox" ? null : null;
  }
  switch (type) {
    case "status":
      return <StatusPill status={ctx.statuses.get(value)} fill />;
    case "client":
      return <span className={classes.strong}>{row?.client_name ?? value}</span>;
    case "client_entity":
      return row?.entity_name ?? "";
    case "board":
      return ctx.boards.get(value) ?? "";
    case "fiscal_year":
      return ctx.fiscalYears.get(value) ?? "";
    case "date": {
      const overdue = col.key === "due_date" && dayjs(value).isBefore(dayjs(), "day");
      return <span className={overdue ? classes.overdue : undefined}>{fmtDate(value)}</span>;
    }
    case "datetime":
      return fmtDateTime(value);
    case "month":
      return MONTHS[Number(value) - 1] ?? "";
    case "year_month":
      return fmtYearMonth(value);
    case "money":
      return <span className={classes.num}>{fmtMoney(value)}</span>;
    case "number":
      return <span className={classes.num}>{value}</span>;
    case "percent":
      return <span className={classes.num}>{value}%</span>;
    case "checkbox":
      return value ? <IconCheck size={16} color="var(--accent)" aria-label="Yes" /> : null;
    case "select": {
      const o = optionOf(col, value);
      return <OptionBadge label={o?.label ?? value} color={o?.color} />;
    }
    case "multi_select":
      return (
        <Group gap={4} wrap="nowrap">
          {(value as string[]).map((k) => {
            const o = optionOf(col, k);
            return <OptionBadge key={k} label={o?.label ?? k} color={o?.color} />;
          })}
        </Group>
      );
    case "lookup":
      return <OptionBadge label={ctx.lookupValues.get(value) ?? "?"} />;
    case "lookup_multi":
      return (
        <Group gap={4} wrap="nowrap">
          {(value as string[]).map((id) => (
            <OptionBadge key={id} label={ctx.lookupValues.get(id) ?? "?"} />
          ))}
        </Group>
      );
    case "user":
      return <People ids={[value]} ctx={ctx} />;
    case "users":
      return <People ids={value} ctx={ctx} compact />;
    case "url":
      return (
        <Anchor href={value} target="_blank" rel="noreferrer" size="sm" onClick={(e) => e.stopPropagation()}>
          {value.replace(/^https?:\/\//, "").slice(0, 40)}
        </Anchor>
      );
    case "email":
      return (
        <Anchor href={`mailto:${value}`} size="sm" onClick={(e) => e.stopPropagation()}>
          {value}
        </Anchor>
      );
    case "period_grid":
      return <PeriodStrip value={value} col={col} />;
    case "long_text":
      return <span className={classes.clip}>{String(value).split("\n")[0]}</span>;
    default:
      return String(value);
  }
}

export function PeriodStrip({ value, col }: { value: Record<string, string>; col: ColumnSpec }) {
  const periods = col.config.periods ?? 12;
  return (
    <div className={classes.periods}>
      {Array.from({ length: periods }, (_, i) => {
        const o = optionOf(col, value?.[String(i + 1)]);
        return (
          <span
            key={i}
            className={classes.period}
            title={`${i + 1}: ${o?.label ?? "—"}`}
            style={{ background: o ? `var(--mantine-color-${o.color}-5)` : undefined }}
          />
        );
      })}
    </div>
  );
}

export function FieldDisplay({ col, row, ctx }: { col: ColumnSpec; row: ItemRow; ctx: FieldCtx }) {
  return <>{renderValue(displayType(col), cellValue(row, col), col, ctx, row)}</>;
}
