import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Nav } from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "SpatialWarrant · Mission Control",
  description:
    "Evidence-audited spatial atlas of the tumor–immune boundary — Rosalind Workbench × Life Sciences Literature × BioNexus",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen bg-slate-950 text-slate-100 antialiased">
        <Nav />
        <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
        <footer className="mx-auto max-w-6xl px-4 pb-10 pt-6 text-xs text-slate-600">
          SpatialWarrant · Research Use Only · Built for the Rosalind Workbench showcase ·
          Plugins: NGS Analysis Workbench · Life Sciences Literature · BioNexus Reliability
        </footer>
      </body>
    </html>
  );
}
