import {
  Badge,
  Center,
  Code,
  Grid,
  Group,
  List,
  Loader,
  NavLink,
  Paper,
  ScrollArea,
  Stack,
  Table,
  Tabs,
  Text,
  TextInput,
  Title,
  UnstyledButton,
} from "@mantine/core";
import { IconKey, IconLink, IconSearch } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { api } from "../../shared/api/client";
import type { DataModel, DataModelTable } from "../../shared/api/types";
import { Page } from "../../shared/ui/Page";

/**
 * Read-only map of how the system stores data, for people who want to
 * understand it. Everything comes from the live schema; no records are shown.
 */
export function DataModelPage() {
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ["data-model"],
    queryFn: () => api.get<DataModel>("/meta/data-model"),
    staleTime: 10 * 60_000,
  });

  return (
    <Page title={t("dataModel.title")} subtitle={t("dataModel.subtitle")}>
      <Stack maw={1200} gap="lg">
        <Paper withBorder p="md">
          <Title order={3} size="h5" mb="xs">
            {t("dataModel.principlesTitle")}
          </Title>
          <List size="sm" spacing={4}>
            {(["p1", "p2", "p3", "p4", "p5"] as const).map((k) => (
              <List.Item key={k}>{t(`dataModel.${k}`)}</List.Item>
            ))}
          </List>
        </Paper>
        {!q.data ? (
          <Center py="xl">
            <Loader />
          </Center>
        ) : (
          <Tabs defaultValue="tables" keepMounted={false}>
            <Tabs.List>
              <Tabs.Tab value="tables">{t("dataModel.tabTables")}</Tabs.Tab>
              <Tabs.Tab value="fields">{t("dataModel.tabFields")}</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value="tables" pt="md">
              <TablesView model={q.data} />
            </Tabs.Panel>
            <Tabs.Panel value="fields" pt="md">
              <FieldsView model={q.data} />
            </Tabs.Panel>
          </Tabs>
        )}
      </Stack>
    </Page>
  );
}

function TablesView({ model }: { model: DataModel }) {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const byName = useMemo(() => new Map(model.tables.map((tb) => [tb.name, tb])), [model]);
  const selected = byName.get(params.get("table") ?? "") ?? byName.get("items") ?? model.tables[0];
  const select = (name: string) =>
    setParams(
      (p) => {
        p.set("table", name);
        return p;
      },
      { replace: true },
    );

  const needle = search.trim().toLowerCase();
  const visible = model.tables.filter(
    (tb) =>
      !needle || tb.name.includes(needle) || tb.columns.some((c) => c.name.toLowerCase().includes(needle)),
  );
  const modules = [...new Set(visible.map((tb) => tb.module))];

  return (
    <Grid gutter="md">
      <Grid.Col span={{ base: 12, md: 3 }}>
        <TextInput
          size="xs"
          leftSection={<IconSearch size={14} />}
          placeholder={t("dataModel.search")}
          value={search}
          onChange={(e) => setSearch(e.currentTarget.value)}
          mb="xs"
        />
        <ScrollArea.Autosize mah="70vh">
          {modules.length === 0 && (
            <Text size="sm" c="dimmed">
              {t("dataModel.noMatch")}
            </Text>
          )}
          {modules.map((m) => (
            <div key={m}>
              <Text size="xs" c="dimmed" fw={600} tt="uppercase" mt="sm" mb={2}>
                {t(`dataModel.modules.${m}`, m)}
              </Text>
              {visible
                .filter((tb) => tb.module === m)
                .map((tb) => (
                  <NavLink
                    key={tb.name}
                    label={<Code bg="transparent">{tb.name}</Code>}
                    active={tb.name === selected?.name}
                    onClick={() => select(tb.name)}
                    py={4}
                  />
                ))}
            </div>
          ))}
        </ScrollArea.Autosize>
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 9 }}>
        {selected && <TableDetail table={selected} all={model.tables} onSelect={select} />}
      </Grid.Col>
    </Grid>
  );
}

function TableLink({ name, onSelect }: { name: string; onSelect: (n: string) => void }) {
  return (
    <UnstyledButton onClick={() => onSelect(name)}>
      <Code c="blue.7">{name}</Code>
    </UnstyledButton>
  );
}

