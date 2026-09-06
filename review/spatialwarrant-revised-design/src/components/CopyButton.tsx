"use client";

import { useState } from "react";

export function CopyButton({ text, label = "复制" }: { text: string; label?: string }) {
  const [ok, setOk] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setOk(true);
      setTimeout(() => setOk(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  }
  return (
    <button
      type="button"
      onClick={copy}
      className="rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:border-emerald-400 hover:text-emerald-300"
    >
      {ok ? "已复制 ✓" : label}
    </button>
  );
}
