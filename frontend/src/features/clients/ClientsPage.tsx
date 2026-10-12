import { Badge, Group, SegmentedControl, Table, Text, TextInput } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { IconSearch } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../shared/api/client";
import { MONTHS } from "../../shared/fields/format";
import { Page } from "../../shared/ui/Page";
import { NewClientButton } from "./NewClientButton";

interface ClientRow {
  id: string;
  name: string;
  client_type: string;
  partner_name: string | null;
  active_items: number;
  is_archived: boolean;
  primary_entity: { entity_type: string; abn: string | null; year_end_month: number | null } | null;
}

export function ClientsPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [archived, setArchived] = useState("active");
  const [debounced] = useDebouncedValue(search, 250);
  const q = useQuery({
    queryKey: ["clients", debounced, archived],
    queryFn: () =>
      api.get<{ total: number; rows: ClientRow[] }>("/clients", {
        search: debounced,
        archived: archived === "archived",
        limit: 500,
      }),
    placeholderData: (p) => p,
  });
  return (
    <Page
      title="Clients"
      subtitle={
        q.data ? `${q.data.total} ${archived === "archived" ? "archived" : "active"} clients` : undefined
      }
      actions={<NewClientButton onCreated={(id) => navigate(`/clients/${id}`)} />}
    >
      <Group mb="md">
        <TextInput
          leftSection={<IconSearch size={14} />}
          placeholder="Search clients"
          value={search}
          onChange={(e) => setSearch(e.currentTarget.value)}
          w={280}
          aria-label="Search clients"
        />
        <SegmentedControl
          value={archived}
          onChange={setArchived}
          data={[
            { value: "active", label: "Active" },
            { value: "archived", label: "Archived" },
          ]}
        />
      </Group>
      <Table
        highlightOnHover
        verticalSpacing="xs"
        style={{ background: "var(--surface)", borderRadius: 8 }}
        withTableBorder
      >
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Name</Table.Th>
            <Table.Th>Type</Table.Th>
            <Table.Th>ABN</Table.Th>
            <Table.Th>Year end</Table.Th>
            <Table.Th>Partner</Table.Th>
            <Table.Th ta="right">Active items</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {(q.data?.rows ?? []).map((c) => (
            <Table.Tr key={c.id} style={{ cursor: "pointer" }} onClick={() => navigate(`/clients/${c.id}`)}>
              <Table.Td>
                <Text size="sm" fw={500}>
                  {c.name}
                </Text>
              </Table.Td>
              <Table.Td>
                <Badge variant="light" color="gray" size="sm" style={{ textTransform: "none" }}>
                  {c.primary_entity?.entity_type ?? c.client_type}
                </Badge>
              </Table.Td>
              <Table.Td>{c.primary_entity?.abn ?? ""}</Table.Td>
              <Table.Td>
                {c.primary_entity?.year_end_month ? MONTHS[c.primary_entity.year_end_month - 1] : ""}
              </Table.Td>
              <Table.Td>{c.partner_name ?? ""}</Table.Td>
              <Table.Td ta="right">{c.active_items}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {q.data && !q.data.rows.length && (
        <Text c="dimmed" mt="md">
          {search
            ? "No client matches your search."
            : "No clients yet. Create one, or import them with Data migration."}
        </Text>
      )}
    </Page>
  );
}
