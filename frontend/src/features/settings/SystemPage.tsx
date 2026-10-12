import { Badge, Button, Group, Paper, SimpleGrid, Stack, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../shared/api/client";
import { useCommand } from "../../shared/api/hooks";
import { fmtDateTime } from "../../shared/fields/format";
import { Page } from "../../shared/ui/Page";

export function SystemPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: () => api.get<any>("/health") });
  const ready = useQuery({
    queryKey: ["ready"],
    queryFn: () => api.get<any>("/ready"),
    refetchInterval: 30_000,
  });
  const dead = useQuery({
    queryKey: ["deliveries"],
    queryFn: () => api.get<any[]>("/system/deliveries", { status: "dead" }),
  });
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: () => api.get<any[]>("/system/jobs", { limit: 50 }) });
  const retry = useCommand("system.retry_delivery", {
    invalidate: [["deliveries"]],
    success: "Queued again",
  });

  const tile = (label: string, value: React.ReactNode, ok?: boolean) => (
    <Paper withBorder p="md">
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text fw={600} size="lg" c={ok === false ? "red.7" : undefined}>
        {value}
      </Text>
    </Paper>
  );

  return (
    <Page
      title="System health"
      subtitle="What is deployed, whether background work is running, and anything that failed."
    >
      <Stack maw={1100} gap="lg">
        <SimpleGrid cols={{ base: 2, md: 4 }}>
          {tile("Deployed version", health.data?.git_sha ?? "…")}
          {tile("Database revision", health.data?.db_revision ?? "…")}
          {tile(
            "Background worker",
            ready.data ? (ready.data.worker ? "Running" : "Not running") : "…",
            ready.data?.worker,
          )}
          {tile("Events waiting", ready.data?.event_backlog ?? "…", (ready.data?.event_backlog ?? 0) < 100)}
        </SimpleGrid>
        <section>
          <Title order={3} size="h5" mb="xs">
            Failed deliveries
          </Title>
          {!dead.data?.length ? (
            <Text size="sm" c="dimmed">
              Nothing has failed.
            </Text>
          ) : (
            <Table withTableBorder style={{ background: "var(--surface)" }}>
              <Table.Tbody>
                {dead.data.map((d) => (
                  <Table.Tr key={d.id}>
                    <Table.Td>{d.subscriber}</Table.Td>
                    <Table.Td>{d.event_type}</Table.Td>
                    <Table.Td>
                      <Text size="xs" c="red.7">
                        {d.last_error}
                      </Text>
                    </Table.Td>
                    <Table.Td>{fmtDateTime(d.updated_at)}</Table.Td>
                    <Table.Td>
                      <Button size="compact-xs" onClick={() => retry.mutate({ delivery_id: d.id })}>
                        Retry
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </section>
        <section>
          <Title order={3} size="h5" mb="xs">
            Scheduled jobs
          </Title>
          <Table withTableBorder style={{ background: "var(--surface)" }}>
            <Table.Tbody>
              {(jobs.data ?? []).map((j) => (
                <Table.Tr key={j.id}>
                  <Table.Td>{j.job}</Table.Td>
                  <Table.Td>
                    <Badge
                      variant="light"
                      color={j.status === "succeeded" ? "teal" : j.status === "failed" ? "red" : "gray"}
                    >
                      {j.status}
                    </Badge>
                  </Table.Td>
                  <Table.Td>{fmtDateTime(j.started_at)}</Table.Td>
                  <Table.Td>{j.duration_ms != null ? `${j.duration_ms} ms` : ""}</Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      <Text size="xs">{j.summary}</Text>
                      {j.error && (
                        <Text size="xs" c="red.7">
                          {j.error}
                        </Text>
                      )}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </section>
      </Stack>
    </Page>
  );
}
