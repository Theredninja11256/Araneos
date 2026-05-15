/**
 * Typed API client for the Data Platform backend.
 *
 * All requests go through the Vite dev proxy (/api → http://localhost:8000/api),
 * so no absolute URL is needed during development.
 */

const BASE = "/api/v1";

// ── Health ─────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  engine_mode: string;
  version: string;
}

// ── Stage 2: profiling + scoring types ────────────────────────────────────

export type ColumnType =
  | "numeric"
  | "date"
  | "identifier"
  | "categorical"
  | "text";

export interface TopValue {
  value: string;
  count: number;
}

export interface ColumnProfile {
  name: string;
  inferred_type: ColumnType;
  dtype_raw: string;
  is_critical_field: boolean;
  // Null
  null_count: number;
  null_pct: number;
  // Uniqueness
  unique_count: number;
  uniqueness_ratio: number;
  is_high_cardinality: boolean;
  // Top values
  top_values: TopValue[];
  // Numeric (null when not numeric)
  min: number | null;
  max: number | null;
  mean: number | null;
  median: number | null;
  std: number | null;
  outlier_count: number | null;
  outlier_pct: number | null;
  // Categorical / text
  casing_inconsistency_count: number | null;
  // Date
  invalid_date_count: number | null;
  date_formats_detected: string[] | null;
  // Issues
  issues: string[];
}

export interface DatasetIssue {
  column: string;
  severity: "critical" | "warning" | "info";
  detail: string;
}

export interface DatasetProfile {
  file_name: string;
  file_path: string;
  engine_used: string;
  row_count: number;
  column_count: number;
  duplicate_row_count: number;
  duplicate_row_pct: number;
  columns: ColumnProfile[];
  dataset_issues: DatasetIssue[];
}

export interface ScorePenalty {
  reason: string;
  points_deducted: number;
  severity: "critical" | "high" | "medium" | "low";
  column?: string;
}

export interface CriticalFieldIssue {
  field: string;
  null_count: number;
  null_pct: number;
  detail: string;
}

export type Grade = "Green" | "Amber" | "Red";

export interface DatasetScore {
  score: number;
  grade: Grade;
  penalties: ScorePenalty[];
  critical_field_issues: CriticalFieldIssue[];
  summary: string;
}

export interface DatasetResult {
  original_filename: string;
  saved_as: string;
  size_bytes: number;
  profile: DatasetProfile;
  score: DatasetScore;
}

// ── Stage 3: proposal types ────────────────────────────────────────────────

export type ProposalType =
  | "cross_dataset_fill"
  | "interpolation"
  | "data_correction";

export type SourceMethod =
  // null-fill methods
  | "cross_dataset_lookup"
  | "linear_interpolation"           // legacy — no longer generated
  | "date_inference"
  | "sequential_id_inference"
  // data correction methods
  | "format_correction"
  | "date_format_standardisation"
  | "value_cleaning"
  | "business_rule";

export type ProposalStatus = "pending" | "approved" | "rejected";

export interface Proposal {
  id: string;
  session_id: string;
  proposal_type: ProposalType;
  source_method: SourceMethod;
  dataset_name: string;
  row_index: number | null;
  row_identifier: string | null;
  column_name: string;
  original_value: string | null;
  proposed_value: string;
  explanation: string;
  confidence: number;
  status: ProposalStatus;
  /** Cross-dataset fill metadata (null for interpolation proposals) */
  source_dataset: string | null;
  source_column: string | null;
  join_key: string | null;
  join_value: string | null;
  created_at: string | null;
  reviewed_at: string | null;
  user_decision: string | null;
}

export interface ProposalsSummary {
  total: number;
  by_type: Record<string, number>;
  by_confidence: { high: number; medium: number; low: number };
}

export interface ProposalsResponse {
  session_id: string;
  total: number;
  by_type: Record<string, number>;
  by_confidence: { high: number; medium: number; low: number };
  proposals: Proposal[];
}

