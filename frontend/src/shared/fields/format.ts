import dayjs from "dayjs";
import type { ColumnSpec, ItemRow } from "../api/types";

export const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
]; // prettier-ignore

export function fmtDate(v: string | null | undefined): string {
  return v ? dayjs(v).format("DD/MM/YYYY") : "";
}

export function fmtDateTime(v: string | null | undefined): string {
  return v ? dayjs(v).format("DD/MM/YYYY HH:mm") : "";
}

export function fmtMoney(v: number | null | undefined): string {
  if (v === null || v === undefined) return "";
  return new Intl.NumberFormat("en-AU", {
    style: "currency",
    currency: "AUD",
    maximumFractionDigits: 2,
  }).format(v);
}

export function fmtYearMonth(v: string | null | undefined): string {
  if (!v) return "";
  const [y, m] = v.split("-");
  return `${MONTHS[Number(m) - 1]?.slice(0, 3)} ${y}`;
}

/** The value of a column on an item row, wherever it is stored. */
export function cellValue(row: ItemRow, col: ColumnSpec): any {
  switch (col.source) {
    case "core":
      return (row as any)[col.key];
    case "role":
      return row.roles?.[col.config.role] ?? [];
    case "mirror":
      return row.mirrors?.[col.key];
    default:
      return row.data?.[col.key];
  }
}

/** Effective type used for display (mirrors render as their display_type). */
export function displayType(col: ColumnSpec): string {
  return col.type === "mirror" ? (col.config.display_type ?? "text") : col.type;
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

/** Return a copy of `row` with `value` written where `col` lives (optimistic updates). */
export function applyValue(row: ItemRow, col: ColumnSpec, value: any): ItemRow {
  switch (col.source) {
    case "core":
      return { ...row, [col.key]: value };
    case "role":
      return { ...row, roles: { ...row.roles, [col.config.role]: value ?? [] } };
    case "data": {
      const data = { ...row.data };
      if (value === null || value === undefined || (Array.isArray(value) && !value.length))
        delete data[col.key];
      else data[col.key] = value;
      return { ...row, data };
    }
    default:
      return row;
  }
}

/** Mantine Select data grouped by a `group` key ({group, items} format). */
export function grouped(options: { value: string; label: string; group?: string | null }[]) {
  const out: { group: string; items: { value: string; label: string }[] }[] = [];
  for (const o of options) {
    const g = o.group ?? "";
    let bucket = out.find((b) => b.group === g);
    if (!bucket) out.push((bucket = { group: g, items: [] }));
    bucket.items.push({ value: o.value, label: o.label });
  }
  return out;
}
