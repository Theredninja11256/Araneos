/**
 * JoinIntelligencePage — Stage 7
 *
 * Displays all detected dataset join pairs for a session with:
 *   - Join key and match quality metrics
 *   - Rule-based insight suggestions for each pair
 *   - Inline "Generate" button that fetches and renders an aggregated table
 *
 * Single-dataset insights (no join required) are shown in a separate section.
 *
 * State
 * -----
 * joins        : full API response (fetched once on mount)
 * generatedTables  : Record<string, GeneratedTable>  — keyed by "<joinId>-<insightId>"
 * generatingKey    : string | null                   — the key currently in-flight
 */

import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  getJoins,
  generateInsight,
  type JoinReport,
  type JoinInsight,
  type SingleDatasetInsightGroup,
  type JoinsResponse,
  type GeneratedTable,
} from "../api/client";
import NavBar from "../components/NavBar";
import WorkflowProgress from "../components/WorkflowProgress";

// ── Confidence badge ──────────────────────────────────────────────────────────

function ConfidenceTag({ confidence }: { confidence: string }) {
  const styles: Record<string, string> = {
    High:   "bg-green-950  text-green-300  border-green-900",
    Medium: "bg-amber-950  text-amber-300  border-amber-900",
    Low:    "bg-slate-800  text-slate-400  border-slate-700",
  };
  return (
    <span className={`inline-block rounded-full border px-2 py-0.5 text-xs font-medium ${styles[confidence] ?? styles.Low}`}>
      {confidence}
    </span>
  );
}

// ── Match rate bar ────────────────────────────────────────────────────────────

function matchStrength(pct: number): { label: string; cls: string } {
  if (pct >= 85) return { label: "Strong",   cls: "bg-green-950 text-green-300" };
  if (pct >= 65) return { label: "Moderate", cls: "bg-amber-950 text-amber-300" };
  return           { label: "Weak",    cls: "bg-red-950   text-red-300"   };
}

