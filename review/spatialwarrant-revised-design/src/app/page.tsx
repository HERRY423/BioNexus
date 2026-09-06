import Link from "next/link";
import { CeilingBadge, Chip } from "@/components/Badge";
import { ResetButton } from "@/components/ResetButton";
import { PROJECT } from "@/db/seed-data";
import { getClaims, getPlugins, getProgress } from "@/lib/queries";

export const dynamic = "force-dynamic";

const ACCENT: Record<string, string> = {
  sky: "from-sky-500/20 to-sky-500/0 border-sky-500/30",
  violet: "from-violet-500/20 to-violet-500/0 border-violet-500/30",
  emerald: "from-emerald-500/20 to-emerald-500/0 border-emerald-500/30",
};

export default async function Home() {
  const [progress, plugins, claims] = await Promise.all([getProgress(), getPlugins(), getClaims()]);
  const ceilingCounts = claims.reduce<Record<string, number>>((acc, c) => {
    acc[c.expectedCeiling] = (acc[c.expectedCeiling] ?? 0) + 1;
    return acc;
  }, {});
  const totalGb = PROJECT.memoryBudget.reduce((n, m) => n + m.gb, 0);

  return (
    <div className="space-y-10">
      {/* Hero */}
      <section className="relative overflow-hidden rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-950 to-slate-950 p-8">
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-emerald-500/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 left-1/3 h-72 w-72 rounded-full bg-sky-500/10 blur-3xl" />
        <div className="relative">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Chip tone="emerald">Rosalind Workbench Showcase</Chip>
            <Chip tone="sky">Spatial × Single-cell</Chip>
            <Chip tone="amber">32 GB laptop · CPU only · no wet lab</Chip>
          </div>
          <h1 className="text-3xl font-black tracking-tight md:text-4xl">
            {PROJECT.name}
            <span className="block bg-gradient-to-r from-emerald-300 to-sky-300 bg-clip-text text-xl font-semibold text-transparent md:text-2xl">
              {PROJECT.tagline}
            </span>
          </h1>
          <p className="mt-2 text-sm text-slate-400">{PROJECT.taglineZh}</p>
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">科学问题</p>
              <p className="mt-1 text-sm leading-relaxed text-slate-200">{PROJECT.question}</p>
            </div>
            <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-emerald-400">获奖角度</p>
              <p className="mt-1 text-sm leading-relaxed text-slate-200">{PROJECT.pitch}</p>
            </div>
          </div>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              href="/pipeline"
              className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400"
            >
              打开流水线 →
            </Link>
            <Link
              href="/submission"
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:border-slate-500"
            >
              查看提交包
            </Link>
            <ResetButton />
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="grid gap-4 md:grid-cols-4">
        <Stat label="任务完成度" value={`${progress.pct}%`} sub={`${progress.done}/${progress.total} 项`}>
          <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-800">
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-sky-400 transition-all"
              style={{ width: `${progress.pct}%` }}
            />
          </div>
        </Stat>
        <Stat label="阶段数 / 设计工时" value={`${progress.stages.length} / ${progress.hours}h`} sub="运行后填写实测工时" />
        <Stat label="声明账本" value={`${claims.length} 条`} sub="全部从 PENDING 开始">
          <div className="mt-3 flex flex-wrap gap-1">
            {Object.entries(ceilingCounts).map(([k, v]) => (
              <span key={k} className="flex items-center gap-1 text-[11px] text-slate-400">
                <CeilingBadge value={k} /> ×{v}
              </span>
            ))}
          </div>
        </Stat>
        <Stat label="内存设计预算" value={`≈ ${totalGb.toFixed(0)} GB`} sub="不是实测峰值；上限 32 GB">
          <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-800">
            <div className="h-full rounded-full bg-amber-400" style={{ width: `${(totalGb / 32) * 100}%` }} />
          </div>
        </Stat>
      </section>

      {/* Plugins */}
      <section>
        <SectionTitle
          title="真实工具分工"
          sub="插件贡献与本地 Python 执行分开记录；只有真实调用过的插件才进入提交文案。"
        />
        <div className="grid gap-4 md:grid-cols-3">
          {plugins.map((p) => (
            <div
              key={p.id}
              className={`rounded-xl border bg-gradient-to-b p-5 ${ACCENT[p.accent] ?? ACCENT.emerald}`}
            >
              <p className="text-xs text-slate-400">{p.vendor}</p>
              <h3 className="mt-1 font-semibold leading-snug text-slate-100">{p.plugin}</h3>
              <p className="mt-2 text-sm text-slate-300">{p.role}</p>
              <ul className="mt-3 space-y-1.5 text-xs text-slate-400">
                {p.howUsed.map((h) => (
                  <li key={h} className="flex gap-2">
                    <span className="text-slate-600">▸</span>
                    <span>{h}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-3 rounded-md bg-slate-950/60 p-2 text-[11px] text-slate-400">
                <span className="font-semibold text-slate-300">证明截图：</span>
                {p.proofArtifact}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Why it wins */}
      <section>
        <SectionTitle title="为什么这个项目更有竞争力" sub="获奖无法保证；以下设计让作品更可信、更易理解" />
        <div className="grid gap-3 md:grid-cols-2">
          {PROJECT.whyItWins.map((w, i) => (
            <div key={w.title} className="flex gap-3 rounded-xl border border-slate-800 bg-slate-900/50 p-4">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-slate-800 font-mono text-xs text-emerald-300">
                {i + 1}
              </span>
              <div>
                <h4 className="font-medium text-slate-100">{w.title}</h4>
                <p className="mt-1 text-sm leading-relaxed text-slate-400">{w.body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Memory */}
      <section>
        <SectionTitle title="32 GB 笔记本资源预算" sub={PROJECT.hardware} />
        <div className="overflow-hidden rounded-xl border border-slate-800">
          <table className="w-full text-sm">
            <tbody>
              {PROJECT.memoryBudget.map((m) => (
                <tr key={m.item} className="border-b border-slate-800/70 last:border-0">
                  <td className="px-4 py-2 text-slate-300">{m.item}</td>
                  <td className="w-40 px-4 py-2">
                    <div className="h-1.5 w-full rounded bg-slate-800">
                      <div className="h-full rounded bg-sky-400" style={{ width: `${(m.gb / 4) * 100}%` }} />
                    </div>
                  </td>
                  <td className="w-20 px-4 py-2 text-right font-mono text-xs text-slate-400">{m.gb.toFixed(1)} GB</td>
                </tr>
              ))}
              <tr className="bg-slate-900/60">
                <td className="px-4 py-2 font-semibold text-slate-200">设计预算合计</td>
                <td />
                <td className="px-4 py-2 text-right font-mono text-xs font-semibold text-amber-300">
                  {totalGb.toFixed(1)} GB
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  children,
}: {
  label: string;
  value: string;
  sub?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
      <p className="text-xs uppercase tracking-wider text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-slate-100">{value}</p>
      {sub && <p className="text-xs text-slate-500">{sub}</p>}
      {children}
    </div>
  );
}

function SectionTitle({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="mb-4">
      <h2 className="text-xl font-bold tracking-tight">{title}</h2>
      {sub && <p className="mt-1 text-sm text-slate-400">{sub}</p>}
    </div>
  );
}
