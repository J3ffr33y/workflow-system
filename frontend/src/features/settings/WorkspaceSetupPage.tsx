import {
  ActionIcon,
  Badge,
  Button,
  ColorSwatch,
  Group,
  Modal,
  Select,
  Stack,
  Switch,
  Table,
  Tabs,
  TagsInput,
  Text,
  TextInput,
} from "@mantine/core";
import { IconArrowDown, IconArrowUp, IconPencil } from "@tabler/icons-react";
import { useState } from "react";
import { useCommand } from "../../shared/api/hooks";
import type { FieldDefinition, StatusDef } from "../../shared/api/types";
import { Page } from "../../shared/ui/Page";
import { StatusPill } from "../../shared/ui/StatusPill";
import { useWorkspace } from "../../shared/workspace";

const FIELD_TYPES = [
  ["text", "Text"], ["long_text", "Long text"], ["number", "Number"], ["money", "Money"], ["percent", "Percent"],
  ["date", "Date"], ["month", "Month"], ["year_month", "Month & year"], ["checkbox", "Checkbox"],
  ["select", "Single select"], ["multi_select", "Multi select"], ["user", "Person"], ["users", "People"],
  ["lookup", "List value"], ["lookup_multi", "List values"], ["email", "Email"], ["phone", "Phone"], ["url", "Link"],
  ["period_grid", "Monthly grid"], ["mirror", "Show a client field"],
].map(([value, label]) => ({ value, label })); // prettier-ignore

const COLORS = [
  "gray",
  "dark",
  "red",
  "pink",
  "grape",
  "violet",
  "indigo",
  "blue",
  "cyan",
  "teal",
  "green",
  "lime",
  "yellow",
  "orange",
];
const CATEGORIES = [
  { value: "todo", label: "Not started" },
  { value: "active", label: "In progress" },
  { value: "waiting", label: "Waiting" },
  { value: "done", label: "Done" },
  { value: "cancelled", label: "Cancelled" },
];

export function WorkspaceSetupPage() {
  const { schema } = useWorkspace();
  if (!schema) return null;
  return (
    <Page
      title={`${schema.workspace.name} setup`}
      subtitle="Fields, statuses and team roles. Changes apply to every board in this product line immediately."
    >
      <Tabs defaultValue="fields">
        <Tabs.List mb="md">
          <Tabs.Tab value="fields">Fields</Tabs.Tab>
          <Tabs.Tab value="statuses">Statuses</Tabs.Tab>
          <Tabs.Tab value="roles">Team roles</Tabs.Tab>
          <Tabs.Tab value="boards">Boards</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="fields">
          <FieldsTab />
        </Tabs.Panel>
        <Tabs.Panel value="statuses">
          <StatusesTab scope="item" />
          <Text fw={600} mt="xl" mb="sm">
            Task statuses
          </Text>
          <StatusesTab scope="task" />
        </Tabs.Panel>
        <Tabs.Panel value="roles">
          <RolesTab />
        </Tabs.Panel>
        <Tabs.Panel value="boards">
          <BoardsTab />
        </Tabs.Panel>
      </Tabs>
    </Page>
  );
}

