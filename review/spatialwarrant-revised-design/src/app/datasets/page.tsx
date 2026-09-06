import { Chip } from "@/components/Badge";
import { getDatasets } from "@/lib/queries";

export const dynamic = "force-dynamic";

const PRIORITY: Record<string, { label: string; tone: string }> = {
  primary: { label: "主数据", tone: "emerald" },
  validation: { label: "留出验证", tone: "sky" },
  knowledge: { label: "知识库", tone: "violet" },
  fallback: { label: "Plan B", tone: "amber" },
};

export default async function DatasetsPage() {
  const rows = await getDatasets();
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">公开数据集</h1>
        <p className="mt-1 text-sm text-slate-400">
          全部公开可下载，无需湿实验。主数据来自 Wu et al. 2021 Nat Genet（scRNA + Visium + 病理标注同源），
          外加 10x 公开切片做 held-out 验证，以及一套 2 小时可切换的 Plan B。
        </p>
      </header>

      <div className="grid gap-4 md:grid-cols-2">
        {rows.map((d) => {
          const p = PRIORITY[d.priority] ?? PRIORITY.primary;
          return (
            <article key={d.id} className="rounded-xl border border-slate-800 bg-slate-900/50 p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <Chip tone={p.tone}>{p.label}</Chip>
                  <h2 className="mt-2 font-semibold leading-snug text-slate-100">{d.name}</h2>
                  <p className="mt-0.5 font-mono text-xs text-slate-400">{d.accession}</p>
                </div>
                <a
                  href={d.sourceUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="shrink-0 rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:border-emerald-400 hover:text-emerald-300"
                >
                  打开 ↗
                </a>
              </div>
              <dl className="mt-4 grid gap-2 text-xs">
                <Row k="模态" v={d.modality} />
                <Row k="用途" v={d.role} />
                <Row k="体积" v={d.sizeNote} />
                <Row k="内存" v={d.ramNote} />
              </dl>
            </article>
          );
        })}
      </div>

      <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-5 text-sm text-slate-300">
        <h3 className="font-semibold text-slate-100">下载与格式提示</h3>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-relaxed text-slate-400">
          <li>GSE176078 的补充文件为 10x 三件套（matrix.mtx / features / barcodes）+ metadata.csv，直接 <code className="text-emerald-300">sc.read_10x_mtx</code> 后 join metadata。</li>
          <li>Zenodo 4739739 每张切片含 <code className="text-emerald-300">filtered_count_matrices/</code>、<code className="text-emerald-300">spatial/</code>、<code className="text-emerald-300">metadata/</code>（病理标注列通常为 Classification）。若缺 <code className="text-emerald-300">scalefactors_json.json</code>，用 Loupe 导出的 tissue_positions 手动构造 <code className="text-emerald-300">adata.obsm[&quot;spatial&quot;]</code>。</li>
          <li>BioNexus 会在没有坐标时拒绝空间分析——这是设计好的硬规则，可以作为一张「诚实拒绝」截图。</li>
          <li>先用 BioNexus provenance 对所有文件做 SHA-256，再开始任何分析；否则后面的 ledger 不能计入 hash-verified 证据。</li>
        </ul>
      </section>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="grid grid-cols-[3.5rem_1fr] gap-2">
      <dt className="text-slate-500">{k}</dt>
      <dd className="leading-relaxed text-slate-300">{v}</dd>
    </div>
  );
}