export interface UploadResponse {
  session_id: string;
  uploaded: number;
  datasets: DatasetResult[];
  proposals_summary: ProposalsSummary;
}

// ── Stage 12: Analyst rules ────────────────────────────────────────────────

export interface AnalystRules {
  min_premium: number | null;       // default 50
  max_premium: number | null;       // null = disabled
  max_ncd: number | null;           // null = disabled
  date_format_standard: string;     // strftime, default "%d-%m-%y"
  currency_symbol: string;          // default "£"
}

export const DEFAULT_ANALYST_RULES: AnalystRules = {
  min_premium: 50,
  max_premium: null,
  max_ncd: null,
  date_format_standard: "%d-%m-%y",
  currency_symbol: "£",
};

// ── Stage 12: Row context types ────────────────────────────────────────────

export interface ContextRow {
  _position: "above" | "target" | "below";
  [column: string]: string | null;
}

export interface DatasetContext {
  dataset: string;
  column: string;
  columns: string[];
  rows: ContextRow[];
  total_rows: number;
  highlighted_column: string | null;
  /** Only for source context (cross-dataset fills) */
  matched_key?: string;
  matched_value?: string;
  match_row_index?: number;
}

export interface ProposalContext {
  target: DatasetContext;
  source: DatasetContext | null;
}

// ── Helpers ────────────────────────────────────────────────────────────────

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string })?.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ── Endpoints ──────────────────────────────────────────────────────────────

export async function checkHealth(): Promise<HealthResponse> {
  const res = await fetch(`${BASE}/health`);
  return handleResponse<HealthResponse>(res);
}

export async function uploadDatasets(
  files: File[],
  analystRules?: AnalystRules,
): Promise<UploadResponse> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  if (analystRules) {
    // Map frontend field names to backend field names
    const backendRules = {
      minimum_premium:      analystRules.min_premium,
      maximum_premium:      analystRules.max_premium,
      max_ncd:              analystRules.max_ncd,
      date_format_standard: analystRules.date_format_standard,
      currency_symbol:      analystRules.currency_symbol,
    };
    form.append("analyst_rules", JSON.stringify(backendRules));
  }

  const res = await fetch(`${BASE}/datasets/upload`, {
    method: "POST",
    body: form,
  });
  return handleResponse<UploadResponse>(res);
}

export async function getProposalContext(proposalId: string): Promise<ProposalContext> {
  const res = await fetch(`${BASE}/proposals/${proposalId}/context`);
  return handleResponse<ProposalContext>(res);
}

// ── Stage 13: Bulk standard-cleaning review ────────────────────────────────

export interface BulkReviewResult {
  updated: number;
  decision: string;
  updated_ids: string[];
}

/** Source methods considered low-risk "standard cleaning" (mirrors backend constant). */
export const STANDARD_CLEANING_METHODS = new Set([
  "format_correction",
  "date_format_standardisation",
  "value_cleaning",
]);

export async function bulkApproveStandardCleaning(sessionId: string): Promise<BulkReviewResult> {
  const res = await fetch(`${BASE}/sessions/${sessionId}/standard-cleaning/approve`, {
    method: "PATCH",
  });
  return handleResponse<BulkReviewResult>(res);
}

export async function bulkRejectStandardCleaning(sessionId: string): Promise<BulkReviewResult> {
  const res = await fetch(`${BASE}/sessions/${sessionId}/standard-cleaning/reject`, {
    method: "PATCH",
  });
  return handleResponse<BulkReviewResult>(res);
}

export async function getProposals(sessionId: string): Promise<ProposalsResponse> {
  const res = await fetch(`${BASE}/proposals/${sessionId}`);
  return handleResponse<ProposalsResponse>(res);
}

export async function approveProposal(proposalId: string): Promise<Proposal> {
  const res = await fetch(`${BASE}/proposals/${proposalId}/approve`, {
    method: "PATCH",
  });
  return handleResponse<Proposal>(res);
}

