import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Box,
  Button,
  Grid,
  Group,
  Loader,
  Modal,
  Paper,
  ScrollArea,
  SegmentedControl,
  Stack,
  Switch,
  Text,
  TextInput,
  Textarea,
  Tooltip,
} from "@mantine/core";
import { modals } from "@mantine/modals";
import {
  IconArrowDown,
  IconCheck,
  IconDownload,
  IconExternalLink,
  IconLock,
  IconLockOpen,
  IconPencil,
  IconPlus,
  IconRefresh,
  IconSparkles,
  IconTrash,
  IconX,
} from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Fragment, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError, api, command } from "../../shared/api/client";
import { notifyError } from "../../shared/api/hooks";
import { fileUrl, useElementLabel, usePassages, useRefreshRdti, useReport } from "./hooks";
import {
  STATUS_COLOR,
  type Activity,
  type Citation,
  type Claim,
  type ClaimStatus,
  type Passage,
  type PassageContext,
  type Section,
  type Workbench,
} from "./types";

const PROBLEM: ClaimStatus[] = ["unsupported", "needs_review"];
const STATUSES: ClaimStatus[] = ["supported", "needs_review", "polish", "unsupported"];

export function ReportTab({ data, activity }: { data: Workbench; activity: Activity | null }) {
  const { t } = useTranslation();
  const itemId = data.item.id;
  const report = useReport(itemId);
  const refresh = useRefreshRdti(itemId);
  const [review, setReview] = useState(true);
  const [onlyProblems, setOnlyProblems] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const sections = useMemo(
    () => (report.data?.sections ?? []).filter((s) => !activity || s.activity_id === activity.id),
    [report.data, activity],
  );
  const claims = useMemo(() => sections.flatMap((s) => s.claims), [sections]);
  const counts = useMemo(() => {
    const c = Object.fromEntries(STATUSES.map((s) => [s, 0])) as Record<ClaimStatus, number>;
    for (const x of claims) c[x.status] += 1;
    return c;
  }, [claims]);
  const current = claims.find((c) => c.id === selected) ?? null;
  const currentSection = current
    ? sections.find((s) => s.claims.some((c) => c.id === current.id))
    : undefined;

  if (!activity) return <Text c="dimmed">{t("rdti.evidence.pick")}</Text>;
  if (report.isLoading) return <Loader />;

  const generate = async () => {
    setBusy(true);
    try {
      await command("rdti.generate_report", { activity_id: activity.id });
      setSelected(null);
      refresh();
    } catch (e) {
      notifyError(e, "Could not generate");
    } finally {
      setBusy(false);
    }
  };

  const removeDraft = () =>
    modals.openConfirmModal({
      title: t("rdti.report.deleteDraft"),
      children: <Text size="sm">{t("rdti.report.deleteDraftHint")}</Text>,
      labels: { confirm: t("rdti.report.deleteDraft"), cancel: t("rdti.claim.close") },
      confirmProps: { color: "red" },
      onConfirm: () =>
        command("rdti.delete_report", { activity_id: activity.id })
          .then(() => {
            setSelected(null);
            refresh();
          })
          .catch((e) => notifyError(e)),
    });

  const nextProblem = () => {
    const problems = claims.filter((c) => PROBLEM.includes(c.status));
    if (!problems.length) return;
    const idx = current ? problems.findIndex((c) => c.id === current.id) : -1;
    const next = problems[(idx + 1) % problems.length];
    setSelected(next.id);
    document.getElementById(`claim-${next.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const exportDoc = (mode: "clean" | "review") => {
    const go = () => window.open(`/api/rdti/items/${itemId}/export.docx?mode=${mode}`, "_blank");
    const unsupported = report.data?.totals.unsupported ?? 0;
    if (mode === "clean" && unsupported > 0) {
      modals.openConfirmModal({
        title: t("rdti.report.exportClean"),
        children: <Text size="sm">{t("rdti.report.unsupportedWarn", { count: unsupported })}</Text>,
        labels: { confirm: t("rdti.report.exportClean"), cancel: t("rdti.claim.close") },
        onConfirm: go,
      });
    } else go();
  };

  return (
    <Stack gap="sm">
      <Paper withBorder p="sm" radius="md">
        <Group justify="space-between" gap="xs">
          <Group gap="xs">
            {data.can_write && (
              <Button leftSection={<IconSparkles size={16} />} onClick={generate} loading={busy}>
                {sections.length ? t("rdti.report.regenerate") : t("rdti.report.generate")}
              </Button>
            )}
            {data.can_write && sections.length > 0 && (
              <Tooltip label={t("rdti.report.deleteDraft")}>
                <ActionIcon variant="subtle" color="red" size="lg" onClick={removeDraft}>
                  <IconTrash size={18} />
                </ActionIcon>
              </Tooltip>
            )}
          </Group>
          <Group gap="xs">
            <Button
              variant="default"
              size="xs"
              leftSection={<IconDownload size={14} />}
              onClick={() => exportDoc("clean")}
            >
              {t("rdti.report.exportClean")}
            </Button>
            <Button
              variant="default"
              size="xs"
              leftSection={<IconDownload size={14} />}
              onClick={() => exportDoc("review")}
            >
              {t("rdti.report.exportReview")}
            </Button>
          </Group>
        </Group>
        {sections.length > 0 && (
          <Group mt="sm" gap="md">
            <Switch
              label={t("rdti.report.review")}
              checked={review}
              onChange={(e) => setReview(e.currentTarget.checked)}
            />
            {review && (
              <>
                <Group gap={6}>
                  {STATUSES.map((s) => (
                    <Badge key={s} color={STATUS_COLOR[s]} variant={s === "polish" ? "outline" : "light"}>
                      {t(`rdti.status.${s}`)} {counts[s]}
                    </Badge>
                  ))}
                </Group>
                <Switch
                  size="xs"
                  label={t("rdti.report.onlyRed")}
                  checked={onlyProblems}
                  onChange={(e) => setOnlyProblems(e.currentTarget.checked)}
                />
                <Button
                  size="xs"
                  variant="light"
                  color="red"
                  leftSection={<IconArrowDown size={14} />}
                  onClick={nextProblem}
                  disabled={!counts.unsupported && !counts.needs_review}
                >
                  {t("rdti.report.next")}
                </Button>
              </>
            )}
          </Group>
        )}
      </Paper>

      {sections.length === 0 ? (
        <Text c="dimmed" size="sm">
          {t("rdti.report.empty")}
        </Text>
      ) : (
        <Grid gutter="md">
          <Grid.Col span={{ base: 12, lg: review && current ? 7 : 12 }}>
            <Stack gap="sm">
              {sections.map((s) => (
                <SectionCard
                  key={s.id}
                  data={data}
                  section={s}
                  review={review}
                  onlyProblems={onlyProblems}
                  selected={selected}
                  onSelect={setSelected}
                />
              ))}
            </Stack>
          </Grid.Col>
          {review && current && currentSection && (
            <Grid.Col span={{ base: 12, lg: 5 }}>
              <Box pos="sticky" top={70}>
                <ClaimPanel
                  data={data}
                  claim={current}
                  section={currentSection}
                  onClose={() => setSelected(null)}
                  onSelect={setSelected}
                />
              </Box>
            </Grid.Col>
          )}
        </Grid>
      )}
    </Stack>
  );
}

function SectionCard({
  data,
  section,
  review,
  onlyProblems,
  selected,
  onSelect,
}: {
  data: Workbench;
  section: Section;
  review: boolean;
  onlyProblems: boolean;
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  const { t } = useTranslation();
  const label = useElementLabel();
  const refresh = useRefreshRdti(data.item.id);
  const [editing, setEditing] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const el = data.rules.elements.find((e) => e.key === section.element);

  const save = async () => {
    if (editing === null) return;
    setBusy(true);
    try {
      await command("rdti.update_section", {
        section_id: section.id,
        body: editing,
        expected_version: section.version,
      });
      setEditing(null);
      refresh();
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };
  const lock = (locked: boolean) =>
    command("rdti.lock_section", { section_id: section.id, locked })
      .then(refresh)
      .catch((e) => notifyError(e));
  const recheck = async () => {
    setBusy(true);
    try {
      await command("rdti.recheck_section", { section_id: section.id });
      refresh();
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Paper withBorder p="md" radius="md">
      <Group justify="space-between" mb="xs" wrap="nowrap">
        <Group gap="xs">
          <Text fw={600}>{section.heading}</Text>
          <Text size="xs" c="dimmed">
            {label(el, section.element)}
          </Text>
          {section.locked && (
            <Badge size="xs" color="dark" leftSection={<IconLock size={10} />}>
              {t("rdti.report.locked")}
            </Badge>
          )}
        </Group>
        <Group gap={2} wrap="nowrap">
          {data.can_write && !section.locked && editing === null && (
            <Tooltip label={t("rdti.report.edit")}>
              <ActionIcon variant="subtle" onClick={() => setEditing(section.body)}>
                <IconPencil size={16} />
              </ActionIcon>
            </Tooltip>
          )}
          {data.can_write && (
            <Tooltip label={t("rdti.report.recheck")}>
              <ActionIcon variant="subtle" onClick={recheck} loading={busy && editing === null}>
                <IconRefresh size={16} />
              </ActionIcon>
            </Tooltip>
          )}
          {data.can_approve && (
            <Tooltip label={section.locked ? t("rdti.report.unlock") : t("rdti.report.lock")}>
              <ActionIcon variant="subtle" onClick={() => lock(!section.locked)}>
                {section.locked ? <IconLockOpen size={16} /> : <IconLock size={16} />}
              </ActionIcon>
            </Tooltip>
          )}
        </Group>
      </Group>
      {editing !== null ? (
        <Stack gap="xs">
          <Textarea
            autosize
            minRows={4}
            value={editing}
            onChange={(e) => setEditing(e.currentTarget.value)}
          />
          <Text size="xs" c="dimmed">
            {t("rdti.report.editHint")}
          </Text>
          <Group justify="flex-end" gap="xs">
            <Button variant="default" size="xs" onClick={() => setEditing(null)}>
              {t("rdti.claim.close")}
            </Button>
            <Button size="xs" onClick={save} loading={busy}>
              {t("rdti.report.save")}
            </Button>
          </Group>
        </Stack>
      ) : review ? (
        <ClaimText section={section} onlyProblems={onlyProblems} selected={selected} onSelect={onSelect} />
      ) : (
        <Text size="sm" style={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>
          {section.body}
        </Text>
      )}
    </Paper>
  );
}

/** Renders the section body with each claim as a coloured span. Our own
 * wording (polish) is plain text on purpose: it has nothing to point to. */
function ClaimText({
  section,
  onlyProblems,
  selected,
  onSelect,
}: {
  section: Section;
  onlyProblems: boolean;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  const parts: React.ReactNode[] = [];
  let pos = 0;
  const body = section.body;
  for (const c of [...section.claims].sort((a, b) => a.start - b.start)) {
    if (c.start < pos) continue;
    if (c.start > pos) parts.push(<Fragment key={`g${pos}`}>{body.slice(pos, c.start)}</Fragment>);
    const text = body.slice(c.start, c.end);
    const dim = onlyProblems && !PROBLEM.includes(c.status);
    if (c.status === "polish") {
      parts.push(
        <Tooltip key={c.id} label={t("rdti.status.polish")} openDelay={400}>
          <span id={`claim-${c.id}`} style={{ color: "var(--mantine-color-dimmed)", opacity: dim ? 0.4 : 1 }}>
            {text}
          </span>
        </Tooltip>,
      );
    } else {
      const color = STATUS_COLOR[c.status];
      const active = c.id === selected;
      parts.push(
        <span
          key={c.id}
          id={`claim-${c.id}`}
          role="button"
          tabIndex={0}
          onClick={() => onSelect(c.id)}
          onKeyDown={(e) => e.key === "Enter" && onSelect(c.id)}
          title={t(`rdti.status.${c.status}`)}
          style={{
            cursor: "pointer",
            borderRadius: 3,
            padding: "1px 0",
            opacity: dim ? 0.4 : 1,
            background: `var(--mantine-color-${color}-light)`,
            borderBottom: `2px solid var(--mantine-color-${color}-filled)`,
            outline: active ? `2px solid var(--mantine-color-${color}-filled)` : undefined,
          }}
        >
          {text}
        </span>,
      );
    }
    pos = c.end;
  }
  if (pos < body.length) parts.push(<Fragment key="tail">{body.slice(pos)}</Fragment>);
  return (
    <Text size="sm" component="div" style={{ whiteSpace: "pre-wrap", lineHeight: 1.9 }}>
      {parts}
    </Text>
  );
}

function Highlight({ text, start, end }: { text: string; start: number | null; end: number | null }) {
  if (start === null || end === null || start < 0 || end > text.length) return <>{text}</>;
  return (
    <>
      {text.slice(0, start)}
      <mark style={{ background: "var(--mantine-color-yellow-3)", color: "inherit", padding: "0 1px" }}>
        {text.slice(start, end)}
      </mark>
      {text.slice(end)}
    </>
  );
}

function ClaimPanel({
  data,
  claim,
  section,
  onClose,
  onSelect,
}: {
  data: Workbench;
  claim: Claim;
  section: Section;
  onClose: () => void;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  const refresh = useRefreshRdti(data.item.id);
  const [adding, setAdding] = useState(false);
  const canEdit = data.can_write && !section.locked;

  const act = async (action: "confirm" | "polish" | "recompute", acknowledge_facts = false) => {
    try {
      await command("rdti.review_claim", { claim_id: claim.id, action, acknowledge_facts });
      refresh();
    } catch (e) {
      if (e instanceof ApiError && e.code === "polish_has_facts") {
        modals.openConfirmModal({
          title: t("rdti.claim.markPolish"),
          children: <Text size="sm">{t("rdti.claim.ackFacts")}</Text>,
          labels: { confirm: t("rdti.claim.markPolish"), cancel: t("rdti.claim.close") },
          onConfirm: () => act(action, true),
        });
      } else notifyError(e);
    }
  };
  const removeCitation = (id: string) =>
    command("rdti.remove_citation", { citation_id: id })
      .then(refresh)
      .catch((e) => notifyError(e));

  return (
    <Paper withBorder p="md" radius="md" shadow="sm">
      <Group justify="space-between" mb="xs">
        <Badge color={STATUS_COLOR[claim.status]}>{t(`rdti.status.${claim.status}`)}</Badge>
        <ActionIcon variant="subtle" onClick={onClose} aria-label={t("rdti.claim.close")}>
          <IconX size={16} />
        </ActionIcon>
      </Group>
      <Text size="sm" fw={500} mb="xs">
        {claim.text}
      </Text>
      {claim.note && (
        <Text size="xs" c="dimmed" mb="xs">
          {claim.note}
        </Text>
      )}
      {claim.fact_warning && (
        <Alert color="orange" variant="light" py={6} mb="xs">
          <Text size="xs">{t("rdti.claim.factWarn")}</Text>
        </Alert>
      )}
      {claim.confirmed_by && (
        <Text size="xs" c="teal" mb="xs">
          {t("rdti.claim.confirmedBy", { name: claim.confirmed_by })}
        </Text>
      )}
      {canEdit && (
        <Group gap={6} mb="sm">
          <Button size="xs" color="teal" leftSection={<IconCheck size={14} />} onClick={() => act("confirm")}>
            {t("rdti.claim.confirm")}
          </Button>
          <Button size="xs" variant="default" onClick={() => act("polish")}>
            {t("rdti.claim.markPolish")}
          </Button>
          <Button size="xs" variant="subtle" onClick={() => act("recompute")}>
            {t("rdti.claim.recompute")}
          </Button>
        </Group>
      )}

      <Group justify="space-between" mb={6}>
        <Text size="sm" fw={600}>
          {t("rdti.claim.sources")}
        </Text>
        {canEdit && (
          <Button
            size="compact-xs"
            variant="light"
            leftSection={<IconPlus size={12} />}
            onClick={() => setAdding(true)}
          >
            {t("rdti.claim.addSource")}
          </Button>
        )}
      </Group>
      <ScrollArea.Autosize mah="55vh">
        <Stack gap="sm">
          {claim.citations.length === 0 && (
            <Text size="sm" c="dimmed">
              {t("rdti.claim.noSources")}
            </Text>
          )}
          {claim.citations.map((c) => (
            <CitationCard
              key={c.id}
              citation={c}
              canEdit={canEdit}
              onRemove={() => removeCitation(c.id)}
              onSelect={onSelect}
            />
          ))}
        </Stack>
      </ScrollArea.Autosize>
      <AddSource
        itemId={data.item.id}
        claim={claim}
        activityId={section.activity_id}
        opened={adding}
        onClose={() => setAdding(false)}
      />
    </Paper>
  );
}

function CitationCard({
  citation: c,
  canEdit,
  onRemove,
  onSelect,
}: {
  citation: Citation;
  canEdit: boolean;
  onRemove: () => void;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  const [showContext, setShowContext] = useState(false);
  const ctx = useQuery({
    queryKey: ["rdti", "passage", c.passage.id],
    queryFn: () => api.get<PassageContext>(`/rdti/passages/${c.passage.id}`),
    enabled: showContext,
  });
  const supportColor = c.support === "supports" ? "teal" : c.support === "partial" ? "yellow" : "red";
  return (
    <Paper withBorder p="sm" radius="sm" bg="var(--mantine-color-body)">
      <Group justify="space-between" gap={4} mb={4} wrap="nowrap">
        <Text size="xs" c="dimmed" lineClamp={1}>
          {c.passage.file_name} · {c.passage.location}
          {!c.passage.is_current && " · old version"}
        </Text>
        <Group gap={2} wrap="nowrap">
          <Tooltip label={t("rdti.claim.openOriginal")}>
            <ActionIcon
              variant="subtle"
              size="sm"
              component="a"
              href={fileUrl(c.passage.file_id, c.passage.page)}
              target="_blank"
            >
              <IconExternalLink size={14} />
            </ActionIcon>
          </Tooltip>
          {canEdit && (
            <Tooltip label={t("rdti.claim.removeSource")}>
              <ActionIcon variant="subtle" size="sm" color="red" onClick={onRemove}>
                <IconTrash size={14} />
              </ActionIcon>
            </Tooltip>
          )}
        </Group>
      </Group>
      <Group gap={4} mb={6}>
        <Badge size="xs" variant="light" color={c.verified ? "teal" : "red"}>
          {c.verified ? t("rdti.claim.verified") : t("rdti.claim.notVerified")}
        </Badge>
        <Badge size="xs" variant="outline" color={supportColor}>
          {t(`rdti.claim.${c.support}`)}
        </Badge>
      </Group>
      {showContext && ctx.data?.before && (
        <Text size="xs" c="dimmed" mb={4}>
          {ctx.data.before.text}
        </Text>
      )}
      <Text size="sm" style={{ lineHeight: 1.6 }}>
        {c.verified ? (
          <Highlight text={c.passage.text} start={c.quote_start} end={c.quote_end} />
        ) : (
          c.passage.text
        )}
      </Text>
      {!c.verified && (
        <Text size="xs" c="red" mt={4}>
          “{c.quote}”
        </Text>
      )}
      {showContext && ctx.data?.after && (
        <Text size="xs" c="dimmed" mt={4}>
          {ctx.data.after.text}
        </Text>
      )}
      {c.rationale && (
        <Text size="xs" c="dimmed" mt={4} fs="italic">
          {c.rationale}
        </Text>
      )}
      <Anchor size="xs" mt={4} component="button" onClick={() => setShowContext((v) => !v)}>
        {t("rdti.claim.context")}
      </Anchor>
      {showContext && ctx.data && ctx.data.cited_by.length > 1 && (
        <Stack gap={2} mt={4}>
          <Text size="xs" fw={600}>
            {t("rdti.claim.alsoCites")}
          </Text>
          {ctx.data.cited_by.map((x) => (
            <Anchor
              key={x.claim_id}
              size="xs"
              component="button"
              ta="left"
              onClick={() => onSelect(x.claim_id)}
              lineClamp={1}
            >
              {x.heading}: {x.text}
            </Anchor>
          ))}
        </Stack>
      )}
    </Paper>
  );
}

/** Pick a passage, then select (or type) the exact words that back the
 * claim. The server only accepts a quote it can find in the passage. */
function AddSource({
  itemId,
  claim,
  activityId,
  opened,
  onClose,
}: {
  itemId: string;
  claim: Claim;
  activityId: string;
  opened: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const refresh = useRefreshRdti(itemId);
  const [scope, setScope] = useState<"activity" | "all">("all");
  const [search, setSearch] = useState("");
  const [picked, setPicked] = useState<Passage | null>(null);
  const [quote, setQuote] = useState("");
  const list = usePassages(
    itemId,
    { activity_id: scope === "activity" ? activityId : undefined, search, limit: 50 },
    opened,
  );

  const reset = () => {
    setPicked(null);
    setQuote("");
    setSearch("");
    onClose();
  };
  const save = async () => {
    if (!picked) return;
    try {
      await command("rdti.add_citation", { claim_id: claim.id, chunk_id: picked.id, quote });
      refresh();
      reset();
    } catch (e) {
      notifyError(e);
    }
  };
  const takeSelection = () => {
    const sel = window.getSelection()?.toString().trim();
    if (sel) setQuote(sel);
  };

  return (
    <Modal opened={opened} onClose={reset} title={t("rdti.claim.addSource")} size="xl">
      <Text size="sm" mb="sm" c="dimmed">
        {claim.text}
      </Text>
      {!picked ? (
        <Stack gap="xs">
          <Group>
            <SegmentedControl
              size="xs"
              value={scope}
              onChange={(v) => setScope(v as "activity" | "all")}
              data={[
                { value: "activity", label: t("rdti.claim.thisActivity") },
                { value: "all", label: t("rdti.activities.all") },
              ]}
            />
            <TextInput
              size="xs"
              placeholder={t("rdti.materials.search")}
              value={search}
              onChange={(e) => setSearch(e.currentTarget.value)}
              flex={1}
            />
          </Group>
          <ScrollArea h={380}>
            <Stack gap={6}>
              {(list.data ?? []).map((p) => (
                <Paper
                  key={p.id}
                  withBorder
                  p="xs"
                  style={{ cursor: "pointer" }}
                  onClick={() => setPicked(p)}
                >
                  <Text size="xs" c="dimmed">
                    {p.file_name} · {p.location}
                  </Text>
                  <Text size="sm" lineClamp={4}>
                    {p.text}
                  </Text>
                </Paper>
              ))}
              {list.data?.length === 0 && (
                <Text size="sm" c="dimmed">
                  {t("rdti.claim.noPassages")}
                </Text>
              )}
            </Stack>
          </ScrollArea>
        </Stack>
      ) : (
        <Stack gap="xs">
          <Text size="xs" c="dimmed">
            {picked.file_name} · {picked.location} ·{" "}
            <Anchor size="xs" component="button" onClick={() => setPicked(null)}>
              {t("rdti.claim.pickAnother")}
            </Anchor>
          </Text>
          <Paper withBorder p="sm" onMouseUp={takeSelection}>
            <Text size="sm" style={{ lineHeight: 1.6, userSelect: "text" }}>
              {picked.text}
            </Text>
          </Paper>
          <Text size="xs" c="dimmed">
            {t("rdti.claim.selectHint")}
          </Text>
          <Textarea
            label={t("rdti.claim.quote")}
            autosize
            minRows={2}
            value={quote}
            onChange={(e) => setQuote(e.currentTarget.value)}
          />
          <Group justify="flex-end">
            <Button onClick={save} disabled={quote.trim().length < 8}>
              {t("rdti.claim.addSource")}
            </Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}
