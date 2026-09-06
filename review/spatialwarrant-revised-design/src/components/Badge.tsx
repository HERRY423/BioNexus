const CEILING_STYLES: Record<string, string> = {
  TO_BE_COMPUTED: "bg-slate-500/20 text-slate-300 ring-slate-500/40",
  ROBUST: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/40",
  SUPPORTED: "bg-sky-500/15 text-sky-300 ring-sky-500/40",
  FRAGILE: "bg-amber-500/15 text-amber-300 ring-amber-500/40",
  ABSTAIN: "bg-slate-500/20 text-slate-300 ring-slate-500/40",
  REFUSED: "bg-rose-500/15 text-rose-300 ring-rose-500/40",
};

const VERDICT_STYLES: Record<string, string> = {
  PENDING: "bg-slate-700/40 text-slate-300 ring-slate-600",
  WARRANTED: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/40",
  WARRANTED_WITH_LIMITS: "bg-amber-500/15 text-amber-300 ring-amber-500/40",
  NOT_SUFFICIENT: "bg-orange-500/15 text-orange-300 ring-orange-500/40",
  REFUSED: "bg-rose-500/15 text-rose-300 ring-rose-500/40",
};

const CLASS_STYLES: Record<string, string> = {
  descriptive: "bg-teal-500/10 text-teal-300 ring-teal-500/30",
  association: "bg-cyan-500/10 text-cyan-300 ring-cyan-500/30",
  population_effect: "bg-indigo-500/10 text-indigo-300 ring-indigo-500/30",
  mechanistic: "bg-fuchsia-500/10 text-fuchsia-300 ring-fuchsia-500/30",
  causal: "bg-pink-500/10 text-pink-300 ring-pink-500/30",
  clinical: "bg-rose-500/10 text-rose-300 ring-rose-500/30",
};

export function CeilingBadge({ value }: { value: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 font-mono text-[11px] font-semibold ring-1 ${
        CEILING_STYLES[value] ?? CEILING_STYLES.ABSTAIN
      }`}
    >
      {value}
    </span>
  );
}

export function VerdictBadge({ value }: { value: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 font-mono text-[11px] font-semibold ring-1 ${
        VERDICT_STYLES[value] ?? VERDICT_STYLES.PENDING
      }`}
    >
      {value}
    </span>
  );
}

export function ClassBadge({ value }: { value: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] ring-1 ${
        CLASS_STYLES[value] ?? CLASS_STYLES.descriptive
      }`}
    >
      {value}
    </span>
  );
}

export function Chip({ children, tone = "slate" }: { children: React.ReactNode; tone?: string }) {
  const tones: Record<string, string> = {
    slate: "bg-slate-800 text-slate-300",
    sky: "bg-sky-500/15 text-sky-200",
    violet: "bg-violet-500/15 text-violet-200",
    emerald: "bg-emerald-500/15 text-emerald-200",
    amber: "bg-amber-500/15 text-amber-200",
  };
  return (
    <span className={`inline-block rounded-md px-2 py-0.5 text-xs ${tones[tone] ?? tones.slate}`}>
      {children}
    </span>
  );
}
