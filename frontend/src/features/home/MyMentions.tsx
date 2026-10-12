import { Anchor, Badge, Group, Paper, Stack, Text, Title, UnstyledButton } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { api } from "../../shared/api/client";
import { useCommand, useMe } from "../../shared/api/hooks";

interface Note {
  id: string;
  kind: string;
  title: string;
  body: string | null;
  entity_type: string | null;
  entity_id: string | null;
  workspace_id: string | null;
  read: boolean;
  created_at: string;
}

/**
 * Unread @mentions and rule alerts. Shares the bell's query key so reading a
 * note in one place clears it in the other.
 */
export function MyMentions() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const me = useMe();
  const q = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.get<{ unread: number; rows: Note[] }>("/notifications"),
  });
  const mark = useCommand("notifications.mark_read", { invalidate: [["notifications"]], silent: true });
  const unread = (q.data?.rows ?? []).filter((n) => !n.read).slice(0, 8);

  const open = (n: Note) => {
    mark.mutate({ notification_ids: [n.id] });
    if (n.entity_type === "item" && n.entity_id) {
      const ws = me.data?.workspaces.find((w) => w.id === n.workspace_id);
      navigate(`/w/${ws?.key ?? "x"}/b/first?item=${n.entity_id}`);
    }
  };

  return (
    <Paper withBorder p="lg" radius="md">
      <Group justify="space-between" mb="sm">
        <Title order={2} size="h4">
          {t("myWork.mentions.title")}
        </Title>
        {unread.length > 0 && (
          <Anchor component="button" size="xs" onClick={() => mark.mutate({ all: true })}>
            {t("myWork.mentions.markAll")}
          </Anchor>
        )}
      </Group>
      {q.data && !unread.length ? (
        <Text c="dimmed" size="sm">
          {t("myWork.mentions.empty")}
        </Text>
      ) : (
        <Stack gap={0}>
          {unread.map((n) => (
            <UnstyledButton
              key={n.id}
              onClick={() => open(n)}
              py={6}
              style={{ borderTop: "1px dashed var(--line)" }}
            >
              <Group justify="space-between" wrap="nowrap" align="flex-start">
                <Text size="sm" lineClamp={2}>
                  {n.title}
                </Text>
                {n.kind !== "mention" && (
                  <Badge size="xs" variant="light">
                    {n.kind}
                  </Badge>
                )}
              </Group>
              <Text size="xs" c="dimmed">
                {dayjs(n.created_at).fromNow()}
              </Text>
            </UnstyledButton>
          ))}
        </Stack>
      )}
    </Paper>
  );
}
