import {
  ActionIcon,
  Anchor,
  Badge,
  Button,
  Center,
  Checkbox,
  Group,
  Loader,
  Modal,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
  TextInput,
  Textarea,
} from "@mantine/core";
import { modals } from "@mantine/modals";
import { IconPencil, IconTrash } from "@tabler/icons-react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../../shared/api/client";
import { useCommand, useDirectory, useMe } from "../../shared/api/hooks";
import type { AuditEntry, ColumnSpec, FieldDefinition, WorkspaceSchema } from "../../shared/api/types";
import { FieldInput } from "../../shared/fields/FieldInput";
import { MONTHS } from "../../shared/fields/format";
import { Page } from "../../shared/ui/Page";
import { StatusPill } from "../../shared/ui/StatusPill";
import { buildCtx } from "../../shared/workspace";
import { ActivityList } from "../activity/ActivityList";
import { CommentsPanel } from "../items/CommentsPanel";
import { CLIENT_TYPES, ENTITY_TYPES } from "./NewClientButton";

interface ClientDetail {
  id: string;
  name: string;
  client_type: string;
  partner_user_id: string | null;
  notes: string | null;
  is_archived: boolean;
  data: Record<string, any>;
  entities: {
    id: string;
    name: string;
    entity_type: string;
    abn: string | null;
    acn: string | null;
    year_end_month: number | null;
    is_primary: boolean;
  }[];
  contacts: {
    id: string;
    name: string;
    email: string | null;
    phone: string | null;
    role: string | null;
    is_primary: boolean;
    is_billing: boolean;
    is_referrer: boolean;
  }[];
  items: {
    id: string;
    name: string;
    status: string | null;
    board_id: string;
    board_name: string;
    workspace_id: string;
    workspace_key: string;
    workspace_name: string;
    is_archived: boolean;
  }[];
}

function asColumn(f: FieldDefinition): ColumnSpec {
  return {
    key: f.key,
    label: f.label,
    type: f.type,
    source: "data",
    kind: "text",
    config: f.config,
    editable: true,
    required: f.is_required,
    group: f.group,
    position: f.position,
    rollover: "carry",
    hidden_by_default: false,
  };
}

