import { useState } from "react";
import { ColumnProfile, ColumnType } from "../api/client";

interface Props { columns: ColumnProfile[] }

const typeConfig: Record<ColumnType, { label: string; style: string }> = {
  numeric:     { label: "Numeric",     style: "bg-blue-950   text-blue-300"   },
  date:        { label: "Date",        style: "bg-purple-950 text-purple-300" },
  identifier:  { label: "ID",          style: "bg-slate-800  text-slate-300"  },
  categorical: { label: "Category",   style: "bg-teal-950   text-teal-300"   },
  text:        { label: "Text",        style: "bg-slate-800  text-slate-400"  },
};

function TypeBadge({ type }: { type: ColumnType }) {
  const { label, style } = typeConfig[type] ?? typeConfig.text;
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold ${style}`}>
      {label}
    </span>
  );
}

function NullCell({ pct, count }: { pct: number; count: number }) {
  const pctDisplay = (pct * 100).toFixed(1) + "%";
  const cls =
    pct > 0.2  ? "font-semibold text-red-400"   :
    pct > 0.05 ? "font-medium text-amber-400"   :
    pct > 0    ? "text-amber-500"                :
                 "text-green-500";
  return (
    <span className={cls}>
      {pctDisplay}
      {count > 0 && <span className="ml-1 text-slate-500 font-normal">({count})</span>}
    </span>
  );
}

function ColumnDetail({ col }: { col: ColumnProfile }) {
  return (
    <div className="grid grid-cols-1 gap-4 px-4 py-4 sm:grid-cols-2 bg-slate-900/50">
      {col.inferred_type === "numeric" && col.mean !== null && (
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Statistics
          </p>
          <dl className="space-y-0.5 text-xs text-slate-400">
            {[["Min", col.min], ["Max", col.max], ["Mean", col.mean], ["Median", col.median], ["Std dev", col.std]].map(
              ([label, val]) => (
                <div key={label as string} className="flex justify-between gap-4">
                  <dt className="text-slate-500">{label}</dt>
                  <dd className="font-mono font-medium text-slate-300">
                    {val !== null && val !== undefined ? Number(val).toLocaleString() : "—"}
                  </dd>
                </div>
              )
            )}
            {col.outlier_count !== null && (
              <div className="flex justify-between gap-4">
                <dt className="text-slate-500">Outliers</dt>
                <dd className="font-mono font-medium text-slate-300">
                  {col.outlier_count}
                  {col.outlier_pct !== null && (
                    <span className="text-slate-500"> ({(col.outlier_pct * 100).toFixed(1)}%)</span>
                  )}
                </dd>
              </div>
            )}
          </dl>
        </div>
      )}

      {col.inferred_type === "date" && col.date_formats_detected && (
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Date formats
          </p>
          {col.date_formats_detected.length === 0 ? (
            <p className="text-xs text-slate-500">None detected</p>
          ) : (
            <ul className="space-y-0.5">
              {col.date_formats_detected.map((f) => (
                <li key={f} className="text-xs text-slate-400">{f}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {col.top_values.length > 0 && (
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Top values
          </p>
          <ul className="space-y-0.5">
            {col.top_values.map((tv) => (
              <li key={tv.value} className="flex justify-between text-xs">
                <span className="font-mono text-slate-300 truncate max-w-[70%]">{tv.value}</span>
                <span className="text-slate-500">{tv.count}×</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {col.issues.length > 0 && (
        <div className="sm:col-span-2">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Issues
          </p>
          <ul className="space-y-1">
            {col.issues.map((issue, i) => (
              <li key={i} className="text-xs text-amber-400">{issue}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function ColumnStatsTable({ columns }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggle(name: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-700">
      <table className="w-full text-sm">
        <thead className="border-b border-slate-700 bg-slate-800 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
          <tr>
            <th className="px-4 py-2.5">Column</th>
            <th className="px-4 py-2.5">Type</th>
            <th className="px-4 py-2.5 text-right">Null %</th>
            <th className="px-4 py-2.5 text-right">Unique %</th>
            <th className="px-4 py-2.5 text-center">Issues</th>
            <th className="px-4 py-2.5 w-6"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {columns.map((col) => {
            const isOpen     = expanded.has(col.name);
            const issueCount = col.issues.length;
            return (
              <>
                <tr
                  key={col.name}
                  className="cursor-pointer transition-colors hover:bg-slate-800/50"
                  onClick={() => toggle(col.name)}
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {col.is_critical_field && (
                        <span className="h-1.5 w-1.5 rounded-full bg-amber-400 shrink-0" title="Critical field" />
                      )}
                      <span className="font-mono font-medium text-slate-200">{col.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3"><TypeBadge type={col.inferred_type} /></td>
                  <td className="px-4 py-3 text-right"><NullCell pct={col.null_pct} count={col.null_count} /></td>
                  <td className="px-4 py-3 text-right text-xs text-slate-400">
                    {(col.uniqueness_ratio * 100).toFixed(0)}%
                    <span className="ml-1 text-slate-600">({col.unique_count})</span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    {issueCount > 0 ? (
                      <span className="inline-flex items-center justify-center rounded-full bg-amber-900/60 px-2 py-0.5 text-xs font-semibold text-amber-300">
                        {issueCount}
                      </span>
                    ) : (
                      <span className="text-xs text-green-500 font-medium">ok</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <svg className={`h-3.5 w-3.5 text-slate-500 transition-transform ${isOpen ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
                    </svg>
                  </td>
                </tr>
                {isOpen && (
                  <tr key={`${col.name}-detail`}>
                    <td colSpan={6} className="border-t border-slate-800">
                      <ColumnDetail col={col} />
                    </td>
                  </tr>
                )}
              </>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
