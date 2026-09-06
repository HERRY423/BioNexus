import { Chip } from "@/components/Badge";
import { TaskItem } from "@/components/TaskItem";
import { getProgress } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function PipelinePage() {
  const progress = await getProgress();

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">流水线 · S0 → S7</h1>
          <p className="mt-1 text-sm text-slate-400">
            每个阶段标注主用插件、工具、内存注意事项、交付物与「必拍截图」。勾选任务会实时保存到数据库。
          </p>
        </div>
        <div className="text-right">
          <p className="text-3xl font-black text-emerald-300">{progress.pct}%</p>
          <p className="text-xs text-slate-500">
            {progress.done}/{progress.total} 项 · 预计 {progress.hours} 小时
          </p>
        </div>
      </header>

      {/* Stage rail */}
      <ol className="grid grid-cols-4 gap-2 md:grid-cols-8">
        {progress.stages.map((s) => {
          const done = s.tasks.filter((t) => t.done).length;
          const pct = s.tasks.length ? (done / s.tasks.length) * 100 : 0;
          return (
            <li key={s.id}>
              <a
                href={`#${s.code}`}
                className="block rounded-lg border border-slate-800 bg-slate-900/50 p-2 text-center hover:border-slate-600"
              >
                <p className="font-mono text-xs text-slate-400">{s.code}</p>
                <div className="mx-auto mt-1 h-1 w-full rounded bg-slate-800">
                  <div className="h-full rounded bg-emerald-400" style={{ width: `${pct}%` }} />
                </div>
              </a>
            </li>
          );
        })}
      </ol>

      <div className="space-y-6">
        {progress.stages.map((s) => {
          const done = s.tasks.filter((t) => t.done).length;
          return (
            <section
              key={s.id}
              id={s.code}
              className="scroll-mt-24 rounded-2xl border border-slate-800 bg-slate-900/40 p-5 md:p-6"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="rounded-md bg-slate-800 px-2 py-0.5 font-mono text-xs text-emerald-300">
                      {s.code}
                    </span>
                    <h2 className="text-lg font-semibold">{s.title}</h2>
                  </div>
                  <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-300">{s.goal}</p>
                </div>
                <div className="text-right text-xs text-slate-500">
                  <p>
                    {done}/{s.tasks.length} 完成
                  </p>
                  <p>≈ {s.estHours} h</p>
                </div>
              </div>

              <div className="mt-4 grid gap-3 md:grid-cols-3">
                <Info label="主用插件" value={s.plugin} tone="emerald" />
                <Info label="内存注意" value={s.memoryNote} tone="amber" />
                <Info label="交付物" value={s.deliverable} tone="sky" />
              </div>

              <div className="mt-3 flex flex-wrap gap-1.5">
                {s.tools.map((t) => (
                  <Chip key={t}>{t}</Chip>
                ))}
              </div>

              <ul className="mt-4 space-y-2">
                {s.tasks.map((t) => (
                  <TaskItem key={t.id} id={t.id} title={t.title} detail={t.detail} done={t.done} />
                ))}
              </ul>

              <p className="mt-4 rounded-lg border border-dashed border-violet-500/40 bg-violet-500/5 p-3 text-xs text-violet-200">
                📸 <span className="font-semibold">必拍截图：</span>
                {s.screenshotHint}
              </p>
            </section>
          );
        })}
      </div>
    </div>
  );
}

function Info({ label, value, tone }: { label: string; value: string; tone: string }) {
  const tones: Record<string, string> = {
    emerald: "text-emerald-300",
    amber: "text-amber-300",
    sky: "text-sky-300",
  };
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
      <p className={`text-[11px] font-semibold uppercase tracking-wider ${tones[tone]}`}>{label}</p>
      <p className="mt-1 text-xs leading-relaxed text-slate-300">{value}</p>
    </div>
  );
}
