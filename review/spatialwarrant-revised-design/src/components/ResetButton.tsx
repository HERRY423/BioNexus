"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

export function ResetButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [, start] = useTransition();
  async function reset() {
    if (!confirm("重置整个作战台到初始方案？（会清空勾选与自定义 claim）")) return;
    setBusy(true);
    await fetch("/api/seed", { method: "POST" });
    setBusy(false);
    start(() => router.refresh());
  }
  return (
    <button
      type="button"
      onClick={reset}
      disabled={busy}
      className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-400 hover:border-rose-400 hover:text-rose-300 disabled:opacity-50"
    >
      {busy ? "重置中…" : "重置方案"}
    </button>
  );
}
