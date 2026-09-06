/**
 * Deterministic canonical JSON serialization and SHA-256 computation matching BNS-019.
 */

import { createHash } from "node:crypto";

export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return "[" + value.map(canonicalJson).join(",") + "]";
  }
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj).sort();
  return (
    "{" +
    keys.map((k) => JSON.stringify(k) + ":" + canonicalJson(obj[k])).join(",") +
    "}"
  );
}

export function sha256Bytes(content: string | Buffer): string {
  return createHash("sha256").update(content).digest("hex");
}

export function sha256CanonicalJson(value: unknown): string {
  return sha256Bytes(canonicalJson(value));
}