export async function rejectProposal(proposalId: string): Promise<Proposal> {
  const res = await fetch(`${BASE}/proposals/${proposalId}/reject`, {
    method: "PATCH",
  });
  return handleResponse<Proposal>(res);
}

// ── Stage 7: Join Intelligence types ──────────────────────────────────────

export type InsightConfidence = "High" | "Medium" | "Low";

export interface JoinInsight {
  id: string;
  name: string;
  explanation: string;
  columns_used: string[];
  confidence: InsightConfidence;
  cross_dataset: boolean;
}

export interface JoinReport {
  id: string;
  dataset_a: string;
  dataset_b: string;
  join_key: string;
  match_rate: number;
  matched_keys: number;
  total_keys_a: number;
  total_keys_b: number;
  unmatched_in_a: number;
  unmatched_in_b: number;
  base_dataset: string;
  insights: JoinInsight[];
}

export interface SingleDatasetInsightGroup {
  dataset: string;
  insights: JoinInsight[];
}

export interface JoinsResponse {
  session_id: string;
  join_reports: JoinReport[];
  single_dataset_insights: SingleDatasetInsightGroup[];
}

export interface GeneratedTable {
  insight_id: string;
  insight_name: string;
  row_count: number;
  columns: string[];
  rows: Record<string, unknown>[];
}

// ── Stage 7: Join Intelligence endpoints ──────────────────────────────────

export async function getJoins(sessionId: string): Promise<JoinsResponse> {
  const res = await fetch(`${BASE}/sessions/${sessionId}/joins`);
  return handleResponse<JoinsResponse>(res);
}

export async function generateInsight(
  sessionId: string,
  payload: {
    dataset_a: string;
    dataset_b?: string;
    join_key?: string;
    insight_id: string;
  }
): Promise<GeneratedTable> {
  const res = await fetch(`${BASE}/sessions/${sessionId}/joins/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<GeneratedTable>(res);
}

// ── Stage 8: CTO Dashboard types ──────────────────────────────────────────

export interface CriticalAlert {
  severity: "critical" | "high" | "medium" | "low";
  dataset: string;
  column: string;
  alert_text: string;
  points_impact: number;
}

export interface JoinOpportunity {
  dataset_a: string;
  dataset_b: string;
  join_key: string;
  match_rate: number;
  insights_count: number;
  business_summary: string;
  top_insights: string[];
}

export interface TrendData {
  current_score: number;
  benchmark_score: number;
  label: string;
  context: string;
}

export interface RAGSummary {
  green: number;
  amber: number;
  red: number;
  total: number;
}

export interface CTODashboard {
  session_id: string;
  overall_score: number;
  grade: Grade;
  dataset_count: number;
  rag_summary: RAGSummary;
  critical_alerts: CriticalAlert[];
  join_opportunities: JoinOpportunity[];
  trend_data: TrendData;
  generated_at: string;
}

// ── Stage 8: CTO Dashboard endpoints ──────────────────────────────────────

export async function getCTODashboard(sessionId: string): Promise<CTODashboard> {
  const res = await fetch(`${BASE}/sessions/${sessionId}/dashboard`);
  return handleResponse<CTODashboard>(res);
}

/**
 * Triggers a browser download of the HTML health report.
 * Uses a hidden anchor rather than fetch so the browser handles the file
 * download natively (Content-Disposition: attachment).
 */
export function downloadDashboardReport(sessionId: string): void {
  const a = document.createElement("a");
  a.href = `${BASE}/sessions/${sessionId}/dashboard/export`;
  a.download = `health_report_${sessionId.slice(0, 8)}.html`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

/**
 * Export a session's approved proposals as a downloadable ZIP.
 *
 * Returns a Blob (application/zip) rather than JSON, so we bypass
 * handleResponse and handle the error body manually.
 */
export async function exportSession(sessionId: string): Promise<Blob> {
  const res = await fetch(`${BASE}/sessions/${sessionId}/export`, {
    method: "POST",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      (body as { detail?: string })?.detail ?? `Export failed (HTTP ${res.status})`
    );
  }
  return res.blob();
}
