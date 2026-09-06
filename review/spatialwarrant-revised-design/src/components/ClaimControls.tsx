"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

const VERDICTS = ["PENDING", "WARRANTED", "WARRANTED_WITH_LIMITS", "NOT_SUFFICIENT", "REFUSED"];

export function VerdictSelect({ id, value }: { id: number; value: string }) {
  const router = useRouter();
  const [v, setV] = useState(value);
  const [, start] = useTransition();

  async function onChange(next: string) {
    setV(next);
    await fetch(`/api/claims/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ verdict: next }),
    });
    start(() => router.refresh());
  }

  return (
    <select
      value={v}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-[11px] text-slate-200 focus:border-emerald-400 focus:outline-none"
    >
      {VERDICTS.map((x) => (
        <option key={x} value={x}>
          {x}
        </option>
      ))}
    </select>
  );
}

export function DeleteClaim({ id }: { id: number }) {
  const router = useRouter();
  const [, start] = useTransition();
  async function del() {
    if (!confirm("删除这条 claim？")) return;
    await fetch(`/api/claims/${id}`, { method: "DELETE" });
    start(() => router.refresh());
  }
  return (
    <button
      type="button"
      onClick={del}
      className="text-xs text-slate-500 hover:text-rose-400"
      aria-label="删除"
    >
      删除
    </button>
  );
}

export function AddClaimForm({ stageCodes }: { stageCodes: string[] }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [, start] = useTransition();

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const fd = new FormData(e.currentTarget);
    const payload = {
      code: fd.get("code"),
      statement: fd.get("statement"),
      claimClass: fd.get("claimClass"),
      capability: fd.get("capability"),
      expectedCeiling: fd.get("expectedCeiling"),
      evidenceFacts: fd.get("evidenceFacts"),
      stageCode: fd.get("stageCode"),
      isTrap: fd.get("isTrap") === "on",
    };
    const res = await fetch("/api/claims", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setBusy(false);
    if (!res.ok) {
      const j = (await res.json().catch(() => ({}))) as { error?: string };
      setError(j.error ?? "提交失败");
      return;
    }
    e.currentTarget.reset();
    setOpen(false);
    start(() => router.refresh());
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400"
      >
        + 新增 claim
      </button>
    );
  }

  const input =
    "w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-emerald-400 focus:outline-none";

  return (
    <form onSubmit={submit} className="grid gap-3 rounded-xl border border-slate-800 bg-slate-900/70 p-4 md:grid-cols-2">
      <input name="code" placeholder="编号，如 C7" required className={input} />
      <select name="stageCode" className={input} defaultValue="S7">
        {stageCodes.map((c) => (
          <option key={c} value={c}>
            阶段 {c}
          </option>
        ))}
      </select>
      <textarea
        name="statement"
        required
        placeholder="声明内容（越具体越好，写清阈值与切片数）"
        className={`${input} md:col-span-2`}
        rows={2}
      />
      <select name="claimClass" className={input} defaultValue="descriptive">
        {["descriptive", "association", "population_effect", "mechanistic", "causal", "clinical"].map((c) => (
          <option key={c}>{c}</option>
        ))}
      </select>
      <select name="expectedCeiling" className={input} defaultValue="FRAGILE">
        {["ROBUST", "SUPPORTED", "FRAGILE", "ABSTAIN", "REFUSED"].map((c) => (
          <option key={c}>{c}</option>
        ))}
      </select>
      <input
        name="capability"
        placeholder="审计能力，如 scrna.pseudobulk_de"
        className={input}
        defaultValue="spatial.inference_validity"
      />
      <input name="evidenceFacts" placeholder="证据事实（设计 / 患者数 / 真值 / 敏感性）" className={input} />
      <label className="flex items-center gap-2 text-xs text-slate-300">
        <input type="checkbox" name="isTrap" className="accent-emerald-500" />
        这是一个陷阱 / 对照声明
      </label>
      <div className="flex items-center justify-end gap-2">
        {error && <span className="text-xs text-rose-400">{error}</span>}
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="rounded-md px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200"
        >
          取消
        </button>
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-emerald-500 px-4 py-1.5 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-50"
        >
          {busy ? "保存中…" : "保存"}
        </button>
      </div>
    </form>
  );
}
