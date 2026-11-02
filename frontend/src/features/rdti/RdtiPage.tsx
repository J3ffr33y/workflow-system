import { Alert, Anchor, Badge, Center, Grid, Loader, Paper, Tabs, Text } from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Page } from "../../shared/ui/Page";
import { ActivityList } from "./ActivityList";
import { ChecklistTab } from "./ChecklistTab";
import { EvidenceTab } from "./EvidenceTab";
import { MaterialsTab } from "./MaterialsTab";
import { ReportTab } from "./ReportTab";
import { useWorkbench } from "./hooks";

/** R&D report workbench for one Grants project: material -> evidence -> checklist -> report. */
export function RdtiPage() {
  const { itemId = "" } = useParams();
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const wb = useWorkbench(itemId);
  const [activityId, setActivityId] = useState<string | null>(null);
  const tab = params.get("tab") ?? "materials";

  if (wb.isLoading) {
    return (
      <Center h="60vh">
        <Loader />
      </Center>
    );
  }
  if (!wb.data) {
    return (
      <Center h="60vh">
        <Text c="dimmed">{wb.error ? String(wb.error) : ""}</Text>
      </Center>
    );
  }
  const data = wb.data;
  const current = data.activities.find((a) => a.id === activityId) ?? data.activities[0] ?? null;

  return (
    <Page
      title={`${t("rdti.title")} · ${data.item.name}`}
      subtitle={
        <>
          {data.item.client_name && (
            <Anchor component={Link} to={`/clients/${data.item.client_id}`} size="sm">
              {data.item.client_name}
            </Anchor>
          )}
          {data.item.client_name && " · "}
          <Anchor component={Link} to={`?item=${data.item.id}`} size="sm">
            {data.item.name}
          </Anchor>
        </>
      }
      actions={
        <Badge variant="light" color={data.ai.external ? "indigo" : "gray"}>
          AI: {data.ai.model}
        </Badge>
      }
    >
      {!data.enabled && <Alert color="gray">{t("rdti.notEnabled")}</Alert>}
      <Alert color={data.ai.external ? "indigo" : "gray"} variant="light" mb="sm" py={8}>
        {data.ai.external ? t("rdti.aiExternal", { model: data.ai.model }) : t("rdti.aiFake")}
      </Alert>
      {data.ai.external && !data.item.ai_consent && (
        <Alert color="orange" variant="light" mb="sm" py={8}>
          {t("rdti.noConsent")}
        </Alert>
      )}
      <Grid gutter="md">
        <Grid.Col span={{ base: 12, md: 3 }}>
          <Paper withBorder p="sm" radius="md">
            <ActivityList data={data} selected={current?.id ?? null} onSelect={setActivityId} />
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 9 }}>
          <Tabs
            value={tab}
            onChange={(v) => {
              params.set("tab", v ?? "materials");
              setParams(params, { replace: true });
            }}
            keepMounted={false}
          >
            <Tabs.List mb="md">
              <Tabs.Tab value="materials">{t("rdti.tabs.materials")}</Tabs.Tab>
              <Tabs.Tab value="evidence">{t("rdti.tabs.evidence")}</Tabs.Tab>
              <Tabs.Tab value="checklist">{t("rdti.tabs.checklist")}</Tabs.Tab>
              <Tabs.Tab value="report">{t("rdti.tabs.report")}</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value="materials">
              <MaterialsTab data={data} />
            </Tabs.Panel>
            <Tabs.Panel value="evidence">
              <EvidenceTab data={data} activity={current} />
            </Tabs.Panel>
            <Tabs.Panel value="checklist">
              <ChecklistTab data={data} />
            </Tabs.Panel>
            <Tabs.Panel value="report">
              <ReportTab data={data} activity={current} />
            </Tabs.Panel>
          </Tabs>
        </Grid.Col>
      </Grid>
    </Page>
  );
}
