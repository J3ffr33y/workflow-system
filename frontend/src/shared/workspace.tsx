import { useMemo } from "react";
import { useParams } from "react-router-dom";
import { useDirectory, useMe, useSchema } from "./api/hooks";
import type { ColumnSpec, DirectoryUser, StatusDef, WorkspaceRef, WorkspaceSchema } from "./api/types";

/** Lookup tables derived from a workspace schema; passed to field renderers. */
export interface FieldCtx {
  schema: WorkspaceSchema;
  columns: Map<string, ColumnSpec>;
  statuses: Map<string, StatusDef>;
  taskStatuses: Map<string, StatusDef>;
  fiscalYears: Map<string, string>;
  boards: Map<string, string>;
  lookupValues: Map<string, string>;
  users: Map<string, DirectoryUser>;
  userList: DirectoryUser[];
  can: (permission: string) => boolean;
}

export function buildCtx(schema: WorkspaceSchema, users: DirectoryUser[]): FieldCtx {
  const lookupValues = new Map<string, string>();
  for (const l of schema.lookups) for (const v of l.values) lookupValues.set(v.id, v.label);
  const perms = new Set(schema.permissions);
  return {
    schema,
    columns: new Map(schema.columns.map((c) => [c.key, c])),
    statuses: new Map(schema.statuses.map((s) => [s.key, s])),
    taskStatuses: new Map(schema.task_statuses.map((s) => [s.key, s])),
    fiscalYears: new Map(schema.fiscal_years.map((f) => [f.id, f.label])),
    boards: new Map(schema.boards.map((b) => [b.id, b.name])),
    lookupValues,
    users: new Map(users.map((u) => [u.id, u])),
    userList: users,
    can: (p) => perms.has(p),
  };
}

/** Current workspace from the URL (/w/:wsKey/...). */
export function useWorkspace(): {
  ref: WorkspaceRef | undefined;
  schema: WorkspaceSchema | undefined;
  ctx: FieldCtx | undefined;
  loading: boolean;
} {
  const { wsKey } = useParams();
  const me = useMe();
  const ref = me.data?.workspaces.find((w) => w.key === wsKey) ?? me.data?.workspaces[0];
  const schema = useSchema(ref?.id);
  const dir = useDirectory();
  const ctx = useMemo(
    () => (schema.data ? buildCtx(schema.data, dir.users) : undefined),
    [schema.data, dir.users],
  );
  return { ref, schema: schema.data, ctx, loading: me.isLoading || schema.isLoading };
}
