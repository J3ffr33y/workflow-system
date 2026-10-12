import { Anchor, Badge, Group, Paper, SegmentedControl, Stack, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../../shared/api/client";
import { useMe } from "../../shared/api/hooks";
import { fmtDate } from "../../shared/fields/format";

type Bucket = "overdue" | "this_week" | "later" | "no_date";

interface MyTask {
  id: string;
  title: string;
  status: string | null;
  status_label: string;
  status_color: string;
  priority: string | null;
  due_date: string | null;
  bucket: Bucket;
  my_roles: string[];
  workspace_id: string;
  item_id: string;
  item_name: string;
  board_id: string;
  board_name: string;
}

const BUCKETS: Bucket[] = ["overdue", "this_week", "later", "no_date"];

/** Tasks assigned to the signed-in user, grouped by when they are due. */
export function MyTasks() {
  const { t } = useTranslation();
  const me = useMe();
  const q = useQuery({ queryKey: ["home", "tasks"], queryFn: () => api.get<MyTask[]>("/home/tasks") });
  const tasks = q.data ?? [];
  const counts = Object.fromEntries(BUCKETS.map((b) => [b, tasks.filter((x) => x.bucket === b).length]));
  // Open on the most urgent group that has something in it.
  const [picked, setPicked] = useState<Bucket | "all" | null>(null);
  const bucket = picked ?? BUCKETS.find((b) => counts[b]) ?? "all";
  const shown = bucket === "all" ? tasks : tasks.filter((x) => x.bucket === bucket);
  const wsKey = (id: string) => me.data?.workspaces.find((w) => w.id === id)?.key ?? "x";

  return (
    <section>
      <Group justify="space-between" mb="sm" wrap="wrap">
        <Title order={2} size="h4">
          {t("myWork.tasks.title")}
        </Title>
        {tasks.length > 0 && (
          <SegmentedControl
            size="xs"
            value={bucket}
            onChange={(v) => setPicked(v as Bucket | "all")}
            data={[
              ...BUCKETS.map((b) => ({ value: b, label: `${t(`myWork.tasks.${b}`)} ${counts[b]}` })),
              { value: "all", label: `${t("myWork.tasks.all")} ${tasks.length}` },
            ]}
          />
        )}
      </Group>
      {q.data && !tasks.length ? (
        <Paper withBorder p="lg">
          <Text c="dimmed" size="sm">
            {t("myWork.tasks.empty")}
          </Text>
        </Paper>
      ) : (
        <Table withTableBorder style={{ background: "var(--surface)" }}>
          <Table.Tbody>
            {shown.map((x) => (
              <Table.Tr key={x.id}>
                <Table.Td w={120}>
                  <Text
                    size="sm"
                    c={x.bucket === "overdue" ? "red.7" : undefined}
                    fw={x.bucket === "overdue" ? 600 : 400}
                  >
                    {x.due_date ? fmtDate(x.due_date) : "—"}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Stack gap={0}>
                    <Text size="sm" fw={500}>
                      {x.title}
                    </Text>
                    <Anchor
                      component={Link}
                      to={`/w/${wsKey(x.workspace_id)}/b/${x.board_id}?item=${x.item_id}`}
                      size="xs"
                    >
                      {x.item_name}
                    </Anchor>
                  </Stack>
                </Table.Td>
                <Table.Td visibleFrom="sm">
                  <Text size="sm" c="dimmed">
                    {x.board_name}
                  </Text>
                </Table.Td>
                <Table.Td w={140}>
                  <Badge color={x.status_color} variant="light">
                    {x.status_label || "—"}
                  </Badge>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </section>
  );
}
