import { Badge, Button, Group, Modal, Select, Stack, Table, Text, TextInput } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { IconSearch } from "@tabler/icons-react";
import { useState } from "react";
import { ApiError, command } from "../../shared/api/client";
import { notifyError } from "../../shared/api/hooks";
import { fmtDate } from "../../shared/fields/format";
import { Page } from "../../shared/ui/Page";
import { StatusPill } from "../../shared/ui/StatusPill";
import { useWorkspace } from "../../shared/workspace";
import { useBoardItems } from "../boards/useBoardItems";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

const SOURCE: Record<string, string> = {
  manual: "Archived by hand",
  automation: "Archived by automation",
  client_archive: "Client archived",
  board_archived: "Board archived",
  rollover: "Rolled over",
};

export function ArchivedPage() {
  const { ref, schema, ctx } = useWorkspace();
  const [search, setSearch] = useState("");
  const [debounced] = useDebouncedValue(search, 250);
  const [selected, setSelected] = useState<string[]>([]);
  const [needBoard, setNeedBoard] = useState<string[] | null>(null);
  const [targets, setTargets] = useState<Record<string, string>>({});
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const items = useBoardItems({ workspaceId: ref?.id ?? "", archived: true, search: debounced });
  const rows = items.data ?? [];
  const canRestore = ctx?.can("items.archive");

  const restore = async (ids: string[], target_boards: Record<string, string> = {}) => {
    try {
      await command("items.restore", { item_ids: ids, target_boards });
      setSelected([]);
      setNeedBoard(null);
      qc.invalidateQueries({ queryKey: ["items"] });
    } catch (e) {
      if (e instanceof ApiError && e.code === "needs_target_board") setNeedBoard(e.details.item_ids);
      else notifyError(e);
    }
  };

  const activeBoards = (schema?.boards ?? []).filter((b) => !b.archived);
  return (
    <Page
      title="Archived"
      subtitle={`${schema?.workspace.name ?? ""} · ${rows.length} archived items`}
      actions={
        canRestore &&
        selected.length > 0 && (
          <Button onClick={() => restore(selected)}>Restore {selected.length} item(s)</Button>
        )
      }
    >
      <TextInput
        mb="md"
        w={280}
        leftSection={<IconSearch size={14} />}
        placeholder="Search archived items"
        value={search}
        onChange={(e) => setSearch(e.currentTarget.value)}
      />
      <Table withTableBorder highlightOnHover style={{ background: "var(--surface)" }}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th w={36} />
            <Table.Th>Item</Table.Th>
            <Table.Th>Client</Table.Th>
            <Table.Th>Board</Table.Th>
            <Table.Th w={200}>Status</Table.Th>
            <Table.Th>Why</Table.Th>
            <Table.Th>When</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((r) => (
            <Table.Tr key={r.id}>
              <Table.Td>
                <input
                  type="checkbox"
                  aria-label={`Select ${r.name}`}
                  checked={selected.includes(r.id)}
                  onChange={(e) =>
                    setSelected(
                      e.currentTarget.checked ? [...selected, r.id] : selected.filter((x) => x !== r.id),
                    )
                  }
                />
              </Table.Td>
              <Table.Td>
                <Link to={`?${new URLSearchParams({ ...Object.fromEntries(params), item: r.id })}`}>
                  {r.name}
                </Link>
              </Table.Td>
              <Table.Td>{r.client_name}</Table.Td>
              <Table.Td>
                {ctx?.boards.get(r.board_id)}
                {schema?.boards.find((b) => b.id === r.board_id)?.archived && (
                  <Badge ml={6} size="xs" color="gray">
                    board archived
                  </Badge>
                )}
              </Table.Td>
              <Table.Td>
                <StatusPill status={ctx?.statuses.get(r.status ?? "")} />
              </Table.Td>
              <Table.Td>
                <Text size="sm">{SOURCE[r.archive_source ?? ""] ?? r.archive_source}</Text>
              </Table.Td>
              <Table.Td>{fmtDate(r.archived_at)}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {!rows.length && !items.isLoading && (
        <Text c="dimmed" mt="md">
          Nothing archived{search ? " matches your search" : ""}.
        </Text>
      )}
      <Modal opened={!!needBoard} onClose={() => setNeedBoard(null)} title="Choose a board" size="lg">
        <Stack>
          <Text size="sm">
            These items belonged to a board that is archived. Pick where each one should go.
          </Text>
          {(needBoard ?? []).map((id) => (
            <Group key={id} grow>
              <Text size="sm">{rows.find((r) => r.id === id)?.name}</Text>
              <Select
                data={activeBoards.map((b) => ({ value: b.id, label: b.name }))}
                value={targets[id] ?? null}
                onChange={(v) => setTargets({ ...targets, [id]: v ?? "" })}
              />
            </Group>
          ))}
          <Group justify="flex-end">
            <Button
              disabled={(needBoard ?? []).some((id) => !targets[id])}
              onClick={() =>
                restore(selected, Object.fromEntries((needBoard ?? []).map((id) => [id, targets[id]])))
              }
            >
              Restore
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Page>
  );
}
