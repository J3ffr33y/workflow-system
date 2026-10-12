import {
  Badge,
  Button,
  Checkbox,
  Group,
  Modal,
  PasswordInput,
  Select,
  SimpleGrid,
  Stack,
  Table,
  TagsInput,
  Text,
  TextInput,
} from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../shared/api/client";
import { useCommand, useMe } from "../../shared/api/hooks";
import { fmtDateTime } from "../../shared/fields/format";
import { Page } from "../../shared/ui/Page";

interface UserRow {
  id: string;
  email: string;
  full_name: string;
  aliases: string[];
  is_active: boolean;
  is_superadmin: boolean;
  is_placeholder: boolean;
  last_login_at: string | null;
  memberships: Record<string, string>;
}

const ROLES = [
  { value: "", label: "No access" },
  { value: "viewer", label: "Viewer" },
  { value: "member", label: "Member" },
  { value: "manager", label: "Manager" },
  { value: "admin", label: "Admin" },
];

export function UsersPage() {
  const me = useMe();
  const q = useQuery({ queryKey: ["users"], queryFn: () => api.get<UserRow[]>("/users") });
  const [edit, setEdit] = useState<(Partial<UserRow> & { password?: string }) | null>(null);
  const inv = { invalidate: [["users"], ["directory"]] };
  const create = useCommand("identity.create_user", { ...inv, success: "User created" });
  const update = useCommand("identity.update_user", { ...inv, success: "User saved" });
  const setPw = useCommand("identity.set_user_password", {
    success: "Password set; the user is signed out everywhere",
  });
  const workspaces = me.data?.workspaces ?? [];

  const save = async () => {
    if (!edit) return;
    const memberships = Object.fromEntries(workspaces.map((w) => [w.key, edit.memberships?.[w.key] || null]));
    if (edit.id) {
      await update.mutateAsync({
        user_id: edit.id,
        email: edit.email,
        full_name: edit.full_name,
        is_active: edit.is_active,
        is_superadmin: edit.is_superadmin,
        aliases: edit.aliases,
        memberships: memberships as any,
      });
      if (edit.password) await setPw.mutateAsync({ user_id: edit.id, password: edit.password });
    } else {
      await create.mutateAsync({
        email: edit.email!,
        full_name: edit.full_name!,
        password: edit.password || null,
        is_superadmin: !!edit.is_superadmin,
        aliases: edit.aliases ?? [],
        memberships: Object.fromEntries(Object.entries(memberships).filter(([, v]) => v)) as any,
      });
    }
    setEdit(null);
  };

  return (
    <Page
      title="Users"
      subtitle="Who can sign in, and what they can do in each product line."
      actions={
        <Button onClick={() => setEdit({ is_active: true, memberships: {}, aliases: [] })}>New user</Button>
      }
    >
      <Table withTableBorder highlightOnHover style={{ background: "var(--surface)" }}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Name</Table.Th>
            <Table.Th>Email</Table.Th>
            {workspaces.map((w) => (
              <Table.Th key={w.key}>{w.name}</Table.Th>
            ))}
            <Table.Th>Last sign-in</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {(q.data ?? []).map((u) => (
            <Table.Tr
              key={u.id}
              style={{ cursor: "pointer", opacity: u.is_active ? 1 : 0.5 }}
              onClick={() => setEdit(u)}
            >
              <Table.Td>
                {u.full_name}
                {u.is_superadmin && (
                  <Badge size="xs" ml={6}>
                    admin
                  </Badge>
                )}
                {u.is_placeholder && (
                  <Badge size="xs" ml={6} color="gray">
                    no login
                  </Badge>
                )}
                {!u.is_active && (
                  <Badge size="xs" ml={6} color="red">
                    disabled
                  </Badge>
                )}
              </Table.Td>
              <Table.Td>{u.is_placeholder ? "" : u.email}</Table.Td>
              {workspaces.map((w) => (
                <Table.Td key={w.key}>{u.memberships[w.key] ?? "—"}</Table.Td>
              ))}
              <Table.Td>{fmtDateTime(u.last_login_at)}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <Modal
        opened={!!edit}
        onClose={() => setEdit(null)}
        title={edit?.id ? `Edit ${edit.full_name}` : "New user"}
        size="lg"
      >
        {edit && (
          <Stack>
            {edit.is_placeholder && (
              <Text size="sm" c="dimmed">
                This person was created by a data migration and cannot sign in yet. Give them a real email and
                a password to activate them.
              </Text>
            )}
            <SimpleGrid cols={2}>
              <TextInput
                label="Full name"
                value={edit.full_name ?? ""}
                onChange={(e) => setEdit({ ...edit, full_name: e.currentTarget.value })}
              />
              <TextInput
                label="Email (sign-in)"
                value={edit.email ?? ""}
                onChange={(e) => setEdit({ ...edit, email: e.currentTarget.value })}
              />
            </SimpleGrid>
            <TagsInput
              label="Other names"
              description="Short names used in old spreadsheets or @mentions, e.g. Win, CL. Used to match people during imports."
              value={edit.aliases ?? []}
              onChange={(aliases) => setEdit({ ...edit, aliases })}
            />
            <SimpleGrid cols={2}>
              {workspaces.map((w) => (
                <Select
                  key={w.key}
                  label={w.name}
                  data={ROLES}
                  value={edit.memberships?.[w.key] ?? ""}
                  onChange={(r) =>
                    setEdit({ ...edit, memberships: { ...(edit.memberships ?? {}), [w.key]: r ?? "" } })
                  }
                />
              ))}
            </SimpleGrid>
            <PasswordInput
              label={edit.id ? "Set a new password (optional)" : "Password"}
              description="At least 10 characters, upper and lower case, and a digit."
              value={edit.password ?? ""}
              onChange={(e) => setEdit({ ...edit, password: e.currentTarget.value })}
            />
            <Group>
              <Checkbox
                label="Active"
                checked={edit.is_active ?? true}
                onChange={(e) => setEdit({ ...edit, is_active: e.currentTarget.checked })}
              />
              <Checkbox
                label="Administrator (manages users and the system)"
                checked={!!edit.is_superadmin}
                onChange={(e) => setEdit({ ...edit, is_superadmin: e.currentTarget.checked })}
              />
            </Group>
            <Group justify="flex-end">
              <Button
                onClick={save}
                loading={create.isPending || update.isPending}
                disabled={!edit.full_name?.trim() || !edit.email?.trim()}
              >
                Save user
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </Page>
  );
}
