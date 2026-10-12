import {
  ActionIcon,
  Badge,
  Button,
  Group,
  Indicator,
  Popover,
  ScrollArea,
  Stack,
  Text,
  UnstyledButton,
} from "@mantine/core";
import { IconBell } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { useNavigate } from "react-router-dom";
import { api } from "../../shared/api/client";
import { useCommand, useMe } from "../../shared/api/hooks";

dayjs.extend(relativeTime);

interface Note {
  id: string;
  kind: string;
  title: string;
  body: string | null;
  entity_type: string | null;
  entity_id: string | null;
  workspace_id: string | null;
  actor: string | null;
  read: boolean;
  created_at: string;
}

export function NotificationBell() {
  const navigate = useNavigate();
  const me = useMe();
  const q = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.get<{ unread: number; rows: Note[] }>("/notifications"),
    refetchInterval: 60_000,
  });
  const mark = useCommand("notifications.mark_read", { invalidate: [["notifications"]], silent: true });

  const open = (n: Note) => {
    if (!n.read) mark.mutate({ notification_ids: [n.id] });
    if (n.entity_type === "item" && n.entity_id) {
      const ws = me.data?.workspaces.find((w) => w.id === n.workspace_id);
      navigate(`/w/${ws?.key ?? "x"}/b/first?item=${n.entity_id}`);
    }
  };

  return (
    <Popover width={360} position="right-start" shadow="lg" withinPortal>
      <Popover.Target>
        <Indicator disabled={!q.data?.unread} label={q.data?.unread} size={16} color="red" offset={4}>
          <ActionIcon variant="subtle" color="gray.4" aria-label="Notifications">
            <IconBell size={18} />
          </ActionIcon>
        </Indicator>
      </Popover.Target>
      <Popover.Dropdown p={0}>
        <Group justify="space-between" px="md" py="sm">
          <Text fw={600}>Notifications</Text>
          {!!q.data?.unread && (
            <Button size="compact-xs" variant="subtle" onClick={() => mark.mutate({ all: true })}>
              Mark all read
            </Button>
          )}
        </Group>
        <ScrollArea.Autosize mah={420}>
          <Stack gap={0}>
            {(q.data?.rows ?? []).length === 0 && (
              <Text size="sm" c="dimmed" px="md" pb="md">
                You're all caught up. Mentions and automation alerts will appear here.
              </Text>
            )}
            {(q.data?.rows ?? []).map((n) => (
              <UnstyledButton
                key={n.id}
                onClick={() => open(n)}
                px="md"
                py="sm"
                style={{ borderTop: "1px solid var(--line)", background: n.read ? undefined : "#f1f8f6" }}
              >
                <Group justify="space-between" wrap="nowrap" align="flex-start">
                  <Text size="sm" fw={n.read ? 400 : 600} lineClamp={2}>
                    {n.title}
                  </Text>
                  {n.kind === "automation" && (
                    <Badge size="xs" variant="light">
                      rule
                    </Badge>
                  )}
                </Group>
                {n.body && (
                  <Text size="xs" c="dimmed" lineClamp={2}>
                    {n.body}
                  </Text>
                )}
                <Text size="xs" c="dimmed" mt={2}>
                  {dayjs(n.created_at).fromNow()}
                </Text>
              </UnstyledButton>
            ))}
          </Stack>
        </ScrollArea.Autosize>
      </Popover.Dropdown>
    </Popover>
  );
}
