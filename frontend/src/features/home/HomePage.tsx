import { Anchor, Badge, Group, Paper, SimpleGrid, Stack, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../../shared/api/client";
import { useMe } from "../../shared/api/hooks";
import { fmtDate } from "../../shared/fields/format";
import { Page } from "../../shared/ui/Page";
import classes from "./home.module.css";

interface Home {
  workspaces: {
    workspace_id: string;
    workspace_key: string;
    workspace_name: string;
    total: number;
    by_status: { status: string; label: string; color: string; category: string; count: number }[];
  }[];
  due_soon: {
    id: string;
    name: string;
    workspace_id: string;
    board_id: string;
    board_name: string;
    due_date: string;
    overdue: boolean;
  }[];
}

export function HomePage() {
  const me = useMe();
  const q = useQuery({ queryKey: ["home"], queryFn: () => api.get<Home>("/home") });
  const first = me.data?.user.full_name.split(" ")[0];
  const wsKey = (id: string) => me.data?.workspaces.find((w) => w.id === id)?.key ?? "";

  return (
    <Page
      title={`Good to see you, ${first ?? ""}`}
      subtitle="Work where you are on the team, across both product lines."
    >
      <Stack gap="xl" maw={1100}>
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          {(q.data?.workspaces ?? []).map((w) => (
            <Paper key={w.workspace_id} withBorder p="lg" radius="md">
              <Group justify="space-between" mb="sm">
                <Title order={3} size="h4">
                  {w.workspace_name}
                </Title>
                <Text size="sm" c="dimmed">
                  {w.total} items
                </Text>
              </Group>
              {/* A single stacked bar: the shape of your workload at a glance. */}
              <div className={classes.bar} role="img" aria-label="Items by status">
                {w.by_status.map((s) => (
                  <span
                    key={s.status}
                    title={`${s.label}: ${s.count}`}
                    style={{
                      flex: s.count,
                      background: `var(--mantine-color-${s.color}-${s.color === "gray" ? 4 : 6})`,
                    }}
                  />
                ))}
              </div>
              <Stack gap={4} mt="md">
                {w.by_status.map((s) => (
                  <Group key={s.status} justify="space-between" className={classes.row}>
                    <Group gap={8}>
                      <span
                        className={classes.dot}
                        style={{ background: `var(--mantine-color-${s.color}-6)` }}
                      />
                      <Text size="sm">{s.label}</Text>
                    </Group>
                    <Text size="sm" fw={500} className={classes.num}>
                      {s.count}
                    </Text>
                  </Group>
                ))}
              </Stack>
            </Paper>
          ))}
          {q.data && !q.data.workspaces.length && (
            <Paper withBorder p="lg">
              <Text c="dimmed">
                You are not on the team of any item yet. Items appear here once someone adds you to one.
              </Text>
            </Paper>
          )}
        </SimpleGrid>

        <section>
          <Title order={2} size="h4" mb="sm">
            Due in the next 30 days
          </Title>
          {q.data && !q.data.due_soon.length ? (
            <Text c="dimmed" size="sm">
              Nothing due for you in the next 30 days.
            </Text>
          ) : (
            <Table withTableBorder style={{ background: "var(--surface)" }}>
              <Table.Tbody>
                {(q.data?.due_soon ?? []).map((d) => (
                  <Table.Tr key={d.id}>
                    <Table.Td w={120}>
                      <Text size="sm" c={d.overdue ? "red.7" : undefined} fw={d.overdue ? 600 : 400}>
                        {fmtDate(d.due_date)}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Anchor
                        component={Link}
                        to={`/w/${wsKey(d.workspace_id)}/b/${d.board_id}?item=${d.id}`}
                        size="sm"
                      >
                        {d.name}
                      </Anchor>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" c="dimmed">
                        {d.board_name}
                      </Text>
                    </Table.Td>
                    <Table.Td w={90}>
                      {d.overdue && (
                        <Badge color="red" variant="light">
                          overdue
                        </Badge>
                      )}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </section>
      </Stack>
    </Page>
  );
}
