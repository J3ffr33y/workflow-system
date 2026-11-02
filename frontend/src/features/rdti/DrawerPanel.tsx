import { Button, Group, Loader, Stack, Text } from "@mantine/core";
import { IconArrowRight } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useWorkbench } from "./hooks";

/** Short status of the R&D report inside the item drawer; the work itself
 * happens on the full-page workbench, which needs the room. */
export function RdtiDrawerPanel({ itemId }: { itemId: string }) {
  const { t } = useTranslation();
  const wb = useWorkbench(itemId);
  if (wb.isLoading) return <Loader size="sm" />;
  const d = wb.data;
  if (!d) return null;
  const gaps = Object.values(d.assessments)
    .flat()
    .filter((a) => a.coverage !== "sufficient").length;
  const open = d.checklist.filter((c) => c.status === "draft" || c.status === "sent").length;
  return (
    <Stack gap="sm">
      <Text size="sm">
        {t("rdti.summary", { activities: d.activities.length, documents: d.documents.length, gaps, open })}
      </Text>
      <Group>
        <Button component={Link} to={`/rdti/${itemId}`} rightSection={<IconArrowRight size={16} />}>
          {t("rdti.openWorkbench")}
        </Button>
      </Group>
    </Stack>
  );
}
