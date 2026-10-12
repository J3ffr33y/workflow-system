import {
  ActionIcon,
  Badge,
  Button,
  Group,
  List,
  Menu,
  Modal,
  Paper,
  Stack,
  Switch,
  Text,
  TextInput,
} from "@mantine/core";
import { modals } from "@mantine/modals";
import { IconDots, IconSearch } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../shared/api/client";
import { notifyError, useCommand } from "../../shared/api/hooks";
import { fmtDateTime } from "../../shared/fields/format";
import { Page } from "../../shared/ui/Page";
import { useWorkspace } from "../../shared/workspace";
import { RuleEditor, type Rule } from "./RuleEditor";

const TRIGGER_TEXT: Record<string, (c: any, labels: (k: string) => string) => string> = {
  status_changed: (c, l) => `Status changes to ${(c.to ?? []).map(l).join(" or ")}`,
  field_changed: (c) => `${c.field} changes`,
  item_created: () => "An item is created",
  date_reached: (c) =>
    `${c.field} ${c.offset?.amount ? `is ${c.offset.amount}${c.offset.unit} ${c.offset.direction}` : "arrives"}${c.mode === "on" ? " (that day only)" : ""}`,
};

export function AutomationsPage() {
  const { ref, ctx } = useWorkspace();
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<Rule | null>(null);
  const [preview, setPreview] = useState<{ name: string; items: { id: string; name: string }[] } | null>(
    null,
  );
  const q = useQuery({
    queryKey: ["rules", ref?.id, search],
    queryFn: () =>
      api.get<(Rule & { id: string; run_count: number; last_run_at: string | null })[]>(
        "/automations/rules",
        { workspace_id: ref!.id, search },
      ),
    enabled: !!ref,
  });
  const toggle = useCommand("automations.set_enabled", { invalidate: [["rules"]] });
  const del = useCommand("automations.delete_rule", { invalidate: [["rules"]], success: "Rule deleted" });
  const canManage = ctx?.can("automations.manage");
  const statusLabel = (k: string) => ctx?.statuses.get(k)?.label ?? k;

  return (
    <Page
      title="Automations"
      subtitle="Rules that update items for you when something changes or a date arrives."
      actions={
        canManage && (
          <Button
            onClick={() =>
              setEditing({
                name: "",
                enabled: true,
                trigger: { type: "status_changed", config: {} },
                conditions: null,
                actions: [{ type: "set_status", config: {} }],
                board_ids: [],
              })
            }
          >
            New rule
          </Button>
        )
      }
    >
      <TextInput
        mb="md"
        w={280}
        leftSection={<IconSearch size={14} />}
        placeholder="Search rules"
        value={search}
        onChange={(e) => setSearch(e.currentTarget.value)}
      />
      <Stack maw={980}>
        {(q.data ?? []).map((r) => (
          <Paper key={r.id} withBorder p="md" style={{ opacity: r.enabled ? 1 : 0.6 }}>
            <Group justify="space-between" wrap="nowrap" align="flex-start">
              <div>
                <Group gap="xs">
                  <Text fw={600}>{r.name}</Text>
                  {r.board_ids.length > 0 && (
                    <Badge variant="light" color="gray" size="sm" style={{ textTransform: "none" }}>
                      {r.board_ids.map((b) => ctx?.boards.get(b)).join(", ")}
                    </Badge>
                  )}
                </Group>
                <Text size="sm" mt={4}>
                  <b>When</b>{" "}
                  {TRIGGER_TEXT[r.trigger.type]?.(r.trigger.config, statusLabel) ?? r.trigger.type}
                  {r.conditions?.rules?.length ? `, if ${r.conditions.rules.length} condition(s) match` : ""}
                  <b> then</b> {r.actions.map((a) => a.type.replace(/_/g, " ")).join(", ")}
                </Text>
                <Text size="xs" c="dimmed" mt={4}>
                  Ran {r.run_count} times{r.last_run_at ? `, last ${fmtDateTime(r.last_run_at)}` : ""}
                </Text>
              </div>
              {canManage && (
                <Group gap="xs" wrap="nowrap">
                  <Switch
                    checked={r.enabled}
                    onChange={(e) => toggle.mutate({ rule_id: r.id, enabled: e.currentTarget.checked })}
                    aria-label="Enabled"
                  />
                  <Menu position="bottom-end">
                    <Menu.Target>
                      <ActionIcon variant="subtle" color="gray" aria-label="Rule menu">
                        <IconDots size={16} />
                      </ActionIcon>
                    </Menu.Target>
                    <Menu.Dropdown>
                      <Menu.Item onClick={() => setEditing(r)}>Edit</Menu.Item>
                      <Menu.Item
                        onClick={() =>
                          api
                            .get<{ id: string; name: string }[]>(`/automations/rules/${r.id}/preview`)
                            .then((items) => setPreview({ name: r.name, items }))
                            .catch((e) => notifyError(e, "Preview failed"))
                        }
                      >
                        Preview matching items
                      </Menu.Item>
                      <Menu.Item
                        color="red"
                        onClick={() =>
                          modals.openConfirmModal({
                            title: `Delete “${r.name}”?`,
                            labels: { confirm: "Delete", cancel: "Cancel" },
                            confirmProps: { color: "red" },
                            onConfirm: () => del.mutate({ rule_id: r.id }),
                          })
                        }
                      >
                        Delete
                      </Menu.Item>
                    </Menu.Dropdown>
                  </Menu>
                </Group>
              )}
            </Group>
          </Paper>
        ))}
        {q.data && !q.data.length && <Text c="dimmed">No automations yet.</Text>}
      </Stack>
      {editing && ctx && <RuleEditor rule={editing} ctx={ctx} onClose={() => setEditing(null)} />}
      <Modal
        opened={!!preview}
        onClose={() => setPreview(null)}
        title={`Items “${preview?.name}” applies to right now`}
      >
        {preview?.items.length ? (
          <List size="sm">
            {preview.items.map((i) => (
              <List.Item key={i.id}>{i.name}</List.Item>
            ))}
          </List>
        ) : (
          <Text size="sm" c="dimmed">
            No items currently match. Nothing would change.
          </Text>
        )}
      </Modal>
    </Page>
  );
}
