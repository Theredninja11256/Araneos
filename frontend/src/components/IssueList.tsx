import { ScorePenalty } from "../api/client";

interface Props { penalties: ScorePenalty[] }

const severityOrder: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };

const severityConfig: Record<string, { dot: string; bg: string; border: string; badge: string; text: string }> = {
  critical: { dot: "bg-red-500",    bg: "bg-red-950/40",   border: "border-red-900",   badge: "bg-red-900 text-red-300",    text: "text-red-300"    },
  high:     { dot: "bg-orange-500", bg: "bg-orange-950/40",border: "border-orange-900",badge: "bg-orange-900 text-orange-300",text: "text-orange-300" },
  medium:   { dot: "bg-amber-400",  bg: "bg-amber-950/40", border: "border-amber-900", badge: "bg-amber-900 text-amber-300", text: "text-amber-300"  },
  low:      { dot: "bg-slate-500",  bg: "bg-slate-800/40", border: "border-slate-700", badge: "bg-slate-800 text-slate-300", text: "text-slate-300"  },
};

export default function IssueList({ penalties }: Props) {
  if (penalties.length === 0) {
    return (
      <p className="text-sm text-slate-500 italic">No issues detected.</p>
    );
  }

  const sorted = [...penalties].sort(
    (a, b) => (severityOrder[a.severity] ?? 9) - (severityOrder[b.severity] ?? 9)
  );

  return (
    <ul className="space-y-2">
      {sorted.map((p, i) => {
        const cfg = severityConfig[p.severity] ?? severityConfig.low;
        return (
          <li
            key={i}
            className={`flex items-start gap-3 rounded-lg border px-4 py-3 ${cfg.bg} ${cfg.border}`}
          >
            <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${cfg.dot}`} />
            <div className="min-w-0 flex-1">
              <p className={`text-sm leading-snug ${cfg.text}`}>{p.reason}</p>
              <div className="mt-1.5 flex flex-wrap items-center gap-2">
                <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${cfg.badge}`}>
                  {p.severity}
                </span>
                {p.column && (
                  <span className="font-mono text-[11px] text-slate-500">{p.column}</span>
                )}
                <span className="ml-auto text-xs font-semibold text-slate-600">
                  &minus;{p.points_deducted}
                </span>
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
