import { Avatar, Button, Group, Menu, Paper, Stack, Text, Textarea } from "@mantine/core";
import { modals } from "@mantine/modals";
import { IconAt } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useRef, useState } from "react";
import { api } from "../../shared/api/client";
import { useCommand } from "../../shared/api/hooks";
import type { CommentRow } from "../../shared/api/types";
import { initials } from "../../shared/fields/format";
import type { FieldCtx } from "../../shared/workspace";

const MENTION = /@\[([^\]]+)\]\(user:[0-9a-fA-F-]{36}\)/g;

function Body({ text }: { text: string }) {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(MENTION)) {
    parts.push(text.slice(last, m.index));
    parts.push(
      <Text span key={m.index} c="eucalyptus.7" fw={500}>
        @{m[1]}
      </Text>,
    );
    last = (m.index ?? 0) + m[0].length;
  }
  parts.push(text.slice(last));
  return (
    <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
      {parts}
    </Text>
  );
}

export function CommentsPanel({
  entityType,
  entityId,
  ctx,
  canWrite,
}: {
  entityType: "item" | "client" | "task";
  entityId: string;
  ctx: FieldCtx;
  canWrite: boolean;
}) {
  const key = ["comments", entityType, entityId];
  const q = useQuery({
    queryKey: key,
    queryFn: () => api.get<CommentRow[]>("/comments", { entity_type: entityType, entity_id: entityId }),
  });
  const inv = { invalidate: [key, ["items"], ["item"]] };
  const add = useCommand("comments.add", inv);
  const edit = useCommand("comments.edit", inv);
  const del = useCommand("comments.delete", inv);
  const [body, setBody] = useState("");
  const [editing, setEditing] = useState<{ id: string; body: string } | null>(null);
  const ta = useRef<HTMLTextAreaElement>(null);

  const mention = (id: string, name: string) => {
    const el = ta.current;
    const token = `@[${name}](user:${id}) `;
    const pos = el?.selectionStart ?? body.length;
    setBody(body.slice(0, pos) + token + body.slice(pos));
    requestAnimationFrame(() => el?.focus());
  };

  const post = () =>
    add.mutate({ entity_type: entityType, entity_id: entityId, body }, { onSuccess: () => setBody("") });

  return (
    <Stack>
      {canWrite && (
        <Paper withBorder p="sm" radius="md">
          <Textarea
            ref={ta}
            placeholder="Write an update. Use @ to notify someone."
            autosize
            minRows={2}
            value={body}
            onChange={(e) => setBody(e.currentTarget.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && body.trim()) post();
            }}
            variant="unstyled"
          />
          <Group justify="space-between" mt={4}>
            <Menu shadow="md" position="bottom-start" withinPortal>
              <Menu.Target>
                <Button size="compact-sm" variant="subtle" leftSection={<IconAt size={14} />}>
                  Mention
                </Button>
              </Menu.Target>
              <Menu.Dropdown mah={300} style={{ overflow: "auto" }}>
                {ctx.userList
                  .filter((u) => !u.is_placeholder)
                  .map((u) => (
                    <Menu.Item key={u.id} onClick={() => mention(u.id, u.full_name)}>
                      {u.full_name}
                    </Menu.Item>
                  ))}
              </Menu.Dropdown>
            </Menu>
            <Button size="compact-sm" onClick={post} disabled={!body.trim()} loading={add.isPending}>
              Post update
            </Button>
          </Group>
        </Paper>
      )}
      {(q.data ?? []).length === 0 && !q.isLoading && (
        <Text size="sm" c="dimmed">
          No updates yet.
        </Text>
      )}
      {(q.data ?? []).map((c) => (
        <Group key={c.id} align="flex-start" wrap="nowrap" gap="sm">
          <Avatar size={30} radius="xl" color="teal">
            {initials(c.author ?? "?")}
          </Avatar>
          <div style={{ flex: 1, minWidth: 0 }}>
            <Group gap={8}>
              <Text size="sm" fw={600}>
                {c.author ?? "Unknown"}
              </Text>
              <Text size="xs" c="dimmed">
                {dayjs(c.created_at).format("DD/MM/YYYY HH:mm")}
                {c.edited_at ? " · edited" : ""}
              </Text>
            </Group>
            {editing?.id === c.id ? (
              <Stack gap={4} mt={4}>
                <Textarea
                  autosize
                  minRows={2}
                  value={editing.body}
                  onChange={(e) => setEditing({ id: c.id, body: e.currentTarget.value })}
                />
                <Group gap={6}>
                  <Button
                    size="compact-xs"
                    onClick={() =>
                      edit.mutate(
                        { comment_id: c.id, body: editing.body },
                        { onSuccess: () => setEditing(null) },
                      )
                    }
                  >
                    Save
                  </Button>
                  <Button size="compact-xs" variant="subtle" color="gray" onClick={() => setEditing(null)}>
                    Cancel
                  </Button>
                </Group>
              </Stack>
            ) : (
              <Body text={c.body} />
            )}
            {c.is_mine && editing?.id !== c.id && (
              <Group gap={4} mt={2}>
                <Button
                  size="compact-xs"
                  variant="subtle"
                  color="gray"
                  onClick={() => setEditing({ id: c.id, body: c.body })}
                >
                  Edit
                </Button>
                <Button
                  size="compact-xs"
                  variant="subtle"
                  color="red"
                  onClick={() =>
                    modals.openConfirmModal({
                      title: "Delete this update?",
                      labels: { confirm: "Delete", cancel: "Cancel" },
                      confirmProps: { color: "red" },
                      onConfirm: () => del.mutate({ comment_id: c.id }),
                    })
                  }
                >
                  Delete
                </Button>
              </Group>
            )}
          </div>
        </Group>
      ))}
    </Stack>
  );
}
