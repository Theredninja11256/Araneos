/**
 * ProposalsTable — interactive review table with diff view and row context.
 *
 * Each row shows a clear current → proposed diff.
 * Expanding a row reveals: reason, source evidence, and surrounding CSV rows.
 */

import { useState } from "react";
import {
  approveProposal,
  rejectProposal,
  getProposalContext,
} from "../api/client";
import type { Proposal, ProposalContext, ContextRow } from "../api/client";

interface Props {
  proposals: Proposal[];
  onDecision: (updated: Proposal) => void;
}

type StatusFilter = "all" | "pending" | "approved" | "rejected";

// ── Labels & styles ──────────────────────────────────────────────────────────

const TYPE_STYLES: Record<string, string> = {
  cross_dataset_fill: "bg-blue-950   text-blue-300   border-blue-900",
  interpolation:      "bg-purple-950 text-purple-300 border-purple-900",
  data_correction:    "bg-teal-950   text-teal-300   border-teal-900",
};

const TYPE_LABELS: Record<string, string> = {
  cross_dataset_fill: "Cross-dataset",
  interpolation:      "Inferred value",
  data_correction:    "Correction",
};

const METHOD_LABELS: Record<string, string> = {
  cross_dataset_lookup:        "Cross-dataset lookup",
  linear_interpolation:        "Row-order sequence",
  date_inference:              "Date pattern inference",
  sequential_id_inference:     "Sequential ID inference",
  format_correction:           "Format fix",
  date_format_standardisation: "Date normalisation",
  value_cleaning:              "Value cleaning",
  business_rule:               "Business rule alert",
};

const ESTIMATED_METHODS = new Set([
  "linear_interpolation",
  "date_inference",
  "sequential_id_inference",
]);

// ── Micro-components ─────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const s: Record<string, string> = {
    pending:  "bg-slate-800  text-slate-300  border-slate-700",
    approved: "bg-green-950  text-green-300  border-green-900",
    rejected: "bg-red-950    text-red-300    border-red-900",
  };
  const l: Record<string, string> = { pending: "Pending", approved: "Approved", rejected: "Rejected" };
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium border ${s[status] ?? s.pending}`}>
      {l[status] ?? status}
    </span>
  );
}

function TypeBadge({ type }: { type: string }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium border ${TYPE_STYLES[type] ?? TYPE_STYLES.data_correction}`}>
      {TYPE_LABELS[type] ?? type}
    </span>
  );
}

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const pct   = Math.round(confidence * 100);
  const label = confidence >= 0.8 ? "High" : confidence >= 0.6 ? "Medium" : "Low";
  const cls   = confidence >= 0.8 ? "text-green-400" : confidence >= 0.6 ? "text-amber-400" : "text-red-400";
  return <span className={`text-xs font-semibold tabular-nums ${cls}`}>{label} ({pct}%)</span>;
}

