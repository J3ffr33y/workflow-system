import {
  Alert,
  Badge,
  Button,
  Center,
  Checkbox,
  Group,
  Loader,
  Paper,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Stepper,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import { modals } from "@mantine/modals";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, command } from "../../shared/api/client";
import { notifyError } from "../../shared/api/hooks";
import { Page } from "../../shared/ui/Page";
import { useWorkspace, type FieldCtx } from "../../shared/workspace";
import { grouped } from "../../shared/fields/format";
import { RUN_STATUS } from "./MigrationPage";

interface Target {
  key: string;
  label: string;
  type: string;
  config: Record<string, any>;
  group: string;
  value_mapped: boolean;
}

interface Run {
  id: string;
  name: string;
  status: string;
  board_id: string;
  source_kind: string;
  source_meta: { headers: string[]; row_count: number; encoding?: string };
  mapping: {
    columns: Record<string, string>;
    values: Record<string, Record<string, string>>;
    options: Record<string, any>;
  };
  stats: Record<string, any> | null;
  targets: Target[];
  distinct: Record<string, Record<string, number>>;
  samples?: Record<string, string[]>;
  outcomes: Record<string, number>;
}

const NEW = "__new__";
const EMPTY = "__empty__";

function valueOptions(t: Target, ctx: FieldCtx) {
  switch (t.type) {
    case "status":
      return ctx.schema.statuses.map((s) => ({ value: s.key, label: s.label }));
    case "select":
    case "multi_select":
    case "entity_type":
      return (t.config.options ?? []).map((o: any) => ({ value: o.key, label: o.label }));
    case "lookup":
    case "lookup_multi":
      return (ctx.schema.lookups.find((l) => l.key === t.config.list)?.values ?? []).map((v) => ({
        value: v.id,
        label: v.label,
      }));
    case "user":
    case "users":
      return ctx.userList.map((u) => ({ value: u.id, label: u.full_name }));
    case "fiscal_year":
      return ctx.schema.fiscal_years.map((f) => ({ value: f.id, label: f.label }));
    default:
      return [];
  }
}

