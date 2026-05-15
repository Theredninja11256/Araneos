export type WorkflowStep =
  | "upload"
  | "analyse"
  | "review"
  | "export"
  | "insights"
  | "dashboard";

const STEPS: { key: WorkflowStep; label: string }[] = [
  { key: "upload",    label: "Upload" },
  { key: "analyse",   label: "Analyse" },
  { key: "review",    label: "Review" },
  { key: "export",    label: "Export" },
  { key: "insights",  label: "Joins" },
  { key: "dashboard", label: "Dashboard" },
];

interface Props { current: WorkflowStep }

export default function WorkflowProgress({ current }: Props) {
  const currentIdx = STEPS.findIndex((s) => s.key === current);

  return (
    <nav aria-label="Workflow" className="flex items-center gap-0.5 overflow-x-auto">
      {STEPS.map((step, idx) => {
        const isDone   = idx < currentIdx;
        const isActive = idx === currentIdx;

        return (
          <span key={step.key} className="flex shrink-0 items-center">
            {idx > 0 && (
              <span className={`h-px w-6 ${idx <= currentIdx ? "bg-blue-800" : "bg-slate-800"}`} />
            )}
            <span
              className={[
                "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium",
                isActive ? "bg-blue-600 text-white"
                : isDone  ? "text-green-400"
                :           "text-slate-600",
              ].join(" ")}
            >
              {isDone ? (
                <svg className="h-3 w-3 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
              ) : (
                <span className={`h-1.5 w-1.5 rounded-full ${isActive ? "bg-white" : "bg-slate-700"}`} />
              )}
              {step.label}
            </span>
          </span>
        );
      })}
    </nav>
  );
}
