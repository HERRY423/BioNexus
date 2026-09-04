#!/usr/bin/env node
/**
 * CLI runner for BNS-019 TypeScript validator.
 */

import { writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { runConformanceSuite, ValidationError } from "./validator.ts";

function parseArgs(): { standardRoot: string; output?: string } {
  const args = process.argv.slice(2);
  let standardRoot = "";
  let output: string | undefined;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--standard-root" && i + 1 < args.length) {
      standardRoot = args[++i];
    } else if (args[i] === "--output" && i + 1 < args.length) {
      output = args[++i];
    }
  }

  if (!standardRoot) {
    console.error("Usage: bns019-validator --standard-root <path> [--output <path>]");
    process.exit(2);
  }

  return { standardRoot, output };
}

function main() {
  const { standardRoot, output } = parseArgs();
  try {
    const result = runConformanceSuite(standardRoot);
    const jsonStr = JSON.stringify(result, null, 2) + "\n";
    if (output) {
      writeFileSync(resolve(output), jsonStr, "utf-8");
    } else {
      process.stdout.write(jsonStr);
    }
    process.exit(result.status === "PASS" ? 0 : 1);
  } catch (err: any) {
    console.error("ERROR:", err?.message || err);
    process.exit(2);
  }
}

main();
