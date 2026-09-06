"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

export function TaskItem({
  id,
  title,
  detail,
  done,
}: {
  id: number;
  title: string;
  detail: string;
  done: boolean;
}) {
  const router = useRouter();
  const [checked, setChecked] = useState(done);
  const [pending, startTransition] = useTransition();

  async function toggle() {
    const next = !checked;
    setChecked(next);
    const res = await fetch(`/api/tasks/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ done: next }),
    });
    if (!res.ok) {
      setChecked(!next);
      return;
    }
    startTransition(() => router.refresh());
  }

  return (
    <li className="flex gap-3 rounded-lg border border-slate-800 bg-slate-900/60 p-3">
      <button
        type="button"
        onClick={toggle}
        disabled={pending}
        aria-label={checked ? "标记未完成" : "标记完成"}
        className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded border transition ${
          checked
            ? "border-emerald-400 bg-emerald-500 text-slate-950"
            : "border-slate-600 bg-slate-950 hover:border-slate-400"
        }`}
      >
        {checked && (
          <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={3}>
            <path d="M4 10l4 4 8-8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </button>
      <div className="min-w-0">
        <p className={`text-sm font-medium ${checked ? "text-slate-500 line-through" : "text-slate-100"}`}>
          {title}
        </p>
        {detail && <p className="mt-1 text-xs leading-relaxed text-slate-400">{detail}</p>}
      </div>
    </li>
  );
}
