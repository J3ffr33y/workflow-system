export type Coverage = "sufficient" | "partial" | "missing";
export type ClaimStatus = "supported" | "needs_review" | "polish" | "unsupported";

export interface Activity {
  id: string;
  code: string;
  title: string;
  kind: "core" | "supporting";
  supports_activity_id: string | null;
  description: string | null;
}

export interface DocumentRow {
  file_id: string;
  name: string;
  version: number;
  version_id: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  uploaded_at: string;
  passages: number;
  assigned: number;
}

export interface Assessment {
  element: string;
  coverage: Coverage;
  rationale: string;
  summary_only: boolean;
  chunk_ids: string[];
  source: "ai" | "human";
  rule_version: string;
  updated_at: string;
}

export interface ChecklistRow {
  id: string;
  activity_id: string | null;
  element: string | null;
  question: string;
  preferred: string;
  alternatives: string[];
  example: string;
  status: "draft" | "sent" | "received" | "closed";
}

export interface RuleElement {
  key: string;
  label: string;
  label_zh: string;
  applies_to: string[];
  question: string;
  sufficient: string;
  preferred: string;
  alternatives: string[];
  example: string;
}

export interface Workbench {
  item: {
    id: string;
    name: string;
    workspace_id: string;
    workspace_key: string;
    client_id: string | null;
    client_name: string | null;
    ai_consent: boolean;
  };
  enabled: boolean;
  can_write: boolean;
  can_approve: boolean;
  ai: { provider: "fake" | "anthropic" | "off"; model: string; external: boolean };
  rules: { key: string; version: string; elements: RuleElement[]; writing_rules: string[] };
  activities: Activity[];
  documents: DocumentRow[];
  assessments: Record<string, Assessment[]>;
  checklist: ChecklistRow[];
  report: Record<string, { sections: number; counts: Record<ClaimStatus, number> }>;
}

export interface Passage {
  id: string;
  file_id: string;
  file_version_id: string;
  file_name: string;
  seq: number;
  page: number | null;
  location: string;
  bbox: number[] | null;
  text: string;
  activity_id: string | null;
  is_current: boolean;
  file_deleted?: boolean;
}

export interface Citation {
  id: string;
  quote: string;
  quote_start: number | null;
  quote_end: number | null;
  verified: boolean;
  support: "supports" | "partial" | "contradicts";
  rationale: string | null;
  passage: Passage;
}

export interface Claim {
  id: string;
  start: number;
  end: number;
  text: string;
  status: ClaimStatus;
  source: "ai" | "human";
  note: string | null;
  fact_warning: boolean;
  confirmed_by: string | null;
  confirmed_at: string | null;
  citations: Citation[];
}

export interface Section {
  id: string;
  activity_id: string;
  activity_code: string;
  activity_title: string;
  element: string;
  heading: string;
  body: string;
  locked: boolean;
  version: number;
  claims: Claim[];
}

export interface Report {
  sections: Section[];
  totals: Record<ClaimStatus, number>;
}

export interface PassageContext {
  passage: Passage;
  before: Passage | null;
  after: Passage | null;
  file: { id: string; name: string; current_version: number; deleted: boolean };
  cited_by: { claim_id: string; section_id: string; heading: string; text: string; status: ClaimStatus }[];
}

export const STATUS_COLOR: Record<ClaimStatus, string> = {
  supported: "teal",
  needs_review: "yellow",
  polish: "gray",
  unsupported: "red",
};

export const COVERAGE_COLOR: Record<Coverage, string> = {
  sufficient: "teal",
  partial: "yellow",
  missing: "red",
};
