import { Grade } from "../api/client";

interface Props {
  score: number;
  grade: Grade;
  size?: "sm" | "md" | "lg";
}

const gradeRing: Record<Grade, string> = {
  Green: "ring-green-800",
  Amber: "ring-amber-700",
  Red:   "ring-red-800",
};

const gradeBg: Record<Grade, string> = {
  Green: "bg-green-600",
  Amber: "bg-amber-500",
  Red:   "bg-red-600",
};

const gradeLabel: Record<Grade, string> = {
  Green: "Good",
  Amber: "Fair",
  Red:   "Poor",
};

const sizeStyles = {
  sm: { circle: "w-14 h-14", score: "text-xl font-bold",   label: "text-[10px]" },
  md: { circle: "w-20 h-20", score: "text-3xl font-bold",  label: "text-xs" },
  lg: { circle: "w-28 h-28", score: "text-4xl font-bold",  label: "text-sm" },
};

export default function ScoreBadge({ score, grade, size = "md" }: Props) {
  const s = sizeStyles[size];
  return (
    <div
      className={[
        "flex shrink-0 flex-col items-center justify-center rounded-full ring-2 text-white",
        s.circle,
        gradeBg[grade],
        gradeRing[grade],
      ].join(" ")}
    >
      <span className={s.score}>{Math.round(score)}</span>
      <span className={`${s.label} font-medium opacity-80`}>{gradeLabel[grade]}</span>
    </div>
  );
}
