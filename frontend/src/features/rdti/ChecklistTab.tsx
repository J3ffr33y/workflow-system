import {
  ActionIcon,
  Badge,
  Button,
  Group,
  Modal,
  Paper,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
} from "@mantine/core";
import { useClipboard } from "@mantine/hooks";
import { IconMail, IconPencil, IconPlus, IconSparkles, IconTrash } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, command } from "../../shared/api/client";
import { notifyError } from "../../shared/api/hooks";
import { rk, useElementLabel, useRefreshRdti } from "./hooks";
import type { ChecklistRow, Workbench } from "./types";

const STATUSES = ["draft", "sent", "received", "closed"] as const;
const STATUS_BADGE: Record<ChecklistRow["status"], string> = {
  draft: "gray",
  sent: "blue",
  received: "teal",
  closed: "dark",
};

interface Draft {
  id?: string;
  question: string;
  preferred: string;
  alternatives: string;
  example: string;
  activity_id: string | null;
}

export function ChecklistTab({ data }: { data: Workbench }) {
  const { t } = useTranslation();
  const refresh = useRefreshRdti(data.item.id);
  const label = useElementLabel();
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<Draft | null>(null);
  const [emailOpen, setEmailOpen] = useState(false);
  const activities = new Map(data.activities.map((a) => [a.id, a]));
  const elements = new Map(data.rules.elements.map((e) => [e.key, e]));

  const generate = async () => {
    setBusy(true);
    try {
      await command("rdti.generate_checklist", { item_id: data.item.id });
      refresh();
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };

  const update = (id: string, patch: Record<string, unknown>) =>
    command("rdti.update_checklist_item", { checklist_item_id: id, ...patch } as any)
      .then(refresh)
      .catch((e) => notifyError(e));

  const save = async () => {
    if (!editing) return;
    const alternatives = editing.alternatives
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    try {
      if (editing.id) {
        await command("rdti.update_checklist_item", {
          checklist_item_id: editing.id,
          question: editing.question,
          preferred: editing.preferred,
          alternatives,
          example: editing.example,
        });
      } else {
        await command("rdti.add_checklist_item", {
          item_id: data.item.id,
          question: editing.question,
          preferred: editing.preferred,
          alternatives,
          example: editing.example,
          activity_id: editing.activity_id,
        });
      }
      setEditing(null);
      refresh();
    } catch (e) {
      notifyError(e);
    }
  };

  return (
    <Paper withBorder p="md" radius="md">
      <Group justify="space-between" mb="sm">
        <Group gap="xs">
          {data.can_write && (
            <>
              <Button leftSection={<IconSparkles size={16} />} onClick={generate} loading={busy}>
                {t("rdti.checklist.generate")}
              </Button>
              <Button
                variant="default"
                leftSection={<IconPlus size={16} />}
                onClick={() =>
                  setEditing({
                    question: "",
                    preferred: "",
                    alternatives: "",
                    example: "",
                    activity_id: null,
                  })
                }
              >
                {t("rdti.checklist.add")}
              </Button>
            </>
          )}
        </Group>
        <Button
          variant="light"
          leftSection={<IconMail size={16} />}
          onClick={() => setEmailOpen(true)}
          disabled={!data.checklist.length}
        >
          {t("rdti.checklist.email")}
        </Button>
      </Group>

      {data.checklist.length === 0 ? (
        <Text c="dimmed" size="sm">
          {t("rdti.checklist.empty")}
        </Text>
      ) : (
        <Table verticalSpacing="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th w={110} />
              <Table.Th>{t("rdti.checklist.question")}</Table.Th>
              <Table.Th w="30%">{t("rdti.checklist.preferred")}</Table.Th>
              <Table.Th w={130}>{t("rdti.checklist.status")}</Table.Th>
              <Table.Th w={70} />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {data.checklist.map((c) => {
              const a = c.activity_id ? activities.get(c.activity_id) : undefined;
              return (
                <Table.Tr key={c.id} style={{ opacity: c.status === "closed" ? 0.55 : 1 }}>
                  <Table.Td>
                    <Stack gap={2}>
                      {a && (
                        <Badge size="sm" variant="outline">
                          {a.code}
                        </Badge>
                      )}
                      {c.element && (
                        <Text size="xs" c="dimmed">
                          {label(elements.get(c.element), c.element)}
                        </Text>
                      )}
                    </Stack>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{c.question}</Text>
                    {c.example && (
                      <Text size="xs" c="dimmed" mt={4}>
                        {t("rdti.checklist.example")}: {c.example}
                      </Text>
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{c.preferred}</Text>
                    {c.alternatives.length > 0 && (
                      <Text size="xs" c="dimmed" mt={4}>
                        {t("rdti.checklist.alternatives")}: {c.alternatives.join("; ")}
                      </Text>
                    )}
                  </Table.Td>
                  <Table.Td>
                    {data.can_write ? (
                      <Select
                        size="xs"
                        value={c.status}
                        allowDeselect={false}
                        data={STATUSES.map((s) => ({ value: s, label: t(`rdti.checklist.${s}`) }))}
                        onChange={(v) => v && update(c.id, { status: v })}
                      />
                    ) : (
                      <Badge color={STATUS_BADGE[c.status]}>{t(`rdti.checklist.${c.status}`)}</Badge>
                    )}
                  </Table.Td>
                  <Table.Td>
                    {data.can_write && (
                      <Group gap={2} wrap="nowrap">
                        <ActionIcon
                          variant="subtle"
                          onClick={() =>
                            setEditing({
                              id: c.id,
                              question: c.question,
                              preferred: c.preferred,
                              alternatives: c.alternatives.join("\n"),
                              example: c.example,
                              activity_id: c.activity_id,
                            })
                          }
                        >
                          <IconPencil size={16} />
                        </ActionIcon>
                        <ActionIcon
                          variant="subtle"
                          color="red"
                          onClick={() => update(c.id, { delete: true })}
                        >
                          <IconTrash size={16} />
                        </ActionIcon>
                      </Group>
                    )}
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      )}

      <Modal opened={!!editing} onClose={() => setEditing(null)} title={t("rdti.checklist.add")} size="lg">
        {editing && (
          <Stack>
            {!editing.id && (
              <Select
                label={t("rdti.activities.title")}
                clearable
                value={editing.activity_id}
                data={data.activities.map((a) => ({ value: a.id, label: `${a.code} ${a.title}` }))}
                onChange={(v) => setEditing({ ...editing, activity_id: v })}
              />
            )}
            <Textarea
              label={t("rdti.checklist.question")}
              autosize
              minRows={2}
              required
              value={editing.question}
              onChange={(e) => setEditing({ ...editing, question: e.currentTarget.value })}
            />
            <TextInput
              label={t("rdti.checklist.preferred")}
              value={editing.preferred}
              onChange={(e) => setEditing({ ...editing, preferred: e.currentTarget.value })}
            />
            <Textarea
              label={t("rdti.checklist.alternatives")}
              description="One per line"
              autosize
              minRows={2}
              value={editing.alternatives}
              onChange={(e) => setEditing({ ...editing, alternatives: e.currentTarget.value })}
            />
            <Textarea
              label={t("rdti.checklist.example")}
              autosize
              value={editing.example}
              onChange={(e) => setEditing({ ...editing, example: e.currentTarget.value })}
            />
            <Group justify="flex-end">
              <Button onClick={save} disabled={!editing.question.trim()}>
                {t("rdti.report.save")}
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>

      <EmailDraft itemId={data.item.id} opened={emailOpen} onClose={() => setEmailOpen(false)} />
    </Paper>
  );
}

function EmailDraft({ itemId, opened, onClose }: { itemId: string; opened: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const clipboard = useClipboard({ timeout: 1500 });
  const q = useQuery({
    queryKey: [...rk.all(itemId), "email"],
    queryFn: () =>
      api.get<{ subject: string; body: string; to: string | null; items: number }>(
        `/rdti/items/${itemId}/email-draft`,
      ),
    enabled: opened,
  });
  const d = q.data;
  return (
    <Modal opened={opened} onClose={onClose} title={t("rdti.checklist.email")} size="xl">
      {d && (
        <Stack>
          <TextInput label="To" value={d.to ?? ""} readOnly />
          <TextInput label="Subject" value={d.subject} readOnly />
          <Textarea
            value={d.body}
            readOnly
            autosize
            minRows={10}
            maxRows={24}
            styles={{ input: { fontFamily: "inherit" } }}
          />
          <Group justify="flex-end">
            <Button
              onClick={() => clipboard.copy(`Subject: ${d.subject}\n\n${d.body}`)}
              color={clipboard.copied ? "teal" : undefined}
            >
              {clipboard.copied ? t("rdti.checklist.copied") : t("rdti.checklist.copy")}
            </Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}
