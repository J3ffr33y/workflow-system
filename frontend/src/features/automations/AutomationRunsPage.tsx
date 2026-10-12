import { Badge, Button, Group, Select, Table, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../shared/api/client";
import { useCommand } from "../../shared/api/hooks";
import { fmtDateTime } from "../../shared/fields/format";
import { Page } from "../../shared/ui/Page";
import { useWorkspace } from "../../shared/workspace";

interface Run {
  id: number;
  rule_id: string;
  rule_name: string;
  item_id: string | null;
  item_name: string | null;
  trigger_source: string;
  status: string;
  error: string | null;
  command_id: string | null;
  changes: { entity_type: string; field: string; before: any; after: any }[];
  created_at: string;
}

export function AutomationRunsPage() {
  const { ref, ctx } = useWorkspace();
  const [status, setStatus] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const q = useQuery({
    queryKey: ["runs", ref?.id, status, offset],
    queryFn: () =>
      api.get<{ total: number; rows: Run[] }>("/automations/runs", {
        workspace_id: ref!.id,
        status,
        limit: 100,
        offset,
      }),
    enabled: !!ref,
  });
  const revert = useCommand("activity.revert", { invalidate: [["runs"], ["items"]], success: "Run undone" });
  const label = (field: string) => ctx?.columns.get(field.replace(/^data\./, ""))?.label ?? field;

  return (
    <Page title="Automation logs" subtitle="Every time a rule acted on an item, and what it changed.">
      <Group mb="md">
        <Select
          placeholder="All results"
          clearable
          w={180}
          data={[
            { value: "succeeded", label: "Succeeded" },
            { value: "failed", label: "Failed" },
          ]}
          value={status}
          onChange={setStatus}
        />
        <Text size="sm" c="dimmed">
          {q.data?.total ?? 0} runs
        </Text>
      </Group>
      <Table withTableBorder style={{ background: "var(--surface)" }}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>When</Table.Th>
            <Table.Th>Rule</Table.Th>
            <Table.Th>Item</Table.Th>
            <Table.Th>Source</Table.Th>
            <Table.Th>Result</Table.Th>
            <Table.Th>Changes</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {(q.data?.rows ?? []).map((r) => (
            <Table.Tr key={r.id}>
              <Table.Td>{fmtDateTime(r.created_at)}</Table.Td>
              <Table.Td>{r.rule_name}</Table.Td>
              <Table.Td>{r.item_id ? <Link to={`?item=${r.item_id}`}>{r.item_name}</Link> : "—"}</Table.Td>
              <Table.Td>{r.trigger_source}</Table.Td>
              <Table.Td>
                <Badge
                  color={r.status === "succeeded" ? "teal" : r.status === "failed" ? "red" : "gray"}
                  variant="light"
                >
                  {r.status}
                </Badge>
                {r.error && (
                  <Text size="xs" c="red.7">
                    {r.error}
                  </Text>
                )}
              </Table.Td>
              <Table.Td>
                {r.changes
                  .filter((c) => c.entity_type === "item")
                  .map((c, i) => (
                    <Text key={i} size="xs">
                      {label(c.field)}: {String(c.before ?? "empty")} → {String(c.after ?? "empty")}
                    </Text>
                  ))}
              </Table.Td>
              <Table.Td>
                {r.command_id && r.changes.length > 0 && ctx?.can("audit.revert") && (
                  <Button
                    size="compact-xs"
                    variant="subtle"
                    onClick={() => revert.mutate({ command_id: r.command_id })}
                  >
                    Undo
                  </Button>
                )}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <Group mt="md">
        <Button
          size="xs"
          variant="default"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 100))}
        >
          Newer
        </Button>
        <Button
          size="xs"
          variant="default"
          disabled={offset + 100 >= (q.data?.total ?? 0)}
          onClick={() => setOffset(offset + 100)}
        >
          Older
        </Button>
      </Group>
    </Page>
  );
}
