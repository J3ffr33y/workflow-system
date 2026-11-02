import { Badge, Button, Group, HoverCard, Paper, Select, Stack, Table, Text, Tooltip } from "@mantine/core";
import { IconPlayerPlay } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { command } from "../../shared/api/client";
import { notifyError } from "../../shared/api/hooks";
import { useElementLabel, usePassages, useRefreshRdti } from "./hooks";
import { COVERAGE_COLOR, type Activity, type Coverage, type Workbench } from "./types";

export function EvidenceTab({ data, activity }: { data: Workbench; activity: Activity | null }) {
  const { t } = useTranslation();
  const refresh = useRefreshRdti(data.item.id);
  const label = useElementLabel();
  const [busy, setBusy] = useState(false);
  if (!activity) return <Text c="dimmed">{t("rdti.evidence.pick")}</Text>;
  const rows = data.assessments[activity.id] ?? [];
  const byKey = new Map(rows.map((r) => [r.element, r]));
  const elements = data.rules.elements.filter((e) => e.applies_to.includes(activity.kind));

  const run = async () => {
    setBusy(true);
    try {
      await command("rdti.assess_activity", { activity_id: activity.id } as any);
      refresh();
    } catch (e) {
      notifyError(e, "Assessment failed");
    } finally {
      setBusy(false);
    }
  };

  const setCoverage = (element: string, coverage: Coverage) =>
    command("rdti.set_assessment", { activity_id: activity.id, element, coverage } as any)
      .then(refresh)
      .catch((e) => notifyError(e));

  return (
    <Paper withBorder p="md" radius="md">
      <Group justify="space-between" mb="sm">
        <Text fw={600}>
          {activity.code} {activity.title}
        </Text>
        {data.can_write && (
          <Button leftSection={<IconPlayerPlay size={16} />} onClick={run} loading={busy}>
            {rows.length ? t("rdti.evidence.rerun") : t("rdti.evidence.run")}
          </Button>
        )}
      </Group>
      <Table verticalSpacing="sm">
        <Table.Thead>
          <Table.Tr>
            <Table.Th w="22%">{t("rdti.evidence.element")}</Table.Th>
            <Table.Th w={150}>{t("rdti.evidence.coverage")}</Table.Th>
            <Table.Th>{t("rdti.evidence.why")}</Table.Th>
            <Table.Th w={90}>{t("rdti.evidence.passages")}</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {elements.map((el) => {
            const a = byKey.get(el.key);
            return (
              <Table.Tr key={el.key}>
                <Table.Td>
                  <Tooltip label={el.question} multiline w={320}>
                    <Text size="sm" fw={500}>
                      {label(el, el.key)}
                    </Text>
                  </Tooltip>
                </Table.Td>
                <Table.Td>
                  {data.can_write ? (
                    <Select
                      size="xs"
                      placeholder="—"
                      value={a?.coverage ?? null}
                      data={(["sufficient", "partial", "missing"] as Coverage[]).map((c) => ({
                        value: c,
                        label: t(`rdti.evidence.${c}`),
                      }))}
                      onChange={(v) => v && setCoverage(el.key, v as Coverage)}
                      allowDeselect={false}
                      styles={{
                        input: {
                          color: a ? `var(--mantine-color-${COVERAGE_COLOR[a.coverage]}-8)` : undefined,
                          fontWeight: 600,
                        },
                      }}
                    />
                  ) : a ? (
                    <Badge color={COVERAGE_COLOR[a.coverage]}>{t(`rdti.evidence.${a.coverage}`)}</Badge>
                  ) : (
                    "—"
                  )}
                </Table.Td>
                <Table.Td>
                  {a ? (
                    <Stack gap={2}>
                      <Text size="sm">{a.rationale}</Text>
                      <Group gap={4}>
                        {a.summary_only && (
                          <Badge size="xs" color="orange" variant="light">
                            {t("rdti.evidence.summaryOnly")}
                          </Badge>
                        )}
                        {a.source === "human" && (
                          <Badge size="xs" color="gray" variant="light">
                            {t("rdti.evidence.human")}
                          </Badge>
                        )}
                      </Group>
                    </Stack>
                  ) : (
                    <Text size="sm" c="dimmed">
                      {t("rdti.evidence.none")}
                    </Text>
                  )}
                </Table.Td>
                <Table.Td>
                  {a && a.chunk_ids.length > 0 ? (
                    <EvidencePeek itemId={data.item.id} ids={a.chunk_ids} />
                  ) : (
                    "—"
                  )}
                </Table.Td>
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>
    </Paper>
  );
}

function EvidencePeek({ itemId, ids }: { itemId: string; ids: string[] }) {
  const [open, setOpen] = useState(false);
  const list = usePassages(itemId, { ids: ids.join(",") }, open);
  return (
    <HoverCard width={460} shadow="md" openDelay={150} onOpen={() => setOpen(true)}>
      <HoverCard.Target>
        <Badge variant="light" style={{ cursor: "help" }}>
          {ids.length}
        </Badge>
      </HoverCard.Target>
      <HoverCard.Dropdown>
        <Stack gap={8} mah={360} style={{ overflow: "auto" }}>
          {(list.data ?? []).map((p) => (
            <div key={p.id}>
              <Text size="xs" c="dimmed">
                {p.file_name} · {p.location}
              </Text>
              <Text size="sm">{p.text}</Text>
            </div>
          ))}
        </Stack>
      </HoverCard.Dropdown>
    </HoverCard>
  );
}
