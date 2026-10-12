import { Button, Group, Select } from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import { useQueries, useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import { api } from "../../shared/api/client";
import { useDirectory, useMe } from "../../shared/api/hooks";
import type { AuditEntry, WorkspaceSchema } from "../../shared/api/types";
import { Page } from "../../shared/ui/Page";
import { buildCtx, useWorkspace } from "../../shared/workspace";
import { ActivityList } from "./ActivityList";

export function ActivityPage() {
  const { ctx } = useWorkspace();
  const dir = useDirectory();
  const me = useMe();
  const schemas = useQueries({
    queries: (me.data?.workspaces ?? []).map((w) => ({
      queryKey: ["schema", w.id],
      queryFn: () => api.get<WorkspaceSchema>(`/workspaces/${w.id}/schema`),
      staleTime: 300_000,
    })),
  });
  const ctxs = new Map(
    schemas.filter((s) => s.data).map((s) => [s.data!.workspace.id, buildCtx(s.data!, dir.users)]),
  );
  const [actor, setActor] = useState<string | null>(null);
  const [entity, setEntity] = useState<string | null>(null);
  const [op, setOp] = useState<string | null>(null);
  const [range, setRange] = useState<[Date | null, Date | null]>([null, null]);
  const [offset, setOffset] = useState(0);
  const q = useQuery({
    queryKey: ["activity", "global", actor, entity, op, range, offset],
    queryFn: () =>
      api.get<{ total: number; rows: AuditEntry[] }>("/activity", {
        actor_id: actor,
        entity_type: entity,
        op,
        date_from: range[0] ? dayjs(range[0]).format("YYYY-MM-DD") : undefined,
        date_to: range[1] ? dayjs(range[1]).format("YYYY-MM-DD") : undefined,
        limit: 100,
        offset,
      }),
  });
  return (
    <Page
      title="Activity"
      subtitle="Who changed what, across clients and items. Values are visible to managers."
    >
      <Group mb="md" wrap="wrap">
        <Select
          placeholder="Anyone"
          clearable
          searchable
          w={200}
          data={dir.users.map((u) => ({ value: u.id, label: u.full_name }))}
          value={actor}
          onChange={setActor}
        />
        <Select
          placeholder="Any record"
          clearable
          w={160}
          data={[
            { value: "item", label: "Items" },
            { value: "client", label: "Clients" },
            { value: "task", label: "Tasks" },
            { value: "item_member", label: "Teams" },
            { value: "comment", label: "Updates" },
          ]}
          value={entity}
          onChange={setEntity}
        />
        <Select
          placeholder="Any action"
          clearable
          w={150}
          data={[
            { value: "create", label: "Created" },
            { value: "update", label: "Changed" },
            { value: "delete", label: "Deleted" },
          ]}
          value={op}
          onChange={setOp}
        />
        <DatePickerInput
          type="range"
          placeholder="Any date"
          clearable
          w={240}
          value={range}
          onChange={setRange}
          valueFormat="DD/MM/YYYY"
        />
      </Group>
      <div style={{ maxWidth: 900 }}>
        <ActivityList
          entries={q.data?.rows ?? []}
          ctx={ctx}
          ctxFor={(id) => (id ? ctxs.get(id) : undefined)}
          showEntity
          canRevert={!!ctx?.can("audit.revert")}
        />
      </div>
      <Group mt="md">
        <Button
          size="xs"
          variant="default"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 100))}
        >
          Newer
        </Button>
        <Button
          size="xs"
          variant="default"
          disabled={offset + 100 >= (q.data?.total ?? 0)}
          onClick={() => setOffset(offset + 100)}
        >
          Older
        </Button>
      </Group>
    </Page>
  );
}
