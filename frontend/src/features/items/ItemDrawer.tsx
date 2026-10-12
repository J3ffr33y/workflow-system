import { Badge, Center, Drawer, Group, Loader, Stack, Tabs, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api } from "../../shared/api/client";
import { useDirectory, useMe, useSchema } from "../../shared/api/hooks";
import type { AuditEntry, ItemRow } from "../../shared/api/types";
import { allowedStatuses } from "../../shared/fields/FieldInput";
import { StatusMenu } from "../../shared/ui/StatusPill";
import { buildCtx } from "../../shared/workspace";
import { ActivityList } from "../activity/ActivityList";
import { useUpdateField } from "../boards/useBoardItems";
import { CommentsPanel } from "./CommentsPanel";
import { DetailsPanel } from "./DetailsPanel";
import { TasksPanel } from "./TasksPanel";

/** Item panel, opened anywhere with ?item=<id>. */
export function ItemDrawer() {
  const [params, setParams] = useSearchParams();
  const id = params.get("item");
  const me = useMe();
  const item = useQuery({
    queryKey: ["item", id],
    queryFn: () => api.get<ItemRow>(`/items/${id}`),
    enabled: !!id,
  });
  const schema = useSchema(item.data?.workspace_id);
  const dir = useDirectory();
  const ctx = schema.data ? buildCtx(schema.data, dir.users) : undefined;
  const activity = useQuery({
    queryKey: ["activity", "item", id],
    queryFn: () => api.get<AuditEntry[]>("/activity/entity", { entity_type: "item", entity_id: id }),
    enabled: !!id,
  });
  const update = useUpdateField();
  const close = () => {
    params.delete("item");
    setParams(params);
  };
  const row = item.data;
  const boardName = row && ctx?.boards.get(row.board_id);

  return (
    <Drawer
      opened={!!id}
      onClose={close}
      size="min(760px, 100vw)"
      padding={0}
      title={null}
      withCloseButton={false}
      styles={{ body: { height: "100%" } }}
    >
      {!row || !ctx ? (
        <Center h="100%">
          {item.isError ? <Text c="dimmed">This item is not available.</Text> : <Loader />}
        </Center>
      ) : (
        <Stack gap={0} h="100%">
          <div style={{ padding: "18px 22px 12px", borderBottom: "1px solid var(--line)" }}>
            <Group justify="space-between" align="flex-start" wrap="nowrap">
              <div style={{ minWidth: 0 }}>
                <Text size="xs" c="dimmed">
                  {ctx.schema.workspace.name} · {boardName}
                  {row.is_archived && (
                    <Badge ml={8} size="xs" color="gray">
                      archived
                    </Badge>
                  )}
                </Text>
                <Title order={2} size={20} mt={2}>
                  {row.name}
                </Title>
                {row.client_name && (
                  <Text size="sm" c="dimmed">
                    {row.client_name}
                    {row.entity_name && row.entity_name !== row.client_name ? ` · ${row.entity_name}` : ""}
                  </Text>
                )}
              </div>
              <Group gap="xs" wrap="nowrap">
                <div style={{ width: 210, height: 34, borderRadius: 6, overflow: "hidden" }}>
                  <StatusMenu
                    statuses={allowedStatuses(ctx, row.board_id)}
                    value={row.status}
                    disabled={!ctx.can("items.update") || row.is_archived}
                    onChange={(v) =>
                      update(row, "status", v, row.status, (r) => ({ ...r, status: v })).then(() =>
                        item.refetch(),
                      )
                    }
                  />
                </div>
                <button
                  type="button"
                  onClick={close}
                  aria-label="Close"
                  className="mantine-focus-auto"
                  style={{
                    border: 0,
                    background: "none",
                    fontSize: 22,
                    cursor: "pointer",
                    color: "var(--ink-soft)",
                  }}
                >
                  ×
                </button>
              </Group>
            </Group>
          </div>
          <Tabs
            defaultValue="details"
            keepMounted={false}
            style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}
          >
            <Tabs.List px="md">
              <Tabs.Tab value="details">Details</Tabs.Tab>
              <Tabs.Tab value="updates">Updates{row.comment_count ? ` (${row.comment_count})` : ""}</Tabs.Tab>
              <Tabs.Tab value="tasks">Tasks{row.task_count ? ` (${row.task_count})` : ""}</Tabs.Tab>
              <Tabs.Tab value="activity">Activity</Tabs.Tab>
            </Tabs.List>
            <div style={{ flex: 1, overflow: "auto", padding: "16px 22px 40px" }}>
              <Tabs.Panel value="details">
                <DetailsPanel row={row} ctx={ctx} onSaved={() => item.refetch()} />
              </Tabs.Panel>
              <Tabs.Panel value="updates">
                <CommentsPanel
                  entityType="item"
                  entityId={row.id}
                  ctx={ctx}
                  canWrite={ctx.can("comments.write")}
                />
              </Tabs.Panel>
              <Tabs.Panel value="tasks">
                <TasksPanel item={row} ctx={ctx} />
              </Tabs.Panel>
              <Tabs.Panel value="activity">
                <ActivityList
                  entries={activity.data ?? []}
                  ctx={ctx}
                  canRevert={ctx.can("audit.revert") && !!me.data}
                />
              </Tabs.Panel>
            </div>
          </Tabs>
        </Stack>
      )}
    </Drawer>
  );
}
