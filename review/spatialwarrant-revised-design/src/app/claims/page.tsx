import { CeilingBadge, ClassBadge, VerdictBadge } from "@/components/Badge";
import { getClaims } from "@/lib/queries";

export const dynamic = "force-dynamic";

const LADDER = [
  { cls: "descriptive", zh: "描述性排序", need: "≥ PRELIMINARY" },
  { cls: "association", zh: "样本内关联", need: "≥ SUPPORTED" },
  { cls: "population_effect", zh: "人群级效应", need: "多供体 + 可识别设计" },
  { cls: "mechanistic", zh: "机制", need: "扰动/独立验证" },
  { cls: "causal", zh: "因果", need: "干预证据" },
  { cls: "clinical", zh: "临床可操作", need: "REPLICATED + 外部验证 + 监管" },
];

export default async function ClaimsPage() {
  const rows = await getClaims();
  const real = rows.filter((c) => !c.isTrap);
  const traps = rows.filter((c) => c.isTrap);

  return (
    <div className="space-y-8">
      <header>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Claim–Evidence Ledger</h1>
          <p className="mt-1 max-w-3xl text-sm text-slate-400">
            与 BioNexus 账本对齐的只读预注册视图。<strong className="text-slate-200">TO_BE_COMPUTED</strong>
            表示结果尚未产生；真实 verdict 只能从哈希绑定的 receipt 导入，不能在展示页手工修改。
          </p>
        </div>
      </header>

      {/* Epistemic ladder */}
      <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Claim class 阶梯（目的决定要求，不改变证据本身）</p>
        <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-6">
          {LADDER.map((l, i) => (
            <div key={l.cls} className="rounded-lg border border-slate-800 bg-slate-950/50 p-2">
              <div className="flex items-center gap-1">
                <span className="font-mono text-[10px] text-slate-600">{i + 1}</span>
                <ClassBadge value={l.cls} />
              </div>
              <p className="mt-1 text-xs text-slate-300">{l.zh}</p>
              <p className="text-[10px] text-slate-500">{l.need}</p>
            </div>
          ))}
        </div>
      </section>

      <ClaimTable title="核心声明" rows={real} />
      <ClaimTable
        title="越界测试与技术对照"
        sub="保留原方案的陷阱演示；技术阳性对照不由生物学结果定义。"
        rows={traps}
      />
    </div>
  );
}

function ClaimTable({
  title,
  sub,
  rows,
}: {
  title: string;
  sub?: string;
  rows: Awaited<ReturnType<typeof getClaims>>;
}) {
  return (
    <section>
      <h2 className="text-lg font-semibold">{title}</h2>
      {sub && <p className="mb-3 mt-1 text-xs text-slate-400">{sub}</p>}
      <div className="mt-3 space-y-3">
        {rows.length === 0 && (
          <p className="rounded-lg border border-dashed border-slate-800 p-4 text-sm text-slate-500">暂无声明</p>
        )}
        {rows.map((c) => (
          <article
            key={c.id}
            className={`rounded-xl border p-4 ${
              c.isTrap ? "border-rose-500/30 bg-rose-500/5" : "border-slate-800 bg-slate-900/50"
            }`}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs font-bold text-emerald-300">{c.code}</span>
                  <ClassBadge value={c.claimClass} />
                  <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
                    {c.stageCode}
                  </span>
                </div>
                <p className="mt-2 text-sm leading-relaxed text-slate-100">{c.statement}</p>
                <p className="mt-2 text-xs text-slate-400">
                  <span className="text-slate-500">证据事实：</span>
                  {c.evidenceFacts || "—"}
                </p>
                <p className="mt-1 font-mono text-[11px] text-slate-500">audit: {c.capability}</p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-2 text-right">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] uppercase text-slate-500">预期天花板</span>
                  <CeilingBadge value={c.expectedCeiling} />
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] uppercase text-slate-500">实际判决</span>
                  <VerdictBadge value={c.verdict} />
                </div>
                <span className="text-[10px] text-slate-500">receipt import only</span>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
