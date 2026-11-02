import {
  ActionIcon,
  Anchor,
  Badge,
  Button,
  Checkbox,
  FileButton,
  Group,
  Paper,
  Select,
  Spoiler,
  Stack,
  Table,
  Text,
  TextInput,
  Tooltip,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import { IconExternalLink, IconRefresh, IconTrash, IconUpload } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, command } from "../../shared/api/client";
import { notifyError } from "../../shared/api/hooks";
import { fileUrl, usePassages, useRefreshRdti } from "./hooks";
import type { DocumentRow, Workbench } from "./types";

export function MaterialsTab({ data }: { data: Workbench }) {
  const { t } = useTranslation();
  const refresh = useRefreshRdti(data.item.id);
  const [busy, setBusy] = useState(false);

  const upload = async (files: File[], replaces?: string) => {
    setBusy(true);
    try {
      for (const f of files) {
        const form = new FormData();
        form.append("file", f);
        if (replaces) form.append("replaces_file_id", replaces);
        const res = await api.post<{ passages: number }>(`/rdti/items/${data.item.id}/documents`, form);
        notifications.show({
          color: "teal",
          message: `${f.name}: ${t("rdti.materials.passages", { count: res.passages })}`,
        });
      }
    } catch (e) {
      notifyError(e, "Upload failed");
    } finally {
      setBusy(false);
      refresh();
    }
  };

  const remove = (d: DocumentRow) =>
    modals.openConfirmModal({
      title: t("rdti.materials.remove"),
      children: <Text size="sm">{d.name}</Text>,
      labels: { confirm: t("rdti.materials.remove"), cancel: t("common.cancel") },
      confirmProps: { color: "red" },
      onConfirm: () =>
        command("rdti.remove_document", { file_id: d.file_id })
          .then(refresh)
          .catch((e) => notifyError(e)),
    });

  return (
    <Stack>
      <Paper withBorder p="md" radius="md">
        <Group justify="space-between" mb="sm">
          <div>
            <Text fw={600}>{t("rdti.tabs.materials")}</Text>
            <Text size="xs" c="dimmed">
              {t("rdti.materials.uploadHint")}
            </Text>
          </div>
          {data.can_write && (
            <FileButton onChange={(f) => f.length && upload(f)} accept=".pdf,.docx,.txt,.md" multiple>
              {(props) => (
                <Button {...props} leftSection={<IconUpload size={16} />} loading={busy}>
                  {t("rdti.materials.upload")}
                </Button>
              )}
            </FileButton>
          )}
        </Group>
        {data.documents.length === 0 ? (
          <Text size="sm" c="dimmed">
            {t("rdti.materials.empty")}
          </Text>
        ) : (
          <Table verticalSpacing={6}>
            <Table.Tbody>
              {data.documents.map((d) => (
                <Table.Tr key={d.file_id}>
                  <Table.Td>
                    <Text size="sm" fw={500}>
                      {d.name}
                    </Text>
                    <Text size="xs" c="dimmed">
                      v{d.version} ·{" "}
                      {d.size_bytes ? `${Math.max(1, Math.round(d.size_bytes / 1024))} KB` : ""}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Badge variant="light" color="gray">
                      {t("rdti.materials.passages", { count: d.passages })}
                    </Badge>{" "}
                    <Badge variant="light" color={d.assigned === d.passages ? "teal" : "yellow"}>
                      {t("rdti.materials.assigned", { count: d.assigned })}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4} justify="flex-end" wrap="nowrap">
                      <Tooltip label={t("rdti.materials.open")}>
                        <ActionIcon variant="subtle" component="a" href={fileUrl(d.file_id)} target="_blank">
                          <IconExternalLink size={16} />
                        </ActionIcon>
                      </Tooltip>
                      {data.can_write && (
                        <>
                          <FileButton
                            onChange={(f) => f && upload([f], d.file_id)}
                            accept=".pdf,.docx,.txt,.md"
                          >
                            {(props) => (
                              <Tooltip label={t("rdti.materials.replace")}>
                                <ActionIcon {...props} variant="subtle">
                                  <IconRefresh size={16} />
                                </ActionIcon>
                              </Tooltip>
                            )}
                          </FileButton>
                          <Tooltip label={t("rdti.materials.remove")}>
                            <ActionIcon variant="subtle" color="red" onClick={() => remove(d)}>
                              <IconTrash size={16} />
                            </ActionIcon>
                          </Tooltip>
                        </>
                      )}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Paper>
      {data.documents.length > 0 && <PassageBrowser data={data} />}
    </Stack>
  );
}

function PassageBrowser({ data }: { data: Workbench }) {
  const { t } = useTranslation();
  const refresh = useRefreshRdti(data.item.id);
  const [fileId, setFileId] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [q] = useDebouncedValue(search, 300);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [target, setTarget] = useState<string | null>(null);
  const params: Record<string, unknown> = {
    file_id: fileId ?? undefined,
    search: q || undefined,
    unassigned: filter === "none" ? true : undefined,
    activity_id: filter !== "all" && filter !== "none" ? filter : undefined,
  };
  const list = usePassages(data.item.id, params);
  const acts = new Map(data.activities.map((a) => [a.id, a]));
  const activityOptions = data.activities.map((a) => ({ value: a.id, label: `${a.code} ${a.title}` }));

  const assign = async () => {
    try {
      await command("rdti.assign_passages", {
        item_id: data.item.id,
        chunk_ids: [...picked],
        activity_id: target === "none" ? null : target,
      } as any);
      setPicked(new Set());
      refresh();
    } catch (e) {
      notifyError(e);
    }
  };

  const rows = list.data ?? [];
  return (
    <Paper withBorder p="md" radius="md">
      <Group mb="sm" gap="xs" wrap="wrap">
        <Select
          size="xs"
          placeholder={t("rdti.activities.all")}
          data={data.documents.map((d) => ({ value: d.file_id, label: d.name }))}
          value={fileId}
          onChange={setFileId}
          clearable
          w={220}
        />
        <Select
          size="xs"
          data={[
            { value: "all", label: t("rdti.activities.all") },
            { value: "none", label: t("rdti.materials.unassigned") },
            ...activityOptions,
          ]}
          value={filter}
          onChange={(v) => setFilter(v ?? "all")}
          allowDeselect={false}
          w={220}
        />
        <TextInput
          size="xs"
          placeholder={t("rdti.materials.search")}
          value={search}
          onChange={(e) => setSearch(e.currentTarget.value)}
          w={200}
        />
        {data.can_write && (
          <Group gap={6} ml="auto">
            <Checkbox
              size="xs"
              label={t("rdti.materials.selectAll")}
              checked={rows.length > 0 && rows.every((r) => picked.has(r.id))}
              onChange={(e) =>
                setPicked(e.currentTarget.checked ? new Set(rows.map((r) => r.id)) : new Set())
              }
            />
            <Select
              size="xs"
              placeholder={t("rdti.materials.assignTo")}
              data={[{ value: "none", label: t("rdti.materials.unassigned") }, ...activityOptions]}
              value={target}
              onChange={setTarget}
              w={200}
            />
            <Button size="xs" disabled={!picked.size || !target} onClick={assign}>
              {t("rdti.materials.assignSelected")} ({picked.size})
            </Button>
          </Group>
        )}
      </Group>
      <Stack gap={4}>
        {rows.map((p) => {
          const a = p.activity_id ? acts.get(p.activity_id) : null;
          return (
            <Group
              key={p.id}
              align="flex-start"
              gap="xs"
              wrap="nowrap"
              style={{ borderBottom: "1px solid var(--line)", padding: "6px 0" }}
            >
              {data.can_write && (
                <Checkbox
                  size="xs"
                  mt={3}
                  checked={picked.has(p.id)}
                  onChange={(e) => {
                    const next = new Set(picked);
                    if (e.currentTarget.checked) next.add(p.id);
                    else next.delete(p.id);
                    setPicked(next);
                  }}
                />
              )}
              <div style={{ flex: 1, minWidth: 0 }}>
                <Group gap={6}>
                  <Anchor size="xs" href={fileUrl(p.file_id, p.page)} target="_blank">
                    {p.file_name} · {p.location}
                  </Anchor>
                  {a ? (
                    <Badge size="xs" variant="light">
                      {a.code}
                    </Badge>
                  ) : (
                    <Badge size="xs" variant="light" color="gray">
                      {t("rdti.materials.unassigned")}
                    </Badge>
                  )}
                </Group>
                <Spoiler maxHeight={44} showLabel="…" hideLabel="↑">
                  <Text size="sm">{p.text}</Text>
                </Spoiler>
              </div>
            </Group>
          );
        })}
      </Stack>
    </Paper>
  );
}