export function MigrationRunPage() {
  const { runId } = useParams();
  const { ctx } = useWorkspace();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["migration-run", runId],
    queryFn: () => api.get<Run>(`/migration/runs/${runId}`),
    refetchInterval: (query) => (query.state.data?.status === "committing" ? 1500 : false),
  });
  const issues = useQuery({
    queryKey: ["migration-rows", runId, q.data?.status],
    queryFn: () =>
      api.get<{ total: number; rows: any[] }>(`/migration/runs/${runId}/rows`, {
        only_issues: true,
        limit: 300,
      }),
    enabled: !!q.data && q.data.status !== "draft",
  });
  const [columns, setColumns] = useState<Record<string, string>>({});
  const [values, setValues] = useState<Record<string, Record<string, string>>>({});
  const [options, setOptions] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (q.data) {
      setColumns(q.data.mapping.columns);
      setValues(q.data.mapping.values);
      setOptions(q.data.mapping.options);
    }
  }, [q.data]);

  if (!q.data || !ctx)
    return (
      <Center h="100%">
        <Loader />
      </Center>
    );
  const run = q.data;
  const targets = new Map(run.targets.map((t) => [t.key, t]));
  const locked = ["committing", "committed", "committed_with_errors", "rolled_back"].includes(run.status);
  const step = run.status === "draft" ? 0 : run.status === "validated" || run.status === "prepared" ? 2 : 3;
  const pendingNew = Object.values(values).some((vm) => Object.values(vm).includes(NEW));

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: ["migration-run", runId] });
      qc.invalidateQueries({ queryKey: ["migration-rows", runId] });
    } catch (e) {
      notifyError(e, "Step failed");
    } finally {
      setBusy(false);
    }
  };
  const saveMapping = () => command("migration.update_mapping", { run_id: run.id, columns, values, options });
  const validate = () =>
    act(async () => {
      await saveMapping();
      await command("migration.validate", { run_id: run.id });
    });
  const prepareAndValidate = () =>
    act(async () => {
      await saveMapping();
      await command("migration.validate", { run_id: run.id });
      await command("migration.prepare", { run_id: run.id });
      await command("migration.validate", { run_id: run.id });
      // New placeholder people / options must show up in pickers.
      qc.invalidateQueries({ queryKey: ["directory"] });
      qc.invalidateQueries({ queryKey: ["schema"] });
    });
  const commit = () =>
    modals.openConfirmModal({
      title: "Import now?",
      children: (
        <Text size="sm">
          {run.source_meta.row_count} rows will be imported. You can roll the whole import back afterwards.
        </Text>
      ),
      labels: { confirm: "Import", cancel: "Cancel" },
      onConfirm: () => act(() => command("migration.start_commit", { run_id: run.id })),
    });
  const rollback = () =>
    modals.openConfirmModal({
      title: "Roll back this import?",
      children: (
        <Text size="sm">
          Items, clients and updates created by this import are removed. Records someone has edited since are
          kept.
        </Text>
      ),
      labels: { confirm: "Roll back", cancel: "Cancel" },
      confirmProps: { color: "red" },
      onConfirm: () => act(() => command("migration.rollback", { run_id: run.id })),
    });

  const sample = (h: string) =>
    (run.samples?.[h] ?? Object.keys(run.distinct[h] ?? {})).slice(0, 3).join(", ");
  const targetData = grouped([
    { value: "ignore", label: "Don't import", group: "" },
    ...run.targets.map((t) => ({ value: t.key, label: t.label, group: t.group })),
  ]);
  const report = run.stats?.report;

  return (
    <Page
      title={run.name}
      subtitle={`${run.source_meta.row_count} rows${run.source_meta.encoding ? ` · read as ${run.source_meta.encoding}` : ""} · into ${ctx.boards.get(run.board_id)}`}
      actions={
        <Badge size="lg" variant="light" color={RUN_STATUS[run.status]?.color}>
          {RUN_STATUS[run.status]?.label ?? run.status}
        </Badge>
      }
    >
      <Stack maw={1100} gap="lg">
        <Stepper active={step} size="sm" allowNextStepsSelect={false}>
          <Stepper.Step label="Map columns" />
          <Stepper.Step label="Match values" />
          <Stepper.Step label="Check" />
          <Stepper.Step label="Import" />
        </Stepper>

        {report && (
          <Paper withBorder p="md">
            <Group justify="space-between" mb="xs">
              <Text fw={600}>Import report</Text>
              {run.status !== "rolled_back" && (
                <Button color="red" variant="light" size="xs" loading={busy} onClick={rollback}>
                  Roll back this import
                </Button>
              )}
            </Group>
            <Group gap="xl" mb="sm">
              {Object.entries(report.outcomes as Record<string, number>).map(([k, v]) => (
                <Text key={k} size="sm">
                  {k.replace(/_/g, " ")}: <b>{v}</b>
                </Text>
              ))}
            </Group>
            <Text size="sm" c="dimmed" mb={4}>
              Reconciliation: how many rows had a value in the source, and how many imported items have it
              now.
            </Text>
            <Table>
              <Table.Tbody>
                {(report.columns as any[])
                  .filter((c) => c.target && c.target !== "ignore")
                  .map((c) => (
                    <Table.Tr key={c.header}>
                      <Table.Td>{c.header}</Table.Td>
                      <Table.Td>{targets.get(c.target)?.label ?? c.target}</Table.Td>
                      <Table.Td>{c.source_non_empty}</Table.Td>
                      <Table.Td>
                        {c.imported_non_empty ?? "—"}
                        {c.imported_non_empty != null && c.imported_non_empty !== c.source_non_empty && (
                          <Badge ml={6} size="xs" color="orange" variant="light">
                            differs
                          </Badge>
                        )}
                      </Table.Td>
                    </Table.Tr>
                  ))}
              </Table.Tbody>
            </Table>
          </Paper>
        )}

        <Paper withBorder p="md">
          <Text fw={600} mb={4}>
            Columns
          </Text>
          <Text size="sm" c="dimmed" mb="sm">
            Each column of the source is matched to a field. Client facts (portal access, contact, ABN) go
            onto the client once, and every board shows them.
          </Text>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Source column</Table.Th>
                <Table.Th>Examples</Table.Th>
                <Table.Th w={320}>Import into</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {run.source_meta.headers.map((h) => (
                <Table.Tr key={h}>
                  <Table.Td>
                    <Text size="sm" fw={500}>
                      {h}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" c="dimmed" lineClamp={1}>
                      {sample(h)}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Select
                      size="xs"
                      searchable
                      disabled={locked}
                      data={targetData}
                      value={columns[h] ?? "ignore"}
                      onChange={(v) => setColumns({ ...columns, [h]: v ?? "ignore" })}
                    />
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
          <SimpleGrid cols={{ base: 1, sm: 2 }} mt="md">
            <TextInput
              label="Item name when the source has none"
              description="Use {client}, {board}, {fiscal_year} or any column name in lower case, e.g. {fy/cy}."
              disabled={locked}
              value={options.name_template ?? ""}
              onChange={(e) => setOptions({ ...options, name_template: e.currentTarget.value })}
            />
            <Stack gap={6} mt={22}>
              <Checkbox
                disabled={locked}
                label="Create clients that don't exist yet"
                checked={!!options.create_clients}
                onChange={(e) => setOptions({ ...options, create_clients: e.currentTarget.checked })}
              />
              <Checkbox
                disabled={locked}
                label="Create placeholder people for unknown names"
                checked={!!options.create_placeholder_users}
                onChange={(e) =>
                  setOptions({ ...options, create_placeholder_users: e.currentTarget.checked })
                }
              />
              <Checkbox
                disabled={locked}
                label="Overwrite client facts that are already filled in"
                checked={options.client_fields === "overwrite"}
                onChange={(e) =>
                  setOptions({
                    ...options,
                    client_fields: e.currentTarget.checked ? "overwrite" : "fill_empty",
                  })
                }
              />
            </Stack>
          </SimpleGrid>
        </Paper>

        {Object.keys(run.distinct).length > 0 && (
          <Paper withBorder p="md">
            <Text fw={600} mb={4}>
              Values
            </Text>
            <Text size="sm" c="dimmed" mb="sm">
              Values that already match are not listed. For the rest, pick what they mean, create them, or
              leave the field empty.
            </Text>
            <Stack gap="md">
              {Object.entries(run.distinct).map(([h, counts]) => {
                const t = targets.get(columns[h]);
                if (!t) return null;
                const vm = values[h] ?? {};
                const unknown = Object.keys(counts).filter((raw) => raw in vm);
                if (!unknown.length) return null;
                const opts = [
                  {
                    value: NEW,
                    label: t.type.startsWith("user") ? "Create placeholder person" : "Create as new option",
                  },
                  { value: EMPTY, label: "Leave empty" },
                  ...valueOptions(t, ctx),
                ];
                return (
                  <div key={h}>
                    <Text size="sm" fw={500} mb={4}>
                      {h} → {t.label}
                    </Text>
                    <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="xs">
                      {unknown.map((raw) => (
                        <Group key={raw} gap={6} wrap="nowrap">
                          <Text size="sm" w={150} truncate title={raw}>
                            {raw}{" "}
                            <Text span size="xs" c="dimmed">
                              ×{counts[raw]}
                            </Text>
                          </Text>
                          <Select
                            size="xs"
                            searchable
                            disabled={locked}
                            style={{ flex: 1 }}
                            data={opts}
                            value={vm[raw] ?? null}
                            onChange={(v) => setValues({ ...values, [h]: { ...vm, [raw]: v ?? EMPTY } })}
                          />
                        </Group>
                      ))}
                    </SimpleGrid>
                  </div>
                );
              })}
            </Stack>
          </Paper>
        )}

        {!locked && (
          <Group>
            <Button variant="default" loading={busy} onClick={validate}>
              Save and check
            </Button>
            {pendingNew && (
              <Button variant="light" loading={busy} onClick={prepareAndValidate}>
                Create new values and check
              </Button>
            )}
            <Button
              loading={busy}
              disabled={
                !["validated", "prepared"].includes(run.status) ||
                (pendingNew && run.status !== "prepared") ||
                (run.stats?.error_rows ?? 0) > 0
              }
              onClick={commit}
            >
              Import {run.source_meta.row_count} rows
            </Button>
          </Group>
        )}

        {run.stats && run.status !== "draft" && !report && (
          <Paper withBorder p="md">
            <Text fw={600} mb="xs">
              Check result
            </Text>
            <Group gap="xl">
              <Text size="sm">
                Ready: <b>{run.stats.ok_rows ?? 0}</b>
              </Text>
              <Text size="sm">
                With warnings: <b>{run.stats.warning_rows ?? 0}</b>
              </Text>
              <Text size="sm" c={(run.stats.error_rows ?? 0) > 0 ? "red.7" : undefined}>
                With errors: <b>{run.stats.error_rows ?? 0}</b>
              </Text>
              <Text size="sm">
                New clients: <b>{run.stats.new_clients ?? 0}</b>
              </Text>
            </Group>
            {(run.stats.error_rows ?? 0) > 0 && (
              <Alert color="red" variant="light" mt="sm">
                Rows with errors would not be imported. Fix the mapping above and check again.
              </Alert>
            )}
          </Paper>
        )}

        {(issues.data?.rows.length ?? 0) > 0 && (
          <Paper withBorder p="md">
            <Text fw={600} mb="xs">
              Rows needing attention ({issues.data!.total})
            </Text>
            <ScrollArea h={320}>
              <Table>
                <Table.Tbody>
                  {issues.data!.rows.map((r) => (
                    <Table.Tr key={r.id}>
                      <Table.Td w={60}>#{r.row_no}</Table.Td>
                      <Table.Td w={220}>{r.source_key}</Table.Td>
                      <Table.Td>
                        {r.issues.map((i: any, k: number) => (
                          <Text key={k} size="xs" c={i.level === "error" ? "red.7" : "orange.8"}>
                            {i.column ? `${i.column}: ` : ""}
                            {i.message}
                          </Text>
                        ))}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollArea>
          </Paper>
        )}
      </Stack>
    </Page>
  );
}
