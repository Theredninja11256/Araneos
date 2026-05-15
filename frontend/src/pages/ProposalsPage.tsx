/**
 * Proposals review page.
 * Compact inline stat strip replaces 4 SummaryCard blocks.
 * Status banners removed. Bottom export block removed.
 * Single Export CTA in the page header.
 */
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  getProposals, exportSession,
  bulkApproveStandardCleaning, bulkRejectStandardCleaning,
  STANDARD_CLEANING_METHODS,
} from "../api/client";
import type { Proposal } from "../api/client";
import ProposalsTable from "../components/ProposalsTable";
import NavBar from "../components/NavBar";
import WorkflowProgress from "../components/WorkflowProgress";

// ── Human-readable labels for source methods ──────────────────────────────

const METHOD_GROUP_LABELS: Record<string, string> = {
  format_correction:           "Casing / whitespace fixes",
  date_format_standardisation: "Date format normalisations",
  value_cleaning:              "Currency formatting fixes",
};

// ── Standard cleaning grouping card ──────────────────────────────────────

function StandardCleaningCard({
  proposals,
  sessionId,
  onRefresh,
}: {
  proposals: Proposal[];
  sessionId: string;
  onRefresh: () => void;
}) {
  const [expanded,    setExpanded]    = useState(false);
  const [processing,  setProcessing]  = useState(false);
  const [error,       setError]       = useState<string | null>(null);

  // Only count proposals that are STANDARD_CLEANING methods
  const all    = proposals.filter((p) => STANDARD_CLEANING_METHODS.has(p.source_method));
  const pending = all.filter((p) => p.status === "pending");
  const approved = all.filter((p) => p.status === "approved").length;
  const rejected = all.filter((p) => p.status === "rejected").length;

  if (all.length === 0) return null;

  // Breakdown by method for the summary
  const methodCounts: Record<string, number> = {};
  for (const p of pending) {
    methodCounts[p.source_method] = (methodCounts[p.source_method] ?? 0) + 1;
  }

  async function handleBulk(action: "approve" | "reject") {
    setProcessing(true); setError(null);
    try {
      if (action === "approve") await bulkApproveStandardCleaning(sessionId);
      else                      await bulkRejectStandardCleaning(sessionId);
      onRefresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Action failed.");
    } finally {
      setProcessing(false);
    }
  }

  const hasPending = pending.length > 0;

  return (
    <div className="rounded-2xl border border-slate-700 bg-slate-900">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4">
        <div className="flex items-center gap-3">
          <div>
            <p className="text-sm font-semibold text-white">Standard data cleaning</p>
            <p className="mt-0.5 text-xs text-slate-400">
              {all.length} low-risk formatting fixes
              {approved > 0 && <span className="ml-2 text-green-400">{approved} approved</span>}
              {rejected > 0 && <span className="ml-2 text-red-400">{rejected} rejected</span>}
              {hasPending && <span className="ml-2 text-amber-400">{pending.length} pending</span>}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {hasPending && (
            <>
              <button
                onClick={() => handleBulk("approve")}
                disabled={processing}
                className="px-3 py-1.5 rounded-xl bg-green-700 text-white text-xs font-semibold hover:bg-green-600 disabled:opacity-50 transition-colors"
              >
                {processing ? "…" : "Approve all"}
              </button>
              <button
                onClick={() => handleBulk("reject")}
                disabled={processing}
                className="px-3 py-1.5 rounded-xl bg-red-800 text-white text-xs font-semibold hover:bg-red-700 disabled:opacity-50 transition-colors"
              >
                {processing ? "…" : "Reject all"}
              </button>
            </>
          )}
          <button
            onClick={() => setExpanded((v) => !v)}
            className="px-3 py-1.5 rounded-xl border border-slate-700 text-xs text-slate-400 hover:text-white hover:border-slate-600 transition-colors"
          >
            {expanded ? "Hide details" : "View details"}
          </button>
        </div>
      </div>

      {/* Pending breakdown summary */}
      {hasPending && !expanded && (
        <div className="border-t border-slate-800 px-5 py-3 flex flex-wrap gap-x-5 gap-y-1">
          {Object.entries(methodCounts).map(([method, count]) => (
            <span key={method} className="text-xs text-slate-400">
              <span className="font-semibold text-slate-300">{count}</span>{" "}
              {METHOD_GROUP_LABELS[method] ?? method}
            </span>
          ))}
        </div>
      )}

      {/* Error message */}
      {error && (
        <div className="mx-5 mb-3 rounded-lg border border-red-900 bg-red-950/40 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}

      {/* Expanded individual proposals */}
      {expanded && (
        <div className="border-t border-slate-800 px-5 pb-5 pt-4">
          <p className="text-xs text-slate-500 mb-3">Individual cleaning proposals</p>
          <div className="overflow-x-auto rounded-xl border border-slate-800">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-slate-800 border-b border-slate-700">
                  {["Dataset","Row","Column","Current value","Proposed value","Type","Status"].map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-semibold text-slate-400 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {all.map((p) => (
                  <tr key={p.id} className={
                    p.status === "approved" ? "bg-green-950/10"
                    : p.status === "rejected" ? "bg-red-950/10"
                    : ""
                  }>
                    <td className="px-3 py-2 font-mono text-slate-400">{p.dataset_name}</td>
                    <td className="px-3 py-2 font-mono text-slate-500">{p.row_identifier ?? `#${p.row_index}`}</td>
                    <td className="px-3 py-2 font-semibold text-slate-200">{p.column_name}</td>
                    <td className="px-3 py-2">
                      {p.original_value
                        ? <span className="text-red-300 bg-red-950/30 border border-red-900/50 px-1.5 py-0.5 rounded font-mono">{p.original_value}</span>
                        : <span className="italic text-slate-600">Missing</span>
                      }
                    </td>
                    <td className="px-3 py-2">
                      <span className="text-green-300 bg-green-950/40 border border-green-900/50 px-1.5 py-0.5 rounded font-semibold">{p.proposed_value}</span>
                    </td>
                    <td className="px-3 py-2 text-slate-500">{METHOD_GROUP_LABELS[p.source_method] ?? p.source_method}</td>
                    <td className="px-3 py-2">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium border ${
                        p.status === "approved" ? "bg-green-950 text-green-300 border-green-900"
                        : p.status === "rejected" ? "bg-red-950 text-red-300 border-red-900"
                        : "bg-slate-800 text-slate-400 border-slate-700"
                      }`}>
                        {p.status.charAt(0).toUpperCase() + p.status.slice(1)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ProposalsPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState<string | null>(null);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [exporting, setExporting] = useState(false);
  const [exportMsg, setExportMsg] = useState<{ text: string; ok: boolean } | null>(null);

  function loadProposals() {
    if (!sessionId) return;
    setLoading(true);
    getProposals(sessionId)
      .then((d) => setProposals(d.proposals))
      .catch((e) => setError(e.message ?? "Failed to load proposals."))
      .finally(() => setLoading(false));
  }

  useEffect(() => { loadProposals(); }, [sessionId]);

  async function handleExport() {
    if (!sessionId || approved === 0 || exporting) return;
    setExporting(true);
    setExportMsg(null);
    try {
      const blob = await exportSession(sessionId);
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href     = url;
      a.download = `export_${sessionId.slice(0, 8)}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setExportMsg({ text: "Export complete.", ok: true });
    } catch (err: unknown) {
      setExportMsg({ text: err instanceof Error ? err.message : "Export failed.", ok: false });
    } finally {
      setExporting(false);
    }
  }

  function handleDecision(updated: Proposal) {
    setProposals((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
  }

  const total    = proposals.length;
  const pending  = proposals.filter((p) => p.status === "pending").length;
  const approved = proposals.filter((p) => p.status === "approved").length;
  const rejected = proposals.filter((p) => p.status === "rejected").length;

  // Proposals that need individual review (excludes standard-cleaning handled by card)
  const individualProposals = proposals.filter(
    (p) => !STANDARD_CLEANING_METHODS.has(p.source_method)
  );

  return (
    <div className="min-h-screen bg-slate-950">
      <NavBar />

      <main className="mx-auto max-w-7xl px-6 py-10 space-y-6">

        <WorkflowProgress current="review" />

        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-white">Proposals</h1>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs">
              <span className="font-mono text-slate-600">{sessionId?.slice(0, 8)}</span>
              {!loading && total > 0 && (
                <>
                  <span className="text-slate-500">{total} total</span>
                  {pending  > 0 && <span className="text-amber-400">{pending} pending</span>}
                  {approved > 0 && <span className="text-green-400">{approved} approved</span>}
                  {rejected > 0 && <span className="text-red-400">{rejected} rejected</span>}
                </>
              )}
            </div>
          </div>
          <button
            onClick={handleExport}
            disabled={approved === 0 || exporting}
            className={[
              "shrink-0 inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-colors",
              approved > 0 && !exporting
                ? "bg-green-700 text-white hover:bg-green-600"
                : "bg-slate-800/50 text-slate-600 cursor-not-allowed",
            ].join(" ")}
            title={approved === 0 ? "Approve at least one proposal to export" : undefined}
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
            </svg>
            {exporting ? "Exporting…" : "Export"}
          </button>
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-20 gap-3">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-800 border-t-blue-500" />
            <p className="text-sm text-slate-500">Loading…</p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="rounded-xl border border-red-900 bg-red-950/30 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* Standard cleaning group card */}
        {!loading && !error && proposals.length > 0 && sessionId && (
          <StandardCleaningCard
            proposals={proposals}
            sessionId={sessionId}
            onRefresh={loadProposals}
          />
        )}

        {/* Individual review table (cross-dataset, interpolation, business rules) */}
        {!loading && !error && (
          individualProposals.length > 0 ? (
            <div className="rounded-2xl border border-slate-800 bg-slate-900">
              <div className="px-5 py-3 border-b border-slate-800">
                <p className="text-sm font-semibold text-white">Individual review required</p>
                <p className="text-xs text-slate-500 mt-0.5">
                  Cross-dataset fills, sequence inferences, and business rule anomalies — each requires a separate decision.
                </p>
              </div>
              <div className="p-5">
                <ProposalsTable proposals={individualProposals} onDecision={handleDecision} />
              </div>
            </div>
          ) : proposals.length > 0 ? null : (
            <div className="rounded-2xl border border-dashed border-slate-800 py-20 text-center">
              <p className="text-sm text-slate-600">No proposals for this session.</p>
            </div>
          )
        )}

        {/* Export feedback toast */}
        {exportMsg && (
          <div className={`flex items-center gap-3 rounded-xl border px-4 py-3 text-sm ${
            exportMsg.ok
              ? "border-green-900 bg-green-950/30 text-green-300"
              : "border-red-900  bg-red-950/30  text-red-300"
          }`}>
            <span className="flex-1">{exportMsg.text}</span>
            <button onClick={() => setExportMsg(null)} className="opacity-50 hover:opacity-100 transition-opacity">
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

      </main>
    </div>
  );
}
