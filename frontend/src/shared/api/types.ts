/** Shapes of the read endpoints (queries return plain JSON objects). */

export interface WorkspaceRef {
  id: string;
  key: string;
  name: string;
  item_label: string;
  permissions: string[];
}

export interface Me {
  user: {
    id: string;
    email: string;
    full_name: string;
    is_superadmin: boolean;
    locale: string;
    preferences: Record<string, any>;
  };
  csrf: string;
  is_superadmin: boolean;
  workspaces: WorkspaceRef[];
}

export interface ColumnSpec {
  key: string;
  label: string;
  type: string;
  source: "core" | "data" | "role" | "mirror" | "computed";
  kind: "text" | "number" | "date" | "datetime" | "bool" | "ref" | "multi" | "json";
  config: Record<string, any>;
  editable: boolean;
  required: boolean;
  group: string | null;
  position: number;
  rollover: "carry" | "clear" | "add_year";
  hidden_by_default: boolean;
}

export interface StatusDef {
  key: string;
  label: string;
  color: string;
  category: "todo" | "active" | "waiting" | "done" | "cancelled";
  position: number;
  is_default: boolean;
  is_archived: boolean;
}

export interface Board {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  icon: string | null;
  position: number;
  period_fiscal_year_id: string | null;
  settings: { statuses?: string[] | null; fields?: string[] | null; [k: string]: any };
  archived: boolean;
}

export interface LookupList {
  id: string;
  key: string;
  label: string;
  values: { id: string; label: string; parent_id: string | null; aliases: string[]; is_active: boolean }[];
}

export interface FieldDefinition {
  id: string;
  entity_kind: string;
  key: string;
  label: string;
  type: string;
  config: Record<string, any>;
  group: string | null;
  description: string | null;
  is_required: boolean;
  rollover: string;
  track_changes: boolean;
  is_archived: boolean;
  position: number;
}

export interface WorkspaceSchema {
  workspace: { id: string; key: string; name: string; item_label: string; settings: Record<string, any> };
  permissions: string[];
  boards: Board[];
  columns: ColumnSpec[];
  statuses: StatusDef[];
  task_statuses: StatusDef[];
  roles: { key: string; label: string; allow_multiple: boolean; is_archived: boolean }[];
  field_definitions: FieldDefinition[];
  fiscal_years: { id: string; label: string; start_date: string; end_date: string }[];
  lookups: LookupList[];
}

export interface ItemRow {
  id: string;
  workspace_id: string;
  board_id: string;
  name: string;
  client: string | null;
  client_name: string | null;
  entity: string | null;
  entity_name: string | null;
  status: string | null;
  fiscal_year: string | null;
  due_date: string | null;
  created_at: string;
  updated_at: string;
  is_archived: boolean;
  archive_source: string | null;
  archive_ref: string | null;
  archived_at: string | null;
  highlight_color: string | null;
  rolled_from_id: string | null;
  version: number;
  data: Record<string, any>;
  roles: Record<string, string[]>;
  mirrors: Record<string, any>;
  task_count: number;
  open_task_count: number;
  comment_count: number;
  last_comment: { body: string; author: string | null; created_at: string } | null;
  members?: { id: string; user_id: string; role_key: string; assigned_date: string | null }[];
}

export interface DirectoryUser {
  id: string;
  full_name: string;
  email: string;
  is_placeholder: boolean;
}

export interface FilterRule {
  field: string;
  operator: string;
  value?: any;
}
export interface FilterGroup {
  op: "and" | "or";
  rules: (FilterRule | FilterGroup)[];
}

export interface ViewConfig {
  columns: { key: string; width?: number | null; hidden?: boolean; pinned?: "left" | "right" | null }[];
  filter?: FilterGroup | null;
  sort: { field: string; dir: "asc" | "desc" }[];
  search?: string | null;
  group_by?: string | null;
  row_height?: "compact" | "normal" | "tall";
}

export interface SavedView {
  id: string;
  workspace_id: string;
  board_id: string | null;
  name: string;
  scope: "personal" | "shared";
  is_default: boolean;
  is_mine: boolean;
  config: ViewConfig;
}

export interface Task {
  id: string;
  item_id: string;
  parent_task_id: string | null;
  title: string;
  status: string | null;
  priority: string | null;
  due_date: string | null;
  period: string | null;
  position: number;
  members: Record<string, string[]>;
  created_at: string;
}

export interface CommentRow {
  id: string;
  author_id: string | null;
  author: string | null;
  body: string;
  created_at: string;
  edited_at: string | null;
  is_mine: boolean;
}

export interface AuditEntry {
  id: number;
  command_id: string;
  command: string | null;
  batch_id: string | null;
  origin: string;
  actor_id: string | null;
  actor: string;
  entity_type: string;
  entity_id: string;
  entity_name: string | null;
  parent_type: string | null;
  parent_id: string | null;
  workspace_id: string | null;
  op: "create" | "update" | "delete";
  changes: { field: string; before: any; after: any; hidden?: boolean }[];
  reverted: boolean;
  created_at: string;
}

export interface DataModelColumn {
  name: string;
  type: string;
  nullable: boolean;
  primary_key: boolean;
  unique: boolean;
  indexed: boolean;
  has_default: boolean;
  references: { table: string; column: string; on_delete: string | null } | null;
}

export interface DataModelTable {
  name: string;
  module: string;
  model: string;
  description: string | null;
  entity_type: string | null;
  audited: boolean;
  soft_delete: boolean;
  has_custom_data: boolean;
  columns: DataModelColumn[];
  unique_together: string[][];
  indexes: { name: string; columns: string[] }[];
}

export interface DataModelField {
  entity_kind: string;
  table: string | null;
  key: string;
  label: string;
  type: string;
  is_archived: boolean;
  mirror_of: { of: string | null; field: string | null } | null;
  stored_in: string | null;
}

export interface DataModel {
  tables: DataModelTable[];
  custom_fields: { workspace: { id: string; key: string; name: string }; fields: DataModelField[] }[];
  field_types: Record<string, string>;
}