function FieldsTab() {
  const { schema } = useWorkspace();
  const [edit, setEdit] = useState<Partial<FieldDefinition> | null>(null);
  const inv = { invalidate: [["schema"]] };
  const create = useCommand("fields.create", { ...inv, success: "Field added" });
  const update = useCommand("fields.update", { ...inv, success: "Field saved" });
  const reorder = useCommand("fields.reorder", inv);
  if (!schema) return null;
  const defs = schema.field_definitions;
  const kinds: Record<string, string> = {
    item: "Item",
    client: "Client",
    task: "Task",
    entity: "Entity",
    contact: "Contact",
  };

  const move = (f: FieldDefinition, dir: -1 | 1) => {
    const same = defs.filter((d) => d.entity_kind === f.entity_kind);
    const i = same.findIndex((d) => d.id === f.id);
    const j = i + dir;
    if (j < 0 || j >= same.length) return;
    const ids = same.map((d) => d.id);
    [ids[i], ids[j]] = [ids[j], ids[i]];
    reorder.mutate({ workspace_id: schema.workspace.id, field_ids: ids });
  };

  const save = () => {
    if (!edit) return;
    const config = { ...(edit.config ?? {}) };
    if (edit.id) {
      update.mutate(
        {
          field_id: edit.id,
          label: edit.label,
          config,
          group: edit.group ?? null,
          rollover: edit.rollover as any,
          is_archived: edit.is_archived,
        },
        { onSuccess: () => setEdit(null) },
      );
    } else {
      create.mutate(
        {
          workspace_id: schema.workspace.id,
          label: edit.label!,
          type: edit.type!,
          entity_kind: (edit.entity_kind ?? "item") as any,
          config,
          group: edit.group ?? null,
          rollover: (edit.rollover ?? "carry") as any,
        },
        { onSuccess: () => setEdit(null) },
      );
    }
  };

  return (
    <Stack maw={1000}>
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          Built-in columns (name, client, status, dates, team roles) are always available. These are your own
          fields.
        </Text>
        <Button onClick={() => setEdit({ type: "text", entity_kind: "item", rollover: "carry", config: {} })}>
          Add field
        </Button>
      </Group>
      <Table withTableBorder style={{ background: "var(--surface)" }}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Field</Table.Th>
            <Table.Th>On</Table.Th>
            <Table.Th>Type</Table.Th>
            <Table.Th>Group</Table.Th>
            <Table.Th>On roll over</Table.Th>
            <Table.Th w={110} />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {defs.map((f) => (
            <Table.Tr key={f.id} style={{ opacity: f.is_archived ? 0.5 : 1 }}>
              <Table.Td>
                {f.label}
                <Text span size="xs" c="dimmed" ml={6}>
                  {f.key}
                </Text>
                {f.is_archived && (
                  <Badge size="xs" ml={6} color="gray">
                    hidden
                  </Badge>
                )}
              </Table.Td>
              <Table.Td>{kinds[f.entity_kind]}</Table.Td>
              <Table.Td>{FIELD_TYPES.find((t) => t.value === f.type)?.label ?? f.type}</Table.Td>
              <Table.Td>{f.group}</Table.Td>
              <Table.Td>
                {f.entity_kind === "item"
                  ? { carry: "Copy", clear: "Clear", add_year: "+1 year" }[f.rollover]
                  : ""}
              </Table.Td>
              <Table.Td>
                <Group gap={2}>
                  <ActionIcon variant="subtle" color="gray" aria-label="Move up" onClick={() => move(f, -1)}>
                    <IconArrowUp size={14} />
                  </ActionIcon>
                  <ActionIcon variant="subtle" color="gray" aria-label="Move down" onClick={() => move(f, 1)}>
                    <IconArrowDown size={14} />
                  </ActionIcon>
                  <ActionIcon
                    variant="subtle"
                    color="gray"
                    aria-label="Edit field"
                    onClick={() => setEdit(f)}
                  >
                    <IconPencil size={14} />
                  </ActionIcon>
                </Group>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <Modal
        opened={!!edit}
        onClose={() => setEdit(null)}
        title={edit?.id ? `Edit ${edit.label}` : "Add field"}
        size="lg"
      >
        {edit && (
          <Stack>
            <TextInput
              label="Label"
              value={edit.label ?? ""}
              onChange={(e) => setEdit({ ...edit, label: e.currentTarget.value })}
              data-autofocus
            />
            {!edit.id && (
              <Group grow>
                <Select
                  label="Type"
                  data={FIELD_TYPES}
                  value={edit.type}
                  onChange={(t) => setEdit({ ...edit, type: t ?? "text", config: {} })}
                />
                <Select
                  label="Belongs to"
                  data={[
                    { value: "item", label: "Items on boards" },
                    { value: "client", label: "Clients (shown on every board via a client field)" },
                  ]}
                  value={edit.entity_kind}
                  onChange={(k) => setEdit({ ...edit, entity_kind: k ?? "item" })}
                />
              </Group>
            )}
            {edit.id && (
              <Text size="xs" c="dimmed">
                The type and key of an existing field cannot change, because stored values, views and
                automations refer to them.
              </Text>
            )}
            {["select", "multi_select", "period_grid"].includes(edit.type ?? "") && (
              <TagsInput
                label="Options"
                description="Existing options cannot be removed once in use; you can rename them."
                value={(edit.config?.options ?? []).map((o: any) => o.label)}
                onChange={(labels) => {
                  const old = edit.config?.options ?? [];
                  setEdit({
                    ...edit,
                    config: {
                      ...edit.config,
                      options: labels.map((l) => old.find((o: any) => o.label === l) ?? { label: l }),
                    },
                  });
                }}
              />
            )}
            {["lookup", "lookup_multi"].includes(edit.type ?? "") && !edit.id && (
              <Select
                label="List"
                data={schema.lookups.map((l) => ({ value: l.key, label: l.label }))}
                value={edit.config?.list ?? null}
                onChange={(list) => setEdit({ ...edit, config: { list } })}
              />
            )}
            {edit.type === "mirror" && !edit.id && (
              <Group grow>
                <Select
                  label="Client field"
                  data={[
                    ...schema.field_definitions
                      .filter((f) => f.entity_kind === "client")
                      .map((f) => ({ value: `client|data.${f.key}|${f.type}`, label: `Client: ${f.label}` })),
                    { value: "entity|abn|text", label: "Entity: ABN" },
                    { value: "entity|entity_type|text", label: "Entity: type" },
                    { value: "contact|name|text", label: "Primary contact: name" },
                    { value: "contact|email|email", label: "Primary contact: email" },
                  ]}
                  onChange={(v) => {
                    if (!v) return;
                    const [of, field, display_type] = v.split("|");
                    setEdit({ ...edit, config: { of, field, display_type } });
                  }}
                />
              </Group>
            )}
            <Group grow>
              <TextInput
                label="Group (optional)"
                value={edit.group ?? ""}
                onChange={(e) => setEdit({ ...edit, group: e.currentTarget.value || null })}
              />
              {edit.entity_kind !== "client" && (
                <Select
                  label="When rolled over"
                  data={[
                    { value: "carry", label: "Copy the value" },
                    { value: "clear", label: "Leave empty" },
                    { value: "add_year", label: "Add one year (dates)" },
                  ]}
                  value={edit.rollover ?? "carry"}
                  onChange={(r) => setEdit({ ...edit, rollover: r ?? "carry" })}
                />
              )}
            </Group>
            {edit.id && (
              <Switch
                label="Hidden (keeps existing values)"
                checked={!!edit.is_archived}
                onChange={(e) => setEdit({ ...edit, is_archived: e.currentTarget.checked })}
              />
            )}
            <Group justify="flex-end">
              <Button
                onClick={save}
                disabled={!edit.label?.trim()}
                loading={create.isPending || update.isPending}
              >
                Save field
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </Stack>
  );
}

function StatusesTab({ scope }: { scope: "item" | "task" }) {
  const { schema } = useWorkspace();
  const [edit, setEdit] = useState<Partial<StatusDef> | null>(null);
  const inv = { invalidate: [["schema"]] };
  const upsert = useCommand("statuses.upsert", { ...inv, success: "Status saved" });
  const reorder = useCommand("statuses.reorder", inv);
  if (!schema) return null;
  const list = scope === "item" ? schema.statuses : schema.task_statuses;
  const move = (i: number, dir: -1 | 1) => {
    const keys = list.map((s) => s.key);
    const j = i + dir;
    if (j < 0 || j >= keys.length) return;
    [keys[i], keys[j]] = [keys[j], keys[i]];
    reorder.mutate({ workspace_id: schema.workspace.id, scope, keys });
  };
  return (
    <Stack maw={760}>
      <Group justify="flex-end">
        <Button variant="light" onClick={() => setEdit({ color: "gray", category: "active" })}>
          Add status
        </Button>
      </Group>
      <Table withTableBorder style={{ background: "var(--surface)" }}>
        <Table.Tbody>
          {list.map((s, i) => (
            <Table.Tr key={s.key} style={{ opacity: s.is_archived ? 0.5 : 1 }}>
              <Table.Td w={240}>
                <StatusPill status={s} />
              </Table.Td>
              <Table.Td>{CATEGORIES.find((c) => c.value === s.category)?.label}</Table.Td>
              <Table.Td>{s.is_default && <Badge size="sm">default</Badge>}</Table.Td>
              <Table.Td w={110}>
                <Group gap={2}>
                  <ActionIcon variant="subtle" color="gray" aria-label="Move up" onClick={() => move(i, -1)}>
                    <IconArrowUp size={14} />
                  </ActionIcon>
                  <ActionIcon variant="subtle" color="gray" aria-label="Move down" onClick={() => move(i, 1)}>
                    <IconArrowDown size={14} />
                  </ActionIcon>
                  <ActionIcon
                    variant="subtle"
                    color="gray"
                    aria-label="Edit status"
                    onClick={() => setEdit(s)}
                  >
                    <IconPencil size={14} />
                  </ActionIcon>
                </Group>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <Modal opened={!!edit} onClose={() => setEdit(null)} title={edit?.key ? "Edit status" : "Add status"}>
        {edit && (
          <Stack>
            <TextInput
              label="Label"
              value={edit.label ?? ""}
              onChange={(e) => setEdit({ ...edit, label: e.currentTarget.value })}
              data-autofocus
            />
            <div>
              <Text size="sm" fw={500} mb={4}>
                Colour
              </Text>
              <Group gap={6}>
                {COLORS.map((c) => (
                  <ColorSwatch
                    key={c}
                    component="button"
                    color={`var(--mantine-color-${c}-6)`}
                    onClick={() => setEdit({ ...edit, color: c })}
                    style={{
                      outline: edit.color === c ? "2px solid var(--ink)" : undefined,
                      outlineOffset: 2,
                      cursor: "pointer",
                    }}
                    aria-label={c}
                  />
                ))}
              </Group>
            </div>
            <Select
              label="Meaning"
              description="Lets reports and rules treat statuses alike across product lines."
              data={CATEGORIES}
              value={edit.category ?? "active"}
              onChange={(c) => setEdit({ ...edit, category: (c ?? "active") as any })}
            />
            <Switch
              label="Default for new items"
              checked={!!edit.is_default}
              onChange={(e) => setEdit({ ...edit, is_default: e.currentTarget.checked })}
            />
            {edit.key && (
              <Switch
                label="Hidden (existing items keep it)"
                checked={!!edit.is_archived}
                onChange={(e) => setEdit({ ...edit, is_archived: e.currentTarget.checked })}
              />
            )}
            <Button
              disabled={!edit.label?.trim()}
              loading={upsert.isPending}
              onClick={() =>
                upsert.mutate(
                  {
                    workspace_id: schema.workspace.id,
                    scope,
                    key: edit.key ?? null,
                    label: edit.label!,
                    color: edit.color ?? "gray",
                    category: edit.category ?? "active",
                    is_default: edit.is_default ?? null,
                    is_archived: edit.is_archived ?? null,
                  },
                  { onSuccess: () => setEdit(null) },
                )
              }
            >
              Save status
            </Button>
          </Stack>
        )}
      </Modal>
    </Stack>
  );
}

function RolesTab() {
  const { schema } = useWorkspace();
  const [label, setLabel] = useState("");
  const upsert = useCommand("member_roles.upsert", { invalidate: [["schema"]], success: "Role saved" });
  if (!schema) return null;
  return (
    <Stack maw={600}>
      <Text size="sm" c="dimmed">
        Roles people can have on an item. Each role becomes a column on the boards, and automations can notify
        a role.
      </Text>
      <Table withTableBorder style={{ background: "var(--surface)" }}>
        <Table.Tbody>
          {schema.roles.map((r) => (
            <Table.Tr key={r.key} style={{ opacity: r.is_archived ? 0.5 : 1 }}>
              <Table.Td>{r.label}</Table.Td>
              <Table.Td>{r.allow_multiple ? "Several people" : "One person"}</Table.Td>
              <Table.Td w={90}>
                <Switch
                  size="xs"
                  label="Active"
                  checked={!r.is_archived}
                  onChange={(e) =>
                    upsert.mutate({
                      workspace_id: schema.workspace.id,
                      key: r.key,
                      label: r.label,
                      allow_multiple: r.allow_multiple,
                      is_archived: !e.currentTarget.checked,
                    })
                  }
                />
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <Group>
        <TextInput
          placeholder="New role, e.g. Reviewer"
          value={label}
          onChange={(e) => setLabel(e.currentTarget.value)}
        />
        <Button
          disabled={!label.trim()}
          onClick={() =>
            upsert.mutate({ workspace_id: schema.workspace.id, label }, { onSuccess: () => setLabel("") })
          }
        >
          Add role
        </Button>
      </Group>
    </Stack>
  );
}

function BoardsTab() {
  const { schema } = useWorkspace();
  const inv = { invalidate: [["schema"], ["items"]] };
  const reorder = useCommand("boards.reorder", inv);
  const restore = useCommand("boards.restore", { ...inv, success: "Board restored with its items" });
  if (!schema) return null;
  const active = schema.boards.filter((b) => !b.archived);
  const move = (i: number, dir: -1 | 1) => {
    const ids = active.map((b) => b.id);
    const j = i + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    reorder.mutate({ workspace_id: schema.workspace.id, board_ids: ids });
  };
  return (
    <Stack maw={600}>
      <Table withTableBorder style={{ background: "var(--surface)" }}>
        <Table.Tbody>
          {active.map((b, i) => (
            <Table.Tr key={b.id}>
              <Table.Td>{b.name}</Table.Td>
              <Table.Td>{schema.fiscal_years.find((f) => f.id === b.period_fiscal_year_id)?.label}</Table.Td>
              <Table.Td w={80}>
                <Group gap={2}>
                  <ActionIcon variant="subtle" color="gray" aria-label="Move up" onClick={() => move(i, -1)}>
                    <IconArrowUp size={14} />
                  </ActionIcon>
                  <ActionIcon variant="subtle" color="gray" aria-label="Move down" onClick={() => move(i, 1)}>
                    <IconArrowDown size={14} />
                  </ActionIcon>
                </Group>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {schema.boards.some((b) => b.archived) && (
        <>
          <Text fw={600}>Archived boards</Text>
          {schema.boards
            .filter((b) => b.archived)
            .map((b) => (
              <Group key={b.id} justify="space-between">
                <Text size="sm">{b.name}</Text>
                <Button size="compact-sm" variant="light" onClick={() => restore.mutate({ board_id: b.id })}>
                  Restore
                </Button>
              </Group>
            ))}
        </>
      )}
    </Stack>
  );
}