function TableDetail({
  table,
  all,
  onSelect,
}: {
  table: DataModelTable;
  all: DataModelTable[];
  onSelect: (n: string) => void;
}) {
  const { t } = useTranslation();
  const linkedFrom = all.flatMap((other) =>
    other.columns
      .filter((c) => c.references?.table === table.name)
      .map((c) => ({ table: other.name, column: c.name })),
  );
  return (
    <Paper withBorder p="md">
      <Group gap="xs" mb={4}>
        <Title order={2} size="h4" ff="monospace">
          {table.name}
        </Title>
        <Badge variant="light" color="gray">
          {t(`dataModel.modules.${table.module}`, table.module)}
        </Badge>
        {table.audited && <Badge variant="light">{t("dataModel.audited")}</Badge>}
        {table.soft_delete && (
          <Badge variant="light" color="orange">
            {t("dataModel.softDelete")}
          </Badge>
        )}
        {table.has_custom_data && (
          <Badge variant="light" color="teal">
            {t("dataModel.customData")}
          </Badge>
        )}
      </Group>
      <Text size="sm" mb={2}>
        {t(`dataModel.tables.${table.name}`, table.description ?? "")}
      </Text>
      <Text size="xs" c="dimmed" mb="md">
        {t("dataModel.model", { model: table.model })}
      </Text>

      <Table.ScrollContainer minWidth={640}>
        <Table striped fz="sm" verticalSpacing={4}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t("dataModel.column")}</Table.Th>
              <Table.Th>{t("dataModel.type")}</Table.Th>
              <Table.Th>{t("dataModel.required")}</Table.Th>
              <Table.Th>{t("dataModel.references")}</Table.Th>
              <Table.Th>{t("dataModel.notes")}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {table.columns.map((c) => (
              <Table.Tr key={c.name}>
                <Table.Td>
                  <Group gap={4} wrap="nowrap">
                    {c.primary_key && <IconKey size={13} aria-label={t("dataModel.pk")} />}
                    {c.references && <IconLink size={13} />}
                    <Code bg="transparent">{c.name}</Code>
                  </Group>
                </Table.Td>
                <Table.Td>
                  <Text size="xs" ff="monospace">
                    {c.type}
                  </Text>
                </Table.Td>
                <Table.Td>{c.nullable ? "" : "✓"}</Table.Td>
                <Table.Td>
                  {c.references && (
                    <Group gap={4} wrap="nowrap">
                      <TableLink name={c.references.table} onSelect={onSelect} />
                      {c.references.on_delete && (
                        <Text size="xs" c="dimmed">
                          {t("dataModel.onDelete", { action: c.references.on_delete })}
                        </Text>
                      )}
                    </Group>
                  )}
                </Table.Td>
                <Table.Td>
                  <Text size="xs" c="dimmed">
                    {[
                      c.primary_key && t("dataModel.pk"),
                      c.unique && !c.primary_key && t("dataModel.unique"),
                      c.indexed && t("dataModel.indexed"),
                      c.has_default && t("dataModel.default"),
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </Text>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>

      {table.unique_together.length > 0 && (
        <>
          <Text size="sm" fw={600} mt="md" mb={4}>
            {t("dataModel.uniqueTogether")}
          </Text>
          <Stack gap={2}>
            {table.unique_together.map((cols) => (
              <Code key={cols.join(",")}>({cols.join(", ")})</Code>
            ))}
          </Stack>
        </>
      )}

      <Text size="sm" fw={600} mt="md" mb={4}>
        {t("dataModel.referencedBy")}
      </Text>
      {linkedFrom.length === 0 ? (
        <Text size="sm" c="dimmed">
          {t("dataModel.nothingLinks")}
        </Text>
      ) : (
        <Group gap="xs">
          {linkedFrom.map((l) => (
            <Group key={`${l.table}.${l.column}`} gap={2} wrap="nowrap">
              <TableLink name={l.table} onSelect={onSelect} />
              <Text size="xs" c="dimmed">
                .{l.column}
              </Text>
            </Group>
          ))}
        </Group>
      )}
    </Paper>
  );
}

const KIND_ORDER = ["item", "task", "client", "entity", "contact"];

function FieldsView({ model }: { model: DataModel }) {
  const { t } = useTranslation();
  if (model.custom_fields.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        {t("dataModel.noFields")}
      </Text>
    );
  }
  return (
    <Stack gap="lg">
      <Text size="sm" c="dimmed">
        {t("dataModel.fieldsIntro")}
      </Text>
      {model.custom_fields.map(({ workspace, fields }) => (
        <Paper key={workspace.id} withBorder p="md">
          <Title order={3} size="h5" mb="sm">
            {workspace.name}
          </Title>
          {fields.length === 0 && (
            <Text size="sm" c="dimmed">
              {t("dataModel.noFields")}
            </Text>
          )}
          {KIND_ORDER.filter((k) => fields.some((f) => f.entity_kind === k)).map((kind) => (
            <div key={kind}>
              <Text size="sm" fw={600} mt="sm" mb={4}>
                {t(`dataModel.kinds.${kind}`, kind)}
              </Text>
              <Table.ScrollContainer minWidth={600}>
                <Table fz="sm" verticalSpacing={4}>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th w="30%">{t("dataModel.label")}</Table.Th>
                      <Table.Th w="22%">{t("dataModel.key")}</Table.Th>
                      <Table.Th w="16%">{t("dataModel.type")}</Table.Th>
                      <Table.Th>{t("dataModel.storedIn")}</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {fields
                      .filter((f) => f.entity_kind === kind)
                      .map((f) => (
                        <Table.Tr key={f.key} c={f.is_archived ? "dimmed" : undefined}>
                          <Table.Td>
                            {f.label}
                            {f.is_archived && (
                              <Text span size="xs" c="dimmed">
                                {" "}
                                ({t("dataModel.archived")})
                              </Text>
                            )}
                          </Table.Td>
                          <Table.Td>
                            <Code bg="transparent">{f.key}</Code>
                          </Table.Td>
                          <Table.Td>{model.field_types[f.type] ?? f.type}</Table.Td>
                          <Table.Td>
                            {f.mirror_of ? (
                              <Text size="xs" c="dimmed">
                                {t("dataModel.mirrorOf", {
                                  of: f.mirror_of.of ?? "?",
                                  field: f.mirror_of.field ?? "?",
                                })}
                              </Text>
                            ) : f.stored_in ? (
                              <Code>
                                {f.stored_in} → "{f.key}"
                              </Code>
                            ) : (
                              <Text size="xs" c="orange.8">
                                {t("dataModel.notStored")}
                              </Text>
                            )}
                          </Table.Td>
                        </Table.Tr>
                      ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            </div>
          ))}
        </Paper>
      ))}
    </Stack>
  );
}
