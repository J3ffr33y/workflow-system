import {
  Alert,
  Badge,
  Button,
  Center,
  Checkbox,
  Group,
  Loader,
  Paper,
  Progress,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Stepper,
  Table,
  Text,
  TextInput,
  ThemeIcon,
} from "@mantine/core";
import { IconArrowLeft, IconArrowRight, IconCheck, IconInfoCircle } from "@tabler/icons-react";
import { modals } from "@mantine/modals";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
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

// The four screens of an import. Nothing is written to boards before "Import".
const STEPS = ["columns", "values", "check", "import"] as const;
type Step = (typeof STEPS)[number];

function initialStep(status: string): Step {
  if (status === "draft") return "columns";
  if (status === "validated" || status === "prepared") return "check";
  return "import";
}

function Stat({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <Paper withBorder p="sm" radius="md">
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text size="xl" fw={600} c={color}>
        {value}
      </Text>
    </Paper>
  );
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
  const [step, setStep] = useState<Step | null>(null);

  useEffect(() => {
    if (q.data) {
      setColumns(q.data.mapping.columns);
      setValues(q.data.mapping.values);
      setOptions(q.data.mapping.options);
      setStep((s) => {
        const locked = ["committing", "committed", "committed_with_errors", "rolled_back"].includes(
          q.data.status,
        );
        return locked ? "import" : (s ?? initialStep(q.data.status));
      });
    }
  }, [q.data]);

  if (!q.data || !ctx || !step)
    return (
      <Center h="100%">
        <Loader />
      </Center>
    );
  const run = q.data;
  const targets = new Map(run.targets.map((t) => [t.key, t]));
  const locked = ["committing", "committed", "committed_with_errors", "rolled_back"].includes(run.status);
  const checked = run.status === "validated" || run.status === "prepared";
  const errorRows = run.stats?.error_rows ?? 0;

  // Source values that don't match anything yet, per column (what step 2 asks about).
  const unmatched = Object.entries(run.distinct)
    .map(([h, counts]) => {
      const t = targets.get(columns[h]);
      const vm = values[h] ?? {};
      return { h, t, counts, raws: t ? Object.keys(counts).filter((raw) => raw in vm) : [] };
    })
    .filter((u) => u.t && u.raws.length);
  const unmatchedCount = unmatched.reduce((n, u) => n + u.raws.length, 0);
  const pendingNew = Object.values(values).some((vm) => Object.values(vm).includes(NEW));

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: ["migration-run", runId] });
      qc.invalidateQueries({ queryKey: ["migration-rows", runId] });
      return true;
    } catch (e) {
      notifyError(e, "Step failed");
      return false;
    } finally {
      setBusy(false);
    }
  };
  const saveMapping = () => command("migration.update_mapping", { run_id: run.id, columns, values, options });

  // Step 1 -> 2: save the column choices; the server works out which values are unknown.
  const toValues = async () => {
    if (await act(saveMapping)) setStep("values");
  };
  // Step 2 -> 3: create the new options / placeholder people if asked, then check every row.
  const toCheck = async () => {
    const ok = await act(async () => {
      await saveMapping();
      await command("migration.validate", { run_id: run.id });
      if (pendingNew) {
        await command("migration.prepare", { run_id: run.id });
        await command("migration.validate", { run_id: run.id });
        // New placeholder people / options must show up in pickers.
        qc.invalidateQueries({ queryKey: ["directory"] });
        qc.invalidateQueries({ queryKey: ["schema"] });
      }
    });
    if (ok) setStep("check");
  };
  const commit = () =>
    modals.openConfirmModal({
      title: "Import now?",
      children: (
        <Text size="sm">
          {run.source_meta.row_count} rows will be written to {ctx.boards.get(run.board_id)}. You can roll the
          whole import back afterwards.
        </Text>
      ),
      labels: { confirm: "Import", cancel: "Cancel" },
      onConfirm: () =>
        act(async () => {
          await command("migration.start_commit", { run_id: run.id });
          setStep("import");
        }),
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
  const imported = Object.values(columns).filter((t) => t !== "ignore").length;
  const index = STEPS.indexOf(step);
  // Going back is always allowed before the import; going forward only through the buttons,
  // so every step's work (save, create values, check) actually runs.
  const goTo = (i: number) => !locked && i < index && setStep(STEPS[i]);

  const footer = (children: React.ReactNode) => (
    <Paper
      withBorder
      p="sm"
      style={{ position: "sticky", bottom: 0, zIndex: 2, background: "var(--mantine-color-body)" }}
    >
      <Group justify="space-between">{children}</Group>
    </Paper>
  );
  const back = (to: Step) => (
    <Button variant="default" leftSection={<IconArrowLeft size={16} />} onClick={() => setStep(to)}>
      Back
    </Button>
  );

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
        <Stepper
          active={run.status.startsWith("committed") ? STEPS.length : index}
          onStepClick={goTo}
          size="sm"
          allowNextStepsSelect={false}
        >
          <Stepper.Step label="1. Map columns" description="Which field each column goes to" />
          <Stepper.Step label="2. Match values" description="Unknown names and options" />
          <Stepper.Step label="3. Check" description="Dry run, nothing written" />
          <Stepper.Step label="4. Import" description="Write to the board" />
        </Stepper>

        {!locked && (
          <Alert variant="light" color="blue" icon={<IconInfoCircle size={18} />}>
            Steps 1 to 3 only prepare the import. Nothing appears on the board until you press <b>Import</b>{" "}
            in step 4, and every import can be rolled back.
          </Alert>
        )}

        {step === "columns" && (
          <>
            <Paper withBorder p="md">
              <Text fw={600} mb={4}>
                Where should each column go?
              </Text>
              <Text size="sm" c="dimmed" mb="sm">
                We matched columns by name; check the right-hand side. Client facts (portal access, contact,
                ABN, State) go onto the client once, and every board shows them.
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
                    <Table.Tr key={h} style={{ opacity: (columns[h] ?? "ignore") === "ignore" ? 0.55 : 1 }}>
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
                          data={targetData}
                          value={columns[h] ?? "ignore"}
                          onChange={(v) => setColumns({ ...columns, [h]: v ?? "ignore" })}
                        />
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Paper>
            <Paper withBorder p="md">
              <Text fw={600} mb="sm">
                Options
              </Text>
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                <TextInput
                  label="Item name when the source has none"
                  description="Use {client}, {board}, {fiscal_year} or any column name in lower case, e.g. {fy/cy}."
                  value={options.name_template ?? ""}
                  onChange={(e) => setOptions({ ...options, name_template: e.currentTarget.value })}
                />
                <Stack gap={6} mt={22}>
                  <Checkbox
                    label="Create clients that don't exist yet"
                    checked={!!options.create_clients}
                    onChange={(e) => setOptions({ ...options, create_clients: e.currentTarget.checked })}
                  />
                  <Checkbox
                    label="Create placeholder people for unknown names"
                    checked={!!options.create_placeholder_users}
                    onChange={(e) =>
                      setOptions({ ...options, create_placeholder_users: e.currentTarget.checked })
                    }
                  />
                  <Checkbox
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
            {footer(
              <>
                <Text size="sm" c="dimmed">
                  {imported} of {run.source_meta.headers.length} columns will be imported
                </Text>
                <Button loading={busy} rightSection={<IconArrowRight size={16} />} onClick={toValues}>
                  Next: match values
                </Button>
              </>,
            )}
          </>
        )}

        {step === "values" && (
          <>
            <Paper withBorder p="md">
              <Text fw={600} mb={4}>
                Values we don't recognise
              </Text>
              {unmatched.length === 0 ? (
                <Group gap="xs">
                  <ThemeIcon color="teal" variant="light" radius="xl" size="sm">
                    <IconCheck size={14} />
                  </ThemeIcon>
                  <Text size="sm">
                    Every status, option and person in the file already exists. Nothing to do here.
                  </Text>
                </Group>
              ) : (
                <>
                  <Text size="sm" c="dimmed" mb="md">
                    {unmatchedCount} value{unmatchedCount === 1 ? "" : "s"} in the file don't match anything
                    in this system yet. For each one, pick what it means, create it, or leave the field empty.
                    Values that already match are not listed.
                  </Text>
                  <Stack gap="md">
                    {unmatched.map(({ h, t, counts, raws }) => {
                      const vm = values[h] ?? {};
                      const opts = [
                        {
                          value: NEW,
                          label: t!.type.startsWith("user")
                            ? "Create placeholder person"
                            : "Create as new option",
                        },
                        { value: EMPTY, label: "Leave empty" },
                        ...valueOptions(t!, ctx),
                      ];
                      return (
                        <div key={h}>
                          <Text size="sm" fw={500} mb={4}>
                            {h} → {t!.label}
                          </Text>
                          <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="xs">
                            {raws.map((raw) => (
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
                                  style={{ flex: 1 }}
                                  data={opts}
                                  value={vm[raw] ?? null}
                                  onChange={(v) =>
                                    setValues({ ...values, [h]: { ...vm, [raw]: v ?? EMPTY } })
                                  }
                                />
                              </Group>
                            ))}
                          </SimpleGrid>
                        </div>
                      );
                    })}
                  </Stack>
                </>
              )}
            </Paper>
            {footer(
              <>
                {back("columns")}
                <Group gap="sm">
                  {pendingNew && (
                    <Text size="sm" c="dimmed">
                      New options and placeholder people are created when you continue.
                    </Text>
                  )}
                  <Button loading={busy} rightSection={<IconArrowRight size={16} />} onClick={toCheck}>
                    Next: check rows
                  </Button>
                </Group>
              </>,
            )}
          </>
        )}

        {step === "check" && (
          <>
            <Paper withBorder p="md">
              <Text fw={600} mb={4}>
                Dry run result
              </Text>
              <Text size="sm" c="dimmed" mb="sm">
                Every row was checked against the mapping. Nothing has been written yet.
              </Text>
              {!checked || !run.stats ? (
                <Text size="sm">Not checked yet. Go back and press "Next" to run the check.</Text>
              ) : (
                <>
                  <SimpleGrid cols={{ base: 2, sm: 4 }}>
                    <Stat label="Ready to import" value={run.stats.ok_rows ?? 0} color="teal.7" />
                    <Stat
                      label="With warnings"
                      value={run.stats.warning_rows ?? 0}
                      color={run.stats.warning_rows ? "orange.7" : undefined}
                    />
                    <Stat label="With errors" value={errorRows} color={errorRows ? "red.7" : undefined} />
                    <Stat label="New clients" value={run.stats.new_clients ?? 0} />
                  </SimpleGrid>
                  {errorRows > 0 ? (
                    <Alert color="red" variant="light" mt="sm">
                      {errorRows} row{errorRows === 1 ? " has" : "s have"} errors (listed below). Go back, fix
                      the column or value mapping, and check again. Import stays disabled until there are no
                      errors.
                    </Alert>
                  ) : (
                    (run.stats.warning_rows ?? 0) > 0 && (
                      <Alert color="orange" variant="light" mt="sm">
                        Rows with warnings will be imported; the listed values are left empty.
                      </Alert>
                    )
                  )}
                </>
              )}
            </Paper>
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
            {footer(
              <>
                {back(unmatched.length ? "values" : "columns")}
                <Button
                  loading={busy}
                  disabled={!checked || errorRows > 0}
                  rightSection={<IconArrowRight size={16} />}
                  onClick={commit}
                >
                  Import {run.source_meta.row_count} rows
                </Button>
              </>,
            )}
          </>
        )}

        {step === "import" && (
          <Paper withBorder p="md">
            {run.status === "committing" && (
              <Stack gap="xs">
                <Text fw={600}>Importing…</Text>
                <Progress value={100} animated striped />
                <Text size="sm" c="dimmed">
                  You can leave this page; the import keeps running in the background.
                </Text>
              </Stack>
            )}
            {report && (
              <>
                <Group justify="space-between" mb="xs">
                  <Text fw={600}>Import report</Text>
                  <Group gap="xs">
                    {run.status !== "rolled_back" && (
                      <Button
                        size="xs"
                        variant="light"
                        component={Link}
                        to={`../../b/${run.board_id}`}
                        relative="path"
                      >
                        Open the board
                      </Button>
                    )}
                    {run.status !== "rolled_back" && (
                      <Button color="red" variant="light" size="xs" loading={busy} onClick={rollback}>
                        Roll back this import
                      </Button>
                    )}
                  </Group>
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
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Source column</Table.Th>
                      <Table.Th>Field</Table.Th>
                      <Table.Th>Rows with a value</Table.Th>
                      <Table.Th>Imported items with a value</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
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
              </>
            )}
          </Paper>
        )}
      </Stack>
    </Page>
  );
}