function DisplayValue({ value, variant }: { value: string | null; variant: "original" | "proposed" }) {
  if (value === null || value === "" || value === "null") {
    return <span className="italic text-slate-600 text-xs">Missing</span>;
  }
  const cls = variant === "original"
    ? "text-red-300 bg-red-950/30 border border-red-900/60 px-2 py-0.5 rounded text-xs font-mono"
    : "text-green-300 bg-green-950/40 border border-green-900/60 px-2 py-0.5 rounded text-xs font-semibold";
  return <span className={cls}>{value}</span>;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

// ── Row context table ─────────────────────────────────────────────────────────

function ContextTable({
  label,
  context,
}: {
  label: string;
  context: { dataset: string; columns: string[]; rows: ContextRow[]; highlighted_column: string | null };
}) {
  // Show at most 8 columns to avoid overflow; always include highlighted column
  const highlight = context.highlighted_column;
  let cols = context.columns;
  if (cols.length > 8) {
    const others = cols.filter((c) => c !== highlight).slice(0, 7);
    cols = highlight ? [highlight, ...others] : others;
  }

  return (
    <div className="mt-3">
      <p className="text-xs font-semibold text-slate-400 mb-2">{label}</p>
      <div className="overflow-x-auto rounded-lg border border-slate-700">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-slate-800 border-b border-slate-700">
              {cols.map((col) => (
                <th
                  key={col}
                  className={`px-2 py-1.5 text-left font-semibold whitespace-nowrap ${
                    col === highlight ? "text-blue-300" : "text-slate-400"
                  }`}
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {context.rows.map((row, i) => {
              const isTarget = row._position === "target";
              return (
                <tr
                  key={i}
                  className={isTarget ? "bg-blue-950/30" : "bg-slate-900"}
                >
                  {cols.map((col) => {
                    const val = row[col];
                    const isHighlighted = col === highlight && isTarget;
                    return (
                      <td
                        key={col}
                        className={`px-2 py-1.5 whitespace-nowrap ${
                          isHighlighted
                            ? "font-semibold text-amber-300"
                            : val === null || val === ""
                            ? "italic text-slate-600"
                            : "text-slate-300"
                        }`}
                      >
                        {val === null || val === "" ? "—" : String(val)}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Action buttons ────────────────────────────────────────────────────────────

function ActionCell({ proposal, processingId, onApprove, onReject }: {
  proposal: Proposal;
  processingId: string | null;
  onApprove: (id: string) => void;
  onReject:  (id: string) => void;
}) {
  if (proposal.status !== "pending") return null;
  const isLoading = processingId === proposal.id;
  const isBlocked = processingId !== null && !isLoading;
  const disabledCls = "bg-slate-800 text-slate-600 cursor-not-allowed";

  return (
    <div className="flex gap-1.5 justify-end">
      <button
        onClick={(e) => { e.stopPropagation(); onApprove(proposal.id); }}
        disabled={isLoading || isBlocked}
        className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors ${isLoading || isBlocked ? disabledCls : "bg-green-700 text-white hover:bg-green-600"}`}
      >
        {isLoading ? "…" : "Approve"}
      </button>
      <button
        onClick={(e) => { e.stopPropagation(); onReject(proposal.id); }}
        disabled={isLoading || isBlocked}
        className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors ${isLoading || isBlocked ? disabledCls : "bg-red-800 text-white hover:bg-red-700"}`}
      >
        {isLoading ? "…" : "Reject"}
      </button>
    </div>
  );
}

// ── Filter bar ────────────────────────────────────────────────────────────────

function FilterBar({
  proposals, datasetFilter, typeFilter, statusFilter,
  onDataset, onType, onStatus,
}: {
  proposals: Proposal[];
  datasetFilter: string;
  typeFilter: string;
  statusFilter: StatusFilter;
  onDataset: (v: string) => void;
  onType: (v: string) => void;
  onStatus: (v: StatusFilter) => void;
}) {
  const datasets = Array.from(new Set(proposals.map((p) => p.dataset_name))).sort();
  const types    = Array.from(new Set(proposals.map((p) => p.proposal_type)));
  const counts = {
    all:      proposals.length,
    pending:  proposals.filter((p) => p.status === "pending").length,
    approved: proposals.filter((p) => p.status === "approved").length,
    rejected: proposals.filter((p) => p.status === "rejected").length,
  };

  const statusOpts: { value: StatusFilter; label: string }[] = [
    { value: "all",      label: `All (${counts.all})`           },
    { value: "pending",  label: `Pending (${counts.pending})`   },
    { value: "approved", label: `Approved (${counts.approved})` },
    { value: "rejected", label: `Rejected (${counts.rejected})` },
  ];

  const selectCls = "text-sm bg-slate-800 border border-slate-700 text-slate-300 rounded-lg px-2 py-1 focus:outline-none focus:border-blue-600";

  return (
    <div className="flex flex-wrap gap-3 mb-4">
      <div>
        <p className="text-xs text-slate-500 mb-1">Status</p>
        <div className="flex gap-1">
          {statusOpts.map((opt) => (
            <button
              key={opt.value}
              onClick={() => onStatus(opt.value)}
              className={[
                "px-3 py-1 rounded-full text-xs font-medium border transition-colors",
                statusFilter === opt.value
                  ? "bg-slate-200 text-slate-900 border-slate-200"
                  : "bg-transparent text-slate-400 border-slate-700 hover:border-slate-500",
              ].join(" ")}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>
      <div>
        <p className="text-xs text-slate-500 mb-1">Dataset</p>
        <select className={selectCls} value={datasetFilter} onChange={(e) => onDataset(e.target.value)}>
          <option value="">All datasets</option>
          {datasets.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
      </div>
      <div>
        <p className="text-xs text-slate-500 mb-1">Type</p>
        <select className={selectCls} value={typeFilter} onChange={(e) => onType(e.target.value)}>
          <option value="">All types</option>
          {types.map((t) => <option key={t} value={t}>{TYPE_LABELS[t] ?? t}</option>)}
        </select>
      </div>
    </div>
  );
}

// ── Expanded detail row ───────────────────────────────────────────────────────

function DetailRow({
  proposal,
  onLoadContext,
  contextCache,
  contextLoading,
}: {
  proposal: Proposal;
  onLoadContext: (id: string) => void;
  contextCache: Record<string, ProposalContext>;
  contextLoading: string | null;
}) {
  const ctx        = contextCache[proposal.id];
  const isLoading  = contextLoading === proposal.id;

  return (
    <tr className="bg-slate-900/80">
      <td colSpan={9} className="px-5 py-4">

        {/* ── Summary grid ── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-1.5 text-xs text-slate-400 mb-3">
          <div className="space-y-1.5">
            <p><span className="font-semibold text-slate-300">Source method: </span>{METHOD_LABELS[proposal.source_method] ?? proposal.source_method}</p>
            {proposal.source_dataset && (
              <p>
                <span className="font-semibold text-slate-300">Source evidence: </span>
                <span className="font-mono text-blue-300">{proposal.source_dataset}</span>
                {" — matched on "}
                <span className="font-mono text-slate-300">{proposal.join_key} = {proposal.join_value}</span>
                {" — source column: "}
                <span className="font-mono text-slate-300">{proposal.source_column}</span>
              </p>
            )}
            <p><span className="font-semibold text-slate-300">Proposal ID: </span><span className="font-mono text-slate-500 break-all">{proposal.id}</span></p>
            <p><span className="font-semibold text-slate-300">Created: </span>{formatDate(proposal.created_at)}</p>
            {proposal.reviewed_at && (
              <p>
                <span className="font-semibold text-slate-300">Reviewed: </span>
                <span className={proposal.status === "approved" ? "text-green-400" : "text-red-400"}>
                  {formatDate(proposal.reviewed_at)} — {proposal.user_decision}
                </span>
              </p>
            )}
          </div>
          <div>
            {ESTIMATED_METHODS.has(proposal.source_method) ? (
              <div className="flex items-start gap-2 rounded-lg border border-amber-900 bg-amber-950/30 px-3 py-2.5">
                <div className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-amber-400" />
                <div>
                  <p className="text-xs font-semibold text-amber-300 mb-0.5">Estimated value — review carefully</p>
                  <p className="text-xs text-amber-400/80 leading-relaxed">{proposal.explanation}</p>
                </div>
              </div>
            ) : proposal.source_method === "business_rule" ? (
              <div className="flex items-start gap-2 rounded-lg border border-orange-900 bg-orange-950/30 px-3 py-2.5">
                <div className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-orange-400" />
                <div>
                  <p className="text-xs font-semibold text-orange-300 mb-0.5">Business rule alert</p>
                  <p className="text-xs text-orange-400/80 leading-relaxed">{proposal.explanation}</p>
                </div>
              </div>
            ) : (
              <p className="text-xs text-slate-400 leading-relaxed">
                <span className="font-semibold text-slate-300">Reason: </span>
                {proposal.explanation}
              </p>
            )}
          </div>
        </div>

        {/* ── Row context section ── */}
        <div className="border-t border-slate-800 pt-3">
          {!ctx && (
            <button
              onClick={() => onLoadContext(proposal.id)}
              disabled={isLoading}
              className="text-xs text-blue-400 hover:text-blue-300 disabled:text-slate-600 transition-colors"
            >
              {isLoading ? "Loading row context…" : "Show row context"}
            </button>
          )}

          {ctx && (
            <div className="space-y-1">
              <ContextTable
                label={`Target row — ${ctx.target.dataset} · column: ${ctx.target.column}`}
                context={ctx.target}
              />
              {ctx.source && (
                <ContextTable
                  label={`Matched source row — ${ctx.source.dataset} · matched on ${ctx.source.matched_key} = ${ctx.source.matched_value}`}
                  context={ctx.source}
                />
              )}
            </div>
          )}
        </div>

      </td>
    </tr>
  );
}

// ── Main table ────────────────────────────────────────────────────────────────

export default function ProposalsTable({ proposals, onDecision }: Props) {
  const [datasetFilter, setDatasetFilter] = useState("");
  const [typeFilter,    setTypeFilter]    = useState("");
  const [statusFilter,  setStatusFilter]  = useState<StatusFilter>("all");
  const [expandedId,    setExpandedId]    = useState<string | null>(null);
  const [processingId,  setProcessingId]  = useState<string | null>(null);
  const [actionError,   setActionError]   = useState<string | null>(null);
  const [contextCache,  setContextCache]  = useState<Record<string, ProposalContext>>({});
  const [contextLoading, setContextLoading] = useState<string | null>(null);

  const filtered = proposals.filter((p) => {
    if (datasetFilter && p.dataset_name !== datasetFilter) return false;
    if (typeFilter    && p.proposal_type !== typeFilter)   return false;
    if (statusFilter !== "all" && p.status !== statusFilter) return false;
    return true;
  });

  async function handleApprove(id: string) {
    setProcessingId(id); setActionError(null);
    try { onDecision(await approveProposal(id)); }
    catch (err: unknown) { setActionError(err instanceof Error ? err.message : "Approve failed."); }
    finally { setProcessingId(null); }
  }

  async function handleReject(id: string) {
    setProcessingId(id); setActionError(null);
    try { onDecision(await rejectProposal(id)); }
    catch (err: unknown) { setActionError(err instanceof Error ? err.message : "Reject failed."); }
    finally { setProcessingId(null); }
  }

  async function handleLoadContext(proposalId: string) {
    if (contextCache[proposalId]) return;
    setContextLoading(proposalId);
    try {
      const ctx = await getProposalContext(proposalId);
      setContextCache((prev) => ({ ...prev, [proposalId]: ctx }));
    } catch {
      // Silently fail — user can retry
    } finally {
      setContextLoading(null);
    }
  }

  function toggleRow(id: string) {
    setExpandedId((prev) => (prev === id ? null : id));
  }

  if (proposals.length === 0) {
    return <p className="text-center py-12 text-slate-500 text-sm">No proposals for this session.</p>;
  }

  return (
    <div>
      <FilterBar
        proposals={proposals}
        datasetFilter={datasetFilter}
        typeFilter={typeFilter}
        statusFilter={statusFilter}
        onDataset={setDatasetFilter}
        onType={setTypeFilter}
        onStatus={setStatusFilter}
      />

      {actionError && (
        <div className="mb-3 rounded-lg border border-red-900 bg-red-950/40 px-4 py-2 text-sm text-red-300">
          {actionError}
        </div>
      )}

      <p className="text-xs text-slate-600 mb-2">
        {filtered.length} of {proposals.length} proposals — click a row to expand
      </p>

      <div className="overflow-x-auto rounded-xl border border-slate-700">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700 bg-slate-800">
              {[
                "Dataset", "Row", "Column",
                "Current value", "Proposed value",
                "Status", "Type", "Confidence", ""
              ].map((h, i) => (
                <th
                  key={i}
                  className={`px-3 py-2.5 text-xs font-semibold uppercase tracking-wide text-slate-400 whitespace-nowrap ${i === 8 ? "text-right" : "text-left"}`}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {filtered.map((p) => {
              const isExpanded = expandedId === p.id;
              const rowBg =
                p.status === "approved" ? "bg-green-950/20 hover:bg-green-950/30"
                : p.status === "rejected" ? "bg-red-950/20 hover:bg-red-950/30"
                : "hover:bg-slate-800/40";

              return (
                <>
                  <tr
                    key={p.id}
                    className={`cursor-pointer transition-colors ${rowBg}`}
                    onClick={() => toggleRow(p.id)}
                  >
                    {/* Dataset */}
                    <td className="px-3 py-2.5">
                      <span className="font-mono text-xs bg-slate-800 px-1.5 py-0.5 rounded text-slate-300">
                        {p.dataset_name}
                      </span>
                    </td>

                    {/* Row identifier */}
                    <td className="px-3 py-2.5 font-mono text-xs text-slate-400 whitespace-nowrap">
                      {p.row_identifier ?? `#${p.row_index ?? "?"}`}
                    </td>

                    {/* Column name */}
                    <td className="px-3 py-2.5 font-semibold text-slate-200 whitespace-nowrap">
                      {p.column_name}
                    </td>

                    {/* Current value — red/amber when bad */}
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <DisplayValue value={p.original_value} variant="original" />
                    </td>

                    {/* Proposed value — green */}
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <DisplayValue value={p.proposed_value} variant="proposed" />
                    </td>

                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <StatusBadge status={p.status} />
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <TypeBadge type={p.proposal_type} />
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <ConfidenceBadge confidence={p.confidence} />
                    </td>
                    <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                      <ActionCell
                        proposal={p}
                        processingId={processingId}
                        onApprove={handleApprove}
                        onReject={handleReject}
                      />
                    </td>
                  </tr>

                  {isExpanded && (
                    <DetailRow
                      key={`${p.id}-detail`}
                      proposal={p}
                      onLoadContext={handleLoadContext}
                      contextCache={contextCache}
                      contextLoading={contextLoading}
                    />
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