function MatchRateBar({ rate }: { rate: number }) {
  const pct    = Math.round(rate * 100);
  const colour = pct >= 85 ? "bg-green-500" : pct >= 65 ? "bg-amber-400" : "bg-red-400";
  const { label, cls } = matchStrength(pct);

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-3">
        <div className="flex-1 h-2.5 rounded-full bg-slate-800 overflow-hidden">
          <div className={`h-full rounded-full transition-all ${colour}`} style={{ width: `${pct}%` }} />
        </div>
        <span className={`text-sm font-bold tabular-nums ${
          pct >= 85 ? "text-green-400" : pct >= 65 ? "text-amber-400" : "text-red-400"
        }`}>
          {pct}%
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${cls}`}>
          {label}
        </span>
        <span className="text-xs text-slate-500">
          {pct}% of records align
        </span>
      </div>
    </div>
  );
}

// ── Generated table ───────────────────────────────────────────────────────────

function InsightTable({ table }: { table: GeneratedTable }) {
  function formatCell(v: unknown): string {
    if (v === null || v === undefined) return "—";
    if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
    return String(v);
  }

  return (
    <div className="mt-3 rounded-lg border border-slate-700 overflow-x-auto">
      <div className="px-4 py-2 bg-slate-800 border-b border-slate-700 flex items-center justify-between">
        <p className="text-xs font-semibold text-slate-300">{table.insight_name}</p>
        <p className="text-xs text-slate-500">{table.row_count} rows</p>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-700">
            {table.columns.map((col) => (
              <th key={col} className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                {col.replace(/_/g, " ")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {table.rows.map((row, i) => (
            <tr key={i} className="hover:bg-slate-800/50 transition-colors">
              {table.columns.map((col) => (
                <td key={col} className="px-4 py-2 text-slate-300 font-mono text-xs">
                  {formatCell(row[col])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Insight card ──────────────────────────────────────────────────────────────

interface InsightCardProps {
  insight: JoinInsight;
  tableKey: string;
  generatingKey: string | null;
  generatedTables: Record<string, GeneratedTable>;
  onGenerate: (key: string, insight: JoinInsight) => void;
}

function InsightCard({
  insight,
  tableKey,
  generatingKey,
  generatedTables,
  onGenerate,
}: InsightCardProps) {
  const isGenerating = generatingKey === tableKey;
  const isDone = tableKey in generatedTables;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1.5">
            <span className="text-sm font-semibold text-slate-200">{insight.name}</span>
            <ConfidenceTag confidence={insight.confidence} />
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">{insight.explanation}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <span className="text-xs text-slate-600 font-medium">Columns:</span>
            {insight.columns_used.map((col) => (
              <span key={col} className="inline-block rounded bg-slate-800 border border-slate-700 px-1.5 py-0.5 font-mono text-[11px] text-slate-400">
                {col}
              </span>
            ))}
          </div>
        </div>
        <button
          onClick={() => onGenerate(tableKey, insight)}
          disabled={isGenerating || generatingKey !== null}
          className={[
            "shrink-0 rounded-xl px-3 py-1.5 text-xs font-semibold transition-colors",
            isDone
              ? "bg-slate-800 text-slate-400 hover:bg-slate-700"
              : isGenerating || generatingKey !== null
              ? "bg-slate-800 text-slate-600 cursor-not-allowed"
              : "bg-blue-700 text-white hover:bg-blue-600",
          ].join(" ")}
        >
          {isGenerating ? "Generating…" : isDone ? "Regenerate" : "Generate insight"}
        </button>
      </div>

      {isDone && <InsightTable table={generatedTables[tableKey]} />}
    </div>
  );
}

// ── Join report card ──────────────────────────────────────────────────────────

interface JoinCardProps {
  report: JoinReport;
  generatingKey: string | null;
  generatedTables: Record<string, GeneratedTable>;
  onGenerate: (key: string, insight: JoinInsight, report: JoinReport) => void;
}

function JoinCard({ report, generatingKey, generatedTables, onGenerate }: JoinCardProps) {
  const [expanded, setExpanded] = useState(false);   // collapsed by default

  const matchPct   = Math.round(report.match_rate * 100);
  const otherDs    = report.dataset_a === report.base_dataset ? report.dataset_b : report.dataset_a;
  const { label: strengthLabel } = matchStrength(matchPct);

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between px-6 py-5 cursor-pointer hover:bg-slate-800/50 transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex flex-wrap items-center gap-3 min-w-0">
          {/* Dataset pair */}
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm font-semibold text-slate-300 bg-slate-800 px-2.5 py-1 rounded-lg">
              {report.dataset_a}
            </span>
            <svg className="h-4 w-4 text-slate-600 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
            </svg>
            <span className="font-mono text-sm font-semibold text-slate-300 bg-slate-800 px-2.5 py-1 rounded-lg">
              {report.dataset_b}
            </span>
          </div>
          {/* Join key */}
          <span className="text-xs text-slate-500">
            via <span className="font-mono text-blue-400">{report.join_key}</span>
          </span>
          {/* Strength badge */}
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
            matchPct >= 85 ? "bg-green-950 text-green-300"
            : matchPct >= 65 ? "bg-amber-950 text-amber-300"
            : "bg-red-950 text-red-300"
          }`}>
            {strengthLabel} — {matchPct}%
          </span>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className="text-xs text-slate-600 hidden sm:inline">
            {report.insights.length} insight{report.insights.length !== 1 ? "s" : ""}
          </span>
          <svg className={`h-4 w-4 text-slate-600 transition-transform ${expanded ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
          </svg>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-slate-800 px-6 pb-6 pt-5 space-y-6">

          {/* Business meaning */}
          <div className="rounded-xl border border-blue-900/40 bg-blue-950/20 px-4 py-3">
            <p className="text-sm text-slate-200">
              This join links{" "}
              <span className="font-mono text-blue-300">{report.dataset_a}</span> to{" "}
              <span className="font-mono text-blue-300">{report.dataset_b}</span> using{" "}
              <span className="font-mono text-blue-400">{report.join_key}</span>.
            </p>
            <p className="mt-1 text-xs text-slate-400">
              Base table: <span className="font-mono text-slate-300">{report.base_dataset}</span>
              {" · "}
              {matchPct}% of <span className="font-mono text-slate-300">{report.base_dataset}</span> records
              have a matching <span className="font-mono text-slate-300">{report.join_key}</span> in{" "}
              <span className="font-mono text-slate-300">{otherDs}</span>.
            </p>
          </div>

          {/* Match quality */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-600 mb-3">
              Match quality
            </p>
            <MatchRateBar rate={report.match_rate} />
            <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-500">
              <span><strong className="text-slate-300">{report.matched_keys}</strong> matched rows</span>
              <span><strong className="text-slate-300">{report.total_keys_a}</strong> keys in {report.dataset_a}</span>
              <span><strong className="text-slate-300">{report.total_keys_b}</strong> keys in {report.dataset_b}</span>
            </div>
            {(report.unmatched_in_a > 0 || report.unmatched_in_b > 0) && (
              <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs">
                {report.unmatched_in_a > 0 && (
                  <span className="text-amber-400">
                    {report.unmatched_in_a} rows in {report.dataset_a} have no match in {report.dataset_b}
                  </span>
                )}
                {report.unmatched_in_b > 0 && (
                  <span className="text-amber-400">
                    {report.unmatched_in_b} rows in {report.dataset_b} have no match in {report.dataset_a}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Insights unlocked */}
          {report.insights.length > 0 ? (
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-slate-600 mb-3">
                Insights unlocked by this join
              </p>
              <div className="space-y-3">
                {report.insights.map((insight) => {
                  const key = `${report.id}-${insight.id}`;
                  return (
                    <InsightCard
                      key={key}
                      insight={insight}
                      tableKey={key}
                      generatingKey={generatingKey}
                      generatedTables={generatedTables}
                      onGenerate={(k, ins) => onGenerate(k, ins, report)}
                    />
                  );
                })}
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-600 italic">No insight rules matched this pair.</p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Single-dataset section ────────────────────────────────────────────────────

interface SingleDatasetSectionProps {
  group: SingleDatasetInsightGroup;
  generatingKey: string | null;
  generatedTables: Record<string, GeneratedTable>;
  sessionId: string;
  onGenerate: (
    key: string,
    insight: JoinInsight,
    datasetName: string
  ) => void;
}

function SingleDatasetSection({
  group,
  generatingKey,
  generatedTables,
  onGenerate,
}: SingleDatasetSectionProps) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 overflow-hidden">
      <div className="px-6 py-4 border-b border-slate-800">
        <p className="text-sm font-semibold text-slate-300">
          <span className="font-mono bg-slate-800 px-2 py-0.5 rounded-lg text-slate-300">{group.dataset}</span>
          <span className="ml-2 font-normal text-slate-500">— within-dataset insights</span>
        </p>
      </div>
      <div className="px-6 py-4 space-y-3">
        {group.insights.map((insight) => {
          const key = `${group.dataset}-${insight.id}`;
          return (
            <InsightCard
              key={key}
              insight={insight}
              tableKey={key}
              generatingKey={generatingKey}
              generatedTables={generatedTables}
              onGenerate={(k, ins) => onGenerate(k, ins, group.dataset)}
            />
          );
        })}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function JoinIntelligencePage() {
  const { sessionId } = useParams<{ sessionId: string }>();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [joins, setJoins] = useState<JoinsResponse | null>(null);

  const [generatingKey, setGeneratingKey] = useState<string | null>(null);
  const [generatedTables, setGeneratedTables] = useState<
    Record<string, GeneratedTable>
  >({});
  const [generateError, setGenerateError] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    setLoading(true);
    getJoins(sessionId)
      .then(setJoins)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load join analysis.")
      )
      .finally(() => setLoading(false));
  }, [sessionId]);

  /** Handle "Generate" for a cross-dataset insight */
  async function handleJoinGenerate(
    key: string,
    insight: JoinInsight,
    report: JoinReport
  ) {
    if (!sessionId) return;
    setGeneratingKey(key);
    setGenerateError(null);
    try {
      const result = await generateInsight(sessionId, {
        dataset_a: report.dataset_a,
        dataset_b: report.dataset_b,
        join_key: report.join_key,
        insight_id: insight.id,
      });
      setGeneratedTables((prev) => ({ ...prev, [key]: result }));
    } catch (err: unknown) {
      setGenerateError(
        err instanceof Error ? err.message : "Failed to generate insight."
      );
    } finally {
      setGeneratingKey(null);
    }
  }

  /** Handle "Generate" for a single-dataset insight */
  async function handleSingleGenerate(
    key: string,
    insight: JoinInsight,
    datasetName: string
  ) {
    if (!sessionId) return;
    setGeneratingKey(key);
    setGenerateError(null);
    try {
      const result = await generateInsight(sessionId, {
        dataset_a: datasetName,
        insight_id: insight.id,
      });
      setGeneratedTables((prev) => ({ ...prev, [key]: result }));
    } catch (err: unknown) {
      setGenerateError(
        err instanceof Error ? err.message : "Failed to generate insight."
      );
    } finally {
      setGeneratingKey(null);
    }
  }

  const totalInsights =
    (joins?.join_reports.reduce((s, r) => s + r.insights.length, 0) ?? 0) +
    (joins?.single_dataset_insights.reduce((s, g) => s + g.insights.length, 0) ?? 0);

  return (
    <div className="min-h-screen bg-slate-950">
      <NavBar />

      <main className="mx-auto max-w-7xl px-6 py-8 space-y-6">

        {/* Workflow progress */}
        <WorkflowProgress current="insights" />

        {/* Page title */}
        <div>
          <h1 className="text-xl font-semibold text-white">Join Intelligence</h1>
          <p className="mt-1 text-xs text-slate-500">
            Detect shared keys and explore cross-dataset insights.
          </p>
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-800 border-t-blue-500" />
            <p className="text-sm text-slate-500">Detecting dataset relationships…</p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="rounded-2xl border border-red-900 bg-red-950/30 px-5 py-4 text-sm text-red-300">
            {error}
          </div>
        )}

        {!loading && !error && joins && (
          <>
            {/* Summary strip */}
            <div className="flex items-center gap-5 text-sm">
              <span>
                <strong className="text-white">{joins.join_reports.length}</strong>
                <span className="ml-1.5 text-slate-600">pair{joins.join_reports.length !== 1 ? "s" : ""}</span>
              </span>
              <span className="text-slate-800">·</span>
              <span>
                <strong className="text-violet-400">{totalInsights}</strong>
                <span className="ml-1.5 text-slate-600">insight{totalInsights !== 1 ? "s" : ""}</span>
              </span>
            </div>

            {/* Generate error banner */}
            {generateError && (
              <div className="flex items-center justify-between rounded-2xl border border-red-900 bg-red-950/30 px-5 py-3 text-sm text-red-300">
                <span>{generateError}</span>
                <button onClick={() => setGenerateError(null)} className="ml-3 text-xs opacity-60 hover:opacity-100">
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            )}

            {/* ── Join pairs ── */}
            {joins.join_reports.length > 0 ? (
              <section>
                <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-slate-700">
                  Join pairs
                </p>
                <div className="space-y-2">
                  {joins.join_reports.map((report) => (
                    <JoinCard
                      key={report.id}
                      report={report}
                      generatingKey={generatingKey}
                      generatedTables={generatedTables}
                      onGenerate={handleJoinGenerate}
                    />
                  ))}
                </div>
              </section>
            ) : (
              <div className="rounded-xl border border-dashed border-slate-800 py-12 text-center">
                <p className="text-sm text-slate-500">No joinable pairs detected.</p>
                <p className="mt-1 text-xs text-slate-600">Upload datasets sharing a key column (e.g. <span className="font-mono">policy_number</span>).</p>
              </div>
            )}

            {/* ── Single-dataset insights ── */}
            {joins.single_dataset_insights.length > 0 && (
              <section>
                <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-slate-700">
                  Within-dataset insights
                </p>
                <div className="space-y-2">
                  {joins.single_dataset_insights.map((group) => (
                    <SingleDatasetSection
                      key={group.dataset}
                      group={group}
                      generatingKey={generatingKey}
                      generatedTables={generatedTables}
                      sessionId={sessionId ?? ""}
                      onGenerate={handleSingleGenerate}
                    />
                  ))}
                </div>
              </section>
            )}
          </>
        )}

      </main>
    </div>
  );
}