export function ClientPage() {
  const { clientId } = useParams();
  const navigate = useNavigate();
  const me = useMe();
  const dir = useDirectory();
  const key = ["clients", "detail", clientId];
  const q = useQuery({ queryKey: key, queryFn: () => api.get<ClientDetail>(`/clients/${clientId}`) });
  const schemas = useQueries({
    queries: (me.data?.workspaces ?? []).map((w) => ({
      queryKey: ["schema", w.id],
      queryFn: () => api.get<WorkspaceSchema>(`/workspaces/${w.id}/schema`),
      staleTime: 300_000,
    })),
  });
  const activity = useQuery({
    queryKey: ["activity", "client", clientId],
    queryFn: () => api.get<AuditEntry[]>("/activity/entity", { entity_type: "client", entity_id: clientId }),
  });
  const inv = { invalidate: [["clients"], ["items"], ["activity"]] };
  const update = useCommand("clients.update", { ...inv, success: "Saved" });
  const archive = useCommand("clients.archive", inv);
  const restore = useCommand("clients.restore", inv);
  const del = useCommand("clients.delete", inv);

  const [draft, setDraft] = useState<Partial<ClientDetail>>({});
  useEffect(() => setDraft({}), [q.data]);

  const firstSchema = schemas.find((s) => s.data)?.data;
  const ctx = firstSchema ? buildCtx(firstSchema, dir.users) : undefined;
  const clientFields = schemas.flatMap(
    (s) => s.data?.field_definitions.filter((f) => f.entity_kind === "client" && !f.is_archived) ?? [],
  );
  const statusOf = (wsId: string, key: string | null) =>
    schemas.find((s) => s.data?.workspace.id === wsId)?.data?.statuses.find((x) => x.key === key);

  if (!q.data || !ctx)
    return <Center h="100%">{q.isError ? <Text c="dimmed">Client not found.</Text> : <Loader />}</Center>;
  const c = q.data;
  const v = { ...c, ...draft };
  const changed = Object.keys(draft).length > 0;
  const canArchive = me.data?.workspaces.some((w) => w.permissions.includes("clients.archive"));

  const save = () =>
    update.mutate({
      client_id: c.id,
      name: v.name,
      client_type: v.client_type,
      partner_user_id: v.partner_user_id ?? undefined,
      clear_partner: !v.partner_user_id && !!c.partner_user_id,
      notes: v.notes ?? undefined,
      data: draft.data ?? {},
    });

  return (
    <Page
      title={
        <Group gap="sm">
          {c.name}
          {c.is_archived && <Badge color="gray">archived</Badge>}
        </Group>
      }
      subtitle={`${CLIENT_TYPES.find((t) => t.value === c.client_type)?.label ?? c.client_type} · ${c.items.filter((i) => !i.is_archived).length} active items`}
      actions={
        canArchive && (
          <>
            {c.is_archived ? (
              <Button variant="default" onClick={() => restore.mutate({ client_id: c.id })}>
                Restore client
              </Button>
            ) : (
              <Button
                variant="default"
                onClick={() =>
                  modals.openConfirmModal({
                    title: `Archive ${c.name}?`,
                    children: (
                      <Text size="sm">
                        Their active items are archived too. Restoring the client brings those items back.
                      </Text>
                    ),
                    labels: { confirm: "Archive", cancel: "Cancel" },
                    onConfirm: () => archive.mutate({ client_id: c.id }),
                  })
                }
              >
                Archive client
              </Button>
            )}
            <Button
              variant="subtle"
              color="red"
              onClick={() =>
                modals.openConfirmModal({
                  title: `Delete ${c.name}?`,
                  children: (
                    <Text size="sm">
                      Only possible when the client has no items. Archive is usually what you want.
                    </Text>
                  ),
                  labels: { confirm: "Delete", cancel: "Cancel" },
                  confirmProps: { color: "red" },
                  onConfirm: () => del.mutate({ client_id: c.id }, { onSuccess: () => navigate("/clients") }),
                })
              }
            >
              Delete
            </Button>
          </>
        )
      }
    >
      <Tabs defaultValue="details">
        <Tabs.List mb="md">
          <Tabs.Tab value="details">Details</Tabs.Tab>
          <Tabs.Tab value="items">Work ({c.items.length})</Tabs.Tab>
          <Tabs.Tab value="updates">Updates</Tabs.Tab>
          <Tabs.Tab value="activity">Activity</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="details">
          <Stack gap="lg" maw={980}>
            <Paper withBorder p="md">
              <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
                <TextInput
                  label="Name"
                  value={v.name}
                  onChange={(e) => setDraft({ ...draft, name: e.currentTarget.value })}
                />
                <Select
                  label="Type"
                  data={CLIENT_TYPES}
                  value={v.client_type}
                  onChange={(t) => setDraft({ ...draft, client_type: t ?? "individual" })}
                />
                <Select
                  label="Responsible partner"
                  clearable
                  searchable
                  data={dir.users.map((u) => ({ value: u.id, label: u.full_name }))}
                  value={v.partner_user_id}
                  onChange={(p) => setDraft({ ...draft, partner_user_id: p })}
                />
                {clientFields.map((f) => (
                  <FieldInput
                    key={f.id}
                    col={asColumn(f)}
                    ctx={ctx}
                    label={f.label}
                    value={(draft.data ?? {})[f.key] ?? c.data[f.key] ?? null}
                    onChange={(val) => setDraft({ ...draft, data: { ...(draft.data ?? {}), [f.key]: val } })}
                  />
                ))}
              </SimpleGrid>
              <Textarea
                mt="sm"
                label="Notes"
                autosize
                minRows={2}
                value={v.notes ?? ""}
                onChange={(e) => setDraft({ ...draft, notes: e.currentTarget.value })}
              />
              <Group justify="flex-end" mt="sm">
                {changed && (
                  <Button variant="subtle" color="gray" onClick={() => setDraft({})}>
                    Discard
                  </Button>
                )}
                <Button disabled={!changed} onClick={save} loading={update.isPending}>
                  Save changes
                </Button>
              </Group>
            </Paper>
            <Entities client={c} />
            <Contacts client={c} />
          </Stack>
        </Tabs.Panel>
        <Tabs.Panel value="items">
          <Table withTableBorder highlightOnHover maw={980} style={{ background: "var(--surface)" }}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Item</Table.Th>
                <Table.Th>Product line</Table.Th>
                <Table.Th>Board</Table.Th>
                <Table.Th w={210}>Status</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {c.items.map((i) => (
                <Table.Tr key={i.id} style={{ opacity: i.is_archived ? 0.55 : 1 }}>
                  <Table.Td>
                    <Anchor
                      component={Link}
                      to={`/w/${i.workspace_key}/b/${i.board_id}?item=${i.id}`}
                      size="sm"
                    >
                      {i.name}
                    </Anchor>
                    {i.is_archived && (
                      <Badge ml={6} size="xs" color="gray">
                        archived
                      </Badge>
                    )}
                  </Table.Td>
                  <Table.Td>{i.workspace_name}</Table.Td>
                  <Table.Td>{i.board_name}</Table.Td>
                  <Table.Td>
                    <StatusPill status={statusOf(i.workspace_id, i.status)} />
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
          {!c.items.length && <Text c="dimmed">No work recorded for this client yet.</Text>}
        </Tabs.Panel>
        <Tabs.Panel value="updates">
          <div style={{ maxWidth: 760 }}>
            <CommentsPanel entityType="client" entityId={c.id} ctx={ctx} canWrite />
          </div>
        </Tabs.Panel>
        <Tabs.Panel value="activity">
          <ActivityList entries={activity.data ?? []} ctx={ctx} canRevert />
        </Tabs.Panel>
      </Tabs>
    </Page>
  );
}

function Entities({ client }: { client: ClientDetail }) {
  const [edit, setEdit] = useState<any | null>(null);
  const inv = { invalidate: [["clients"], ["items"]] };
  const upsert = useCommand("clients.upsert_entity", inv);
  const del = useCommand("clients.delete_entity", inv);
  return (
    <Paper withBorder p="md">
      <Group justify="space-between" mb="xs">
        <Text fw={600}>Entities</Text>
        <Button
          size="compact-sm"
          variant="light"
          onClick={() =>
            setEdit({
              name: client.name,
              entity_type: "individual",
              abn: "",
              year_end_month: 6,
              is_primary: !client.entities.length,
            })
          }
        >
          Add entity
        </Button>
      </Group>
      <Table>
        <Table.Tbody>
          {client.entities.map((e) => (
            <Table.Tr key={e.id}>
              <Table.Td>
                {e.name}{" "}
                {e.is_primary && (
                  <Badge size="xs" ml={4}>
                    primary
                  </Badge>
                )}
              </Table.Td>
              <Table.Td>
                {ENTITY_TYPES.find((t) => t.value === e.entity_type)?.label ?? e.entity_type}
              </Table.Td>
              <Table.Td>{e.abn ? `ABN ${e.abn}` : ""}</Table.Td>
              <Table.Td>{e.year_end_month ? `Year end ${MONTHS[e.year_end_month - 1]}` : ""}</Table.Td>
              <Table.Td w={70}>
                <Group gap={2}>
                  <ActionIcon
                    variant="subtle"
                    color="gray"
                    aria-label="Edit entity"
                    onClick={() => setEdit(e)}
                  >
                    <IconPencil size={14} />
                  </ActionIcon>
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    aria-label="Delete entity"
                    onClick={() => del.mutate({ entity_id: e.id })}
                  >
                    <IconTrash size={14} />
                  </ActionIcon>
                </Group>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <Modal opened={!!edit} onClose={() => setEdit(null)} title={edit?.id ? "Edit entity" : "Add entity"}>
        {edit && (
          <Stack>
            <TextInput
              label="Name"
              value={edit.name}
              onChange={(e) => setEdit({ ...edit, name: e.currentTarget.value })}
            />
            <Select
              label="Type"
              data={ENTITY_TYPES}
              value={edit.entity_type}
              onChange={(t) => setEdit({ ...edit, entity_type: t })}
            />
            <TextInput
              label="ABN"
              value={edit.abn ?? ""}
              onChange={(e) => setEdit({ ...edit, abn: e.currentTarget.value })}
            />
            <Select
              label="Year end"
              clearable
              data={MONTHS.map((m, i) => ({ value: String(i + 1), label: m }))}
              value={edit.year_end_month ? String(edit.year_end_month) : null}
              onChange={(m) => setEdit({ ...edit, year_end_month: m ? Number(m) : null })}
            />
            <Checkbox
              label="Primary entity"
              checked={!!edit.is_primary}
              onChange={(e) => setEdit({ ...edit, is_primary: e.currentTarget.checked })}
            />
            <Button
              loading={upsert.isPending}
              onClick={() =>
                upsert.mutate(
                  {
                    client_id: client.id,
                    entity_id: edit.id ?? null,
                    name: edit.name,
                    entity_type: edit.entity_type,
                    abn: edit.abn || null,
                    year_end_month: edit.year_end_month,
                    is_primary: edit.is_primary,
                  },
                  { onSuccess: () => setEdit(null) },
                )
              }
            >
              Save entity
            </Button>
          </Stack>
        )}
      </Modal>
    </Paper>
  );
}

function Contacts({ client }: { client: ClientDetail }) {
  const [edit, setEdit] = useState<any | null>(null);
  const inv = { invalidate: [["clients"], ["items"]] };
  const upsert = useCommand("clients.upsert_contact", inv);
  const del = useCommand("clients.delete_contact", inv);
  return (
    <Paper withBorder p="md">
      <Group justify="space-between" mb="xs">
        <Text fw={600}>Contacts</Text>
        <Button
          size="compact-sm"
          variant="light"
          onClick={() => setEdit({ name: "", is_primary: !client.contacts.length })}
        >
          Add contact
        </Button>
      </Group>
      {!client.contacts.length && (
        <Text size="sm" c="dimmed">
          No contacts yet.
        </Text>
      )}
      <Table>
        <Table.Tbody>
          {client.contacts.map((ct) => (
            <Table.Tr key={ct.id}>
              <Table.Td>
                {ct.name}
                {ct.is_primary && (
                  <Badge size="xs" ml={4}>
                    primary
                  </Badge>
                )}
                {ct.is_billing && (
                  <Badge size="xs" ml={4} color="gray">
                    billing
                  </Badge>
                )}
                {ct.is_referrer && (
                  <Badge size="xs" ml={4} color="grape">
                    referrer
                  </Badge>
                )}
              </Table.Td>
              <Table.Td>{ct.role}</Table.Td>
              <Table.Td>{ct.email}</Table.Td>
              <Table.Td>{ct.phone}</Table.Td>
              <Table.Td w={70}>
                <Group gap={2}>
                  <ActionIcon
                    variant="subtle"
                    color="gray"
                    aria-label="Edit contact"
                    onClick={() => setEdit(ct)}
                  >
                    <IconPencil size={14} />
                  </ActionIcon>
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    aria-label="Delete contact"
                    onClick={() => del.mutate({ contact_id: ct.id })}
                  >
                    <IconTrash size={14} />
                  </ActionIcon>
                </Group>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <Modal opened={!!edit} onClose={() => setEdit(null)} title={edit?.id ? "Edit contact" : "Add contact"}>
        {edit && (
          <Stack>
            <TextInput
              label="Name"
              value={edit.name}
              onChange={(e) => setEdit({ ...edit, name: e.currentTarget.value })}
            />
            <TextInput
              label="Role"
              value={edit.role ?? ""}
              onChange={(e) => setEdit({ ...edit, role: e.currentTarget.value })}
            />
            <TextInput
              label="Email"
              value={edit.email ?? ""}
              onChange={(e) => setEdit({ ...edit, email: e.currentTarget.value })}
            />
            <TextInput
              label="Phone"
              value={edit.phone ?? ""}
              onChange={(e) => setEdit({ ...edit, phone: e.currentTarget.value })}
            />
            <Group>
              <Checkbox
                label="Primary"
                checked={!!edit.is_primary}
                onChange={(e) => setEdit({ ...edit, is_primary: e.currentTarget.checked })}
              />
              <Checkbox
                label="Billing"
                checked={!!edit.is_billing}
                onChange={(e) => setEdit({ ...edit, is_billing: e.currentTarget.checked })}
              />
              <Checkbox
                label="Referrer"
                checked={!!edit.is_referrer}
                onChange={(e) => setEdit({ ...edit, is_referrer: e.currentTarget.checked })}
              />
            </Group>
            <Button
              loading={upsert.isPending}
              disabled={!edit.name?.trim()}
              onClick={() =>
                upsert.mutate(
                  {
                    contact_id: edit.id ?? null,
                    client_id: client.id,
                    name: edit.name,
                    role: edit.role || null,
                    email: edit.email || null,
                    phone: edit.phone || null,
                    is_primary: !!edit.is_primary,
                    is_billing: !!edit.is_billing,
                    is_referrer: !!edit.is_referrer,
                  },
                  { onSuccess: () => setEdit(null) },
                )
              }
            >
              Save contact
            </Button>
          </Stack>
        )}
      </Modal>
    </Paper>
  );
}
