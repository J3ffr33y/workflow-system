import {
  Alert,
  Badge,
  Button,
  FileInput,
  Group,
  Paper,
  PasswordInput,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  TagsInput,
  Text,
  TextInput,
} from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../shared/api/client";
import { errorMessage } from "../../shared/api/hooks";
import { fmtDateTime } from "../../shared/fields/format";
import { Page } from "../../shared/ui/Page";
import { useWorkspace } from "../../shared/workspace";

export const RUN_STATUS: Record<string, { label: string; color: string }> = {
  draft: { label: "Mapping", color: "gray" },
  validated: { label: "Checked", color: "blue" },
  prepared: { label: "Ready to import", color: "cyan" },
  committing: { label: "Importing…", color: "orange" },
  committed: { label: "Imported", color: "teal" },
  committed_with_errors: { label: "Imported with errors", color: "orange" },
  rolled_back: { label: "Rolled back", color: "gray" },
};

export function MigrationPage() {
  const { ref, schema } = useWorkspace();
  const navigate = useNavigate();
  const runs = useQuery({
    queryKey: ["migration-runs", ref?.id],
    queryFn: () => api.get<any[]>("/migration/runs", { workspace_id: ref!.id }),
    enabled: !!ref,
  });
  const [board, setBoard] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [keys, setKeys] = useState<string[]>(["Client Name"]);
  const [erp, setErp] = useState({
    base_url: "",
    api_key: "",
    api_secret: "",
    project_types: [] as string[],
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const upload = async () => {
    setBusy(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("workspace_id", ref!.id);
      fd.append("board_id", board!);
      fd.append("key_columns", keys.join(","));
      fd.append("file", file!);
      const res = await api.post<{ run_id: string }>("/migration/upload-csv", fd);
      navigate(res.run_id);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const pull = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.post<{ run_id: string }>("/migration/pull-erpnext", {
        workspace_id: ref!.id,
        board_id: board,
        ...erp,
      });
      navigate(res.run_id);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Page
      title="Data migration"
      subtitle="Bring items from the old ERPNext system into this product line. Nothing is written until you confirm the import, and every import can be rolled back."
    >
      <Stack maw={1000} gap="lg">
        <Paper withBorder p="md">
          <Select
            label="Import into board"
            w={320}
            data={(schema?.boards ?? [])
              .filter((b) => !b.archived)
              .map((b) => ({ value: b.id, label: b.name }))}
            value={board}
            onChange={setBoard}
            mb="md"
          />
          {error && (
            <Alert color="red" variant="light" mb="md">
              {error}
            </Alert>
          )}
          <Tabs defaultValue="csv">
            <Tabs.List mb="md">
              <Tabs.Tab value="csv">CSV export</Tabs.Tab>
              <Tabs.Tab value="erpnext">ERPNext directly (recommended)</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value="csv">
              <Stack gap="sm">
                <Text size="sm" c="dimmed">
                  Any encoding works (UTF-8, or GBK files re-saved by Excel). Exports only contain the columns
                  that were visible, so check the mapping on the next screen.
                </Text>
                <SimpleGrid cols={2}>
                  <FileInput
                    label="CSV file"
                    accept=".csv,text/csv"
                    value={file}
                    onChange={setFile}
                    placeholder="Choose file"
                  />
                  <TagsInput
                    label="Columns that identify a row"
                    description="Used to recognise the same row if you import again."
                    value={keys}
                    onChange={setKeys}
                  />
                </SimpleGrid>
                <Button w="fit-content" disabled={!board || !file} loading={busy} onClick={upload}>
                  Upload and map columns
                </Button>
              </Stack>
            </Tabs.Panel>
            <Tabs.Panel value="erpnext">
              <Stack gap="sm">
                <Text size="sm" c="dimmed">
                  Reads every field, team, software, update and monthly status straight from ERPNext. The API
                  key is used for this request only and is not stored.
                </Text>
                <SimpleGrid cols={2}>
                  <TextInput
                    label="ERPNext address"
                    placeholder="https://erp.example.com"
                    value={erp.base_url}
                    onChange={(e) => setErp({ ...erp, base_url: e.currentTarget.value })}
                  />
                  <TagsInput
                    label="Project Types (boards) to pull"
                    placeholder="e.g. ITR, FY 2026"
                    value={erp.project_types}
                    onChange={(v) => setErp({ ...erp, project_types: v })}
                  />
                  <TextInput
                    label="API key"
                    value={erp.api_key}
                    onChange={(e) => setErp({ ...erp, api_key: e.currentTarget.value })}
                  />
                  <PasswordInput
                    label="API secret"
                    value={erp.api_secret}
                    onChange={(e) => setErp({ ...erp, api_secret: e.currentTarget.value })}
                  />
                </SimpleGrid>
                <Button
                  w="fit-content"
                  disabled={!board || !erp.base_url || !erp.api_key || !erp.project_types.length}
                  loading={busy}
                  onClick={pull}
                >
                  Fetch and map columns
                </Button>
              </Stack>
            </Tabs.Panel>
          </Tabs>
        </Paper>

        <section>
          <Text fw={600} mb="xs">
            Previous imports
          </Text>
          <Table withTableBorder highlightOnHover style={{ background: "var(--surface)" }}>
            <Table.Tbody>
              {(runs.data ?? []).map((r) => (
                <Table.Tr key={r.id} style={{ cursor: "pointer" }} onClick={() => navigate(r.id)}>
                  <Table.Td>{r.name}</Table.Td>
                  <Table.Td>{schema?.boards.find((b) => b.id === r.board_id)?.name}</Table.Td>
                  <Table.Td>{r.source_meta?.row_count} rows</Table.Td>
                  <Table.Td>
                    <Badge variant="light" color={RUN_STATUS[r.status]?.color}>
                      {RUN_STATUS[r.status]?.label ?? r.status}
                    </Badge>
                  </Table.Td>
                  <Table.Td>{fmtDateTime(r.created_at)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
          {runs.data && !runs.data.length && (
            <Group>
              <Text size="sm" c="dimmed">
                No imports yet.
              </Text>
            </Group>
          )}
        </section>
      </Stack>
    </Page>
  );
}
