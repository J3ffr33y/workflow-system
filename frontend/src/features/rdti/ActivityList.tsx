import {
  ActionIcon,
  Badge,
  Button,
  Group,
  Modal,
  Select,
  Stack,
  Text,
  TextInput,
  Textarea,
  UnstyledButton,
} from "@mantine/core";
import { modals } from "@mantine/modals";
import { IconPencil, IconPlus, IconTrash } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { command } from "../../shared/api/client";
import { notifyError } from "../../shared/api/hooks";
import { useRefreshRdti } from "./hooks";
import type { Activity, Workbench } from "./types";

export function ActivityList({
  data,
  selected,
  onSelect,
}: {
  data: Workbench;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  const refresh = useRefreshRdti(data.item.id);
  const [editing, setEditing] = useState<Partial<Activity> | null>(null);
  const cores = data.activities.filter((a) => a.kind === "core");

  const remove = (a: Activity) =>
    modals.openConfirmModal({
      title: t("rdti.activities.delete"),
      children: <Text size="sm">{`${a.code} ${a.title}`}</Text>,
      labels: { confirm: t("common.delete"), cancel: t("common.cancel") },
      confirmProps: { color: "red" },
      onConfirm: () =>
        command("rdti.delete_activity", { activity_id: a.id })
          .then(refresh)
          .catch((e) => notifyError(e)),
    });

  return (
    <Stack gap={6}>
      <Group justify="space-between">
        <Text fw={600} size="sm">
          {t("rdti.activities.title")}
        </Text>
        {data.can_write && (
          <ActionIcon
            variant="subtle"
            onClick={() => setEditing({ kind: "core" })}
            aria-label={t("rdti.activities.add")}
          >
            <IconPlus size={16} />
          </ActionIcon>
        )}
      </Group>
      {data.activities.length === 0 && (
        <Text size="sm" c="dimmed">
          {t("rdti.activities.empty")}
        </Text>
      )}
      {data.activities.map((a) => {
        const counts = data.report[a.id]?.counts;
        const problems = counts ? counts.unsupported + counts.needs_review : 0;
        const supports =
          a.supports_activity_id && data.activities.find((x) => x.id === a.supports_activity_id);
        return (
          <UnstyledButton
            key={a.id}
            component="div"
            role="button"
            tabIndex={0}
            onClick={() => onSelect(a.id)}
            onKeyDown={(e) => e.key === "Enter" && onSelect(a.id)}
            style={{
              padding: "6px 8px",
              borderRadius: 6,
              background: selected === a.id ? "#e3f1ed" : undefined,
              marginLeft: a.kind === "supporting" ? 12 : 0,
            }}
          >
            <Group justify="space-between" wrap="nowrap" gap={4}>
              <div style={{ minWidth: 0 }}>
                <Text size="sm" fw={500} truncate>
                  {a.code} {a.title}
                </Text>
                <Text size="xs" c="dimmed">
                  {a.kind === "core" ? t("rdti.activities.core") : t("rdti.activities.supporting")}
                  {supports ? ` → ${supports.code}` : ""}
                </Text>
              </div>
              <Group gap={2} wrap="nowrap">
                {problems > 0 && (
                  <Badge size="xs" color="red" variant="light">
                    {problems}
                  </Badge>
                )}
                {data.can_write && selected === a.id && (
                  <>
                    <ActionIcon
                      size="sm"
                      variant="subtle"
                      onClick={() => setEditing(a)}
                      aria-label={t("common.edit")}
                    >
                      <IconPencil size={14} />
                    </ActionIcon>
                    <ActionIcon
                      size="sm"
                      variant="subtle"
                      color="red"
                      onClick={() => remove(a)}
                      aria-label={t("common.delete")}
                    >
                      <IconTrash size={14} />
                    </ActionIcon>
                  </>
                )}
              </Group>
            </Group>
          </UnstyledButton>
        );
      })}
      {data.can_write && (
        <Button
          size="xs"
          variant="light"
          leftSection={<IconPlus size={14} />}
          onClick={() => setEditing({ kind: "core" })}
        >
          {t("rdti.activities.add")}
        </Button>
      )}
      <ActivityModal
        value={editing}
        cores={cores}
        onClose={() => setEditing(null)}
        onSaved={(id) => {
          setEditing(null);
          refresh();
          if (id) onSelect(id);
        }}
        itemId={data.item.id}
      />
    </Stack>
  );
}

function ActivityModal({
  value,
  cores,
  itemId,
  onClose,
  onSaved,
}: {
  value: Partial<Activity> | null;
  cores: Activity[];
  itemId: string;
  onClose: () => void;
  onSaved: (id?: string) => void;
}) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<Partial<Activity>>({});
  const [busy, setBusy] = useState(false);
  const v = { ...value, ...draft };
  const close = () => {
    setDraft({});
    onClose();
  };
  const save = async () => {
    setBusy(true);
    try {
      if (value?.id) {
        await command("rdti.update_activity", {
          activity_id: value.id,
          title: v.title,
          code: v.code,
          description: v.description ?? undefined,
          supports_activity_id: v.supports_activity_id ?? undefined,
          clear_supports: v.kind === "supporting" && !v.supports_activity_id,
        } as any);
        setDraft({});
        onSaved(value.id);
      } else {
        const res = await command<{ id: string }>("rdti.create_activity", {
          item_id: itemId,
          title: v.title ?? "",
          kind: v.kind ?? "core",
          supports_activity_id: v.kind === "supporting" ? (v.supports_activity_id ?? null) : null,
          description: v.description ?? null,
        } as any);
        setDraft({});
        onSaved(res.result.id);
      }
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal opened={!!value} onClose={close} title={value?.id ? t("common.edit") : t("rdti.activities.add")}>
      <Stack>
        {!value?.id && (
          <Select
            label={t("rdti.activities.kind")}
            data={[
              { value: "core", label: t("rdti.activities.core") },
              { value: "supporting", label: t("rdti.activities.supporting") },
            ]}
            value={v.kind ?? "core"}
            onChange={(k) => setDraft({ ...draft, kind: (k as Activity["kind"]) ?? "core" })}
            allowDeselect={false}
          />
        )}
        {value?.id && (
          <TextInput
            label="Code"
            value={v.code ?? ""}
            onChange={(e) => setDraft({ ...draft, code: e.currentTarget.value })}
          />
        )}
        <TextInput
          label={t("rdti.activities.titleField")}
          value={v.title ?? ""}
          onChange={(e) => setDraft({ ...draft, title: e.currentTarget.value })}
          data-autofocus
        />
        {v.kind === "supporting" && (
          <Select
            label={t("rdti.activities.supports")}
            data={cores.map((c) => ({ value: c.id, label: `${c.code} ${c.title}` }))}
            value={v.supports_activity_id ?? null}
            onChange={(id) => setDraft({ ...draft, supports_activity_id: id })}
            clearable
          />
        )}
        <Textarea
          label={t("rdti.activities.description")}
          autosize
          minRows={2}
          value={v.description ?? ""}
          onChange={(e) => setDraft({ ...draft, description: e.currentTarget.value })}
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={close}>
            {t("common.cancel")}
          </Button>
          <Button onClick={save} loading={busy} disabled={!v.title?.trim()}>
            {t("common.save")}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
