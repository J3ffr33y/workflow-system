import { Anchor, Group, SimpleGrid, Stack, Text } from "@mantine/core";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { ColumnSpec, ItemRow } from "../../shared/api/types";
import { renderValue } from "../../shared/fields/Display";
import { FieldInput } from "../../shared/fields/FieldInput";
import { applyValue, cellValue, displayType, fmtDate } from "../../shared/fields/format";
import type { FieldCtx } from "../../shared/workspace";
import { useUpdateField } from "../boards/useBoardItems";

const SAVE_ON_BLUR = new Set(["text", "long_text", "number", "money", "percent", "email", "phone", "url"]);

function FieldRow({
  col,
  row,
  ctx,
  onSaved,
}: {
  col: ColumnSpec;
  row: ItemRow;
  ctx: FieldCtx;
  onSaved: () => void;
}) {
  const update = useUpdateField();
  const value = cellValue(row, col);
  const [draft, setDraft] = useState<any>(value);
  useEffect(() => setDraft(value), [value]);
  const editable = ctx.can("items.update") && col.editable && col.source !== "mirror" && !row.is_archived;

  const save = async (v: any) => {
    if (JSON.stringify(v ?? null) === JSON.stringify(value ?? null)) return;
    await update(row, col.key, v, value ?? null, (r) => applyValue(r, col, v));
    onSaved();
  };

  if (!editable) {
    return (
      <div>
        <Text size="xs" c="dimmed" mb={2}>
          {col.label}
          {col.source === "mirror" && " (from client)"}
        </Text>
        <div style={{ minHeight: 28, display: "flex", alignItems: "center" }}>
          {renderValue(displayType(col), value, col, ctx, row) ?? (
            <Text size="sm" c="dimmed">
              —
            </Text>
          )}
        </div>
      </div>
    );
  }
  const blur = SAVE_ON_BLUR.has(col.type);
  return (
    <div onBlur={blur ? () => save(draft) : undefined}>
      <FieldInput
        col={col}
        ctx={ctx}
        label={col.label}
        value={draft}
        clientId={row.client}
        boardId={row.board_id}
        onChange={(v) => {
          setDraft(v);
          if (!blur) save(v);
        }}
        onEnter={col.type !== "long_text" ? () => save(draft) : undefined}
      />
    </div>
  );
}

export function DetailsPanel({ row, ctx, onSaved }: { row: ItemRow; ctx: FieldCtx; onSaved: () => void }) {
  const board = ctx.schema.boards.find((b) => b.id === row.board_id);
  const enabled = board?.settings?.fields;
  const cols = ctx.schema.columns.filter(
    (c) =>
      !["board", "created_at", "updated_at", "archive_source", "name"].includes(c.key) &&
      !(c.source === "core" && c.hidden_by_default) &&
      (!enabled?.length || enabled.includes(c.key)),
  );
  const groups = new Map<string, ColumnSpec[]>();
  for (const c of cols) {
    const g =
      c.source === "core"
        ? "General"
        : c.source === "role"
          ? "Team"
          : c.source === "mirror"
            ? "From the client record"
            : (c.group ?? "Details");
    groups.set(g, [...(groups.get(g) ?? []), c]);
  }
  const order = [
    "General",
    "Team",
    "Details",
    ...[...groups.keys()].filter(
      (g) => !["General", "Team", "Details", "From the client record"].includes(g),
    ),
    "From the client record",
  ];

  return (
    <Stack gap="lg">
      {row.client && (
        <Anchor component={Link} to={`/clients/${row.client}`} size="sm">
          Open client record
        </Anchor>
      )}
      {order
        .filter((g) => groups.has(g))
        .map((g) => (
          <section key={g}>
            <Text fw={600} size="sm" mb="xs">
              {g}
            </Text>
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md" verticalSpacing="sm">
              {groups.get(g)!.map((c) => (
                <div
                  key={c.key}
                  style={
                    c.type === "long_text" || c.type === "period_grid" ? { gridColumn: "1 / -1" } : undefined
                  }
                >
                  <FieldRow col={c} row={row} ctx={ctx} onSaved={onSaved} />
                </div>
              ))}
            </SimpleGrid>
            {g === "Team" && row.members?.length ? (
              <Group gap="md" mt={6}>
                {row.members.map((m) => (
                  <Text key={m.id} size="xs" c="dimmed">
                    {ctx.users.get(m.user_id)?.full_name} (
                    {ctx.schema.roles.find((r) => r.key === m.role_key)?.label}) since{" "}
                    {fmtDate(m.assigned_date)}
                  </Text>
                ))}
              </Group>
            ) : null}
          </section>
        ))}
      <Text size="xs" c="dimmed">
        Created {fmtDate(row.created_at)} · last changed {fmtDate(row.updated_at)}
        {row.rolled_from_id ? " · rolled over from a previous period" : ""}
        {row.is_archived ? ` · archived (${row.archive_source})` : ""}
      </Text>
    </Stack>
  );
}
