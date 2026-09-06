/**
 * Independent, zero-dependency BNS-019 validator in TypeScript.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { resolve, relative, join } from "node:path";
import { canonicalJson, sha256Bytes, sha256CanonicalJson } from "./canonical_json.ts";
import type {
  AttributeMap,
  AttributeValidationReport,
  ReleaseManifest,
  SemanticRegistry,
} from "./types.ts";

export const MANIFEST_SCHEMA = "urn:bionexus:scientific-semantic-release-manifest:1";
export const RESULT_SCHEMA = "urn:bionexus:bns019-implementation-result:1";
export const STANDARD_ID = "BNS-019";
export const ARTIFACT_NAME = "bionexus-scientific-semantic-conventions";

export class ValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ValidationError";
  }
}

function readJson<T = unknown>(path: string, label: string): T {
  try {
    const text = readFileSync(path, "utf-8");
    return JSON.parse(text) as T;
  } catch (err: any) {
    throw new ValidationError(`cannot read ${label}: ${err?.message || err}`);
  }
}

function getAllFiles(dir: string, baseDir: string = dir): string[] {
  let results: string[] = [];
  const entries = readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name !== "__pycache__" && entry.name !== ".git") {
        results = results.concat(getAllFiles(fullPath, baseDir));
      }
    } else if (entry.isFile()) {
      if (entry.name !== "release-manifest.json") {
        const rel = relative(baseDir, fullPath).replace(/\\/g, "/");
        results.push(rel);
      }
    }
  }
  return results.sort();
}

export function loadVerifiedRelease(standardRoot: string): {
  manifest: ReleaseManifest;
  registry: SemanticRegistry;
} {
  const root = resolve(standardRoot);
  const manifestPath = join(root, "release-manifest.json");
  const manifest = readJson<ReleaseManifest>(manifestPath, "release manifest");

  if (manifest.schema !== MANIFEST_SCHEMA) {
    throw new ValidationError("unsupported release manifest schema");
  }
  if (manifest.standard_id !== STANDARD_ID || manifest.artifact_name !== ARTIFACT_NAME) {
    throw new ValidationError("release identity mismatch");
  }

  const versionPath = join(root, "VERSION");
  let version = "";
  try {
    version = readFileSync(versionPath, "utf-8").trim();
  } catch (err: any) {
    throw new ValidationError(`cannot read VERSION: ${err?.message || err}`);
  }
  if (!version || manifest.version !== version) {
    throw new ValidationError("release version mismatch");
  }

  if (!Array.isArray(manifest.files) || manifest.files.length === 0) {
    throw new ValidationError("manifest files must be a non-empty array");
  }

  const seen = new Set<string>();
  for (const record of manifest.files) {
    const rel = record.path;
    if (seen.has(rel)) {
      throw new ValidationError(`duplicate manifest path: ${rel}`);
    }
    seen.add(rel);

    const fullPath = join(root, rel);
    let st;
    try {
      st = statSync(fullPath);
    } catch {
      throw new ValidationError(`manifest file is missing: ${rel}`);
    }

    if (st.size !== record.size_bytes) {
      throw new ValidationError(`size mismatch: ${rel}`);
    }

    const content = readFileSync(fullPath);
    const hash = sha256Bytes(content);
    if (hash !== record.sha256) {
      throw new ValidationError(`SHA-256 mismatch: ${rel}`);
    }
  }

  const distributed = new Set(getAllFiles(root));
  if (seen.size !== distributed.size || [...seen].some((x) => !distributed.has(x))) {
    throw new ValidationError("manifest inventory mismatch");
  }

  const expectedDigest = sha256CanonicalJson(manifest.files);
  if (manifest.release_digest_sha256 !== expectedDigest) {
    throw new ValidationError("release_digest_sha256 mismatch");
  }

  const registry = readJson<SemanticRegistry>(join(root, "registry.json"), "registry");
  if (registry.schema_version !== version) {
    throw new ValidationError("registry version mismatch");
  }

  return { manifest, registry };
}

function failureClass(message: string): string {
  if (message.includes(" is blocked:")) {
    return "blocked_legacy_value";
  }
  if (message.startsWith("missing required attribute:")) {
    return "missing_required_attribute";
  }
  if (message.startsWith("unknown attribute ")) {
    return "unknown_attribute";
  }
  if (message.startsWith("unknown value for ")) {
    return "unknown_registered_value";
  }
  if (message.startsWith("conflicting values supplied for ")) {
    return "conflicting_alias";
  }
  if (message.startsWith("unknown convention group:")) {
    return "unknown_convention";
  }
  if (message.includes(" must be ") || message.includes(" must contain ")) {
    return "type_or_cardinality";
  }
  return "semantic_validation_error";
}

export function validateAttributes(
  registry: SemanticRegistry,
  convention: string,
  attributes: Record<string, any>
): AttributeValidationReport {
  const groups = registry.groups || {};
  const definitions = registry.attributes || {};

  if (!groups[convention]) {
    const errors = [`unknown convention group: ${convention}`];
    return {
      valid: false,
      normalized_attributes: {},
      failure_classes: errors.map(failureClass),
      errors,
      warnings: [],
    };
  }

  if (!attributes || typeof attributes !== "object" || Array.isArray(attributes)) {
    const errors = ["attributes must be an object"];
    return {
      valid: false,
      normalized_attributes: {},
      failure_classes: errors.map(failureClass),
      errors,
      warnings: [],
    };
  }

  const aliases = registry.attribute_aliases || {};
  const canonical: Record<string, any> = {};
  const errors: string[] = [];
  const warnings: string[] = [];

  for (const [suppliedName, suppliedValue] of Object.entries(attributes)) {
    const target = aliases[suppliedName] || suppliedName;
    if (target in canonical && canonical[target] !== suppliedValue) {
      errors.push(`conflicting values supplied for ${target} through an alias`);
      continue;
    }
    canonical[target] = suppliedValue;
  }

  const extensionPattern = new RegExp(registry.extension_namespace_pattern);
  const normalized: Record<string, any> = {};

  for (const name of Object.keys(canonical).sort()) {
    const value = canonical[name];
    if (!definitions[name]) {
      if (extensionPattern.test(name)) {
        if (typeof value === "string") {
          normalized[name] = value;
        } else if (
          Array.isArray(value) &&
          value.every((item) => typeof item === "string")
        ) {
          normalized[name] = [...new Set(value)].sort();
        } else {
          errors.push(`extension attribute ${name} must be a string or string array`);
        }
      } else {
        errors.push(`unknown attribute ${name}; custom attributes must use x.<vendor>.*`);
      }
      continue;
    }

    const definition = definitions[name];
    const isMany = definition.cardinality === "many";
    let values: string[];

    if (isMany) {
      if (!Array.isArray(value)) {
        errors.push(`${name} must be a string array`);
        continue;
      }
      if (value.length === 0) {
        errors.push(`${name} must contain at least one value`);
        continue;
      }
      if (!value.every((item) => typeof item === "string")) {
        errors.push(`${name} must contain only strings`);
        continue;
      }
      values = value;
    } else {
      if (typeof value !== "string") {
        errors.push(`${name} must be a string`);
        continue;
      }
      values = [value];
    }

    const allowed = new Set(definition.values || []);
    const valueAliases = registry.value_aliases?.[name] || {};
    const blocked = registry.blocked_legacy_values?.[name] || {};
    const output: string[] = [];
    const itemErrors: string[] = [];

    for (const raw of values) {
      if (raw in blocked) {
        itemErrors.push(`${name}=${JSON.stringify(raw)} is blocked: ${blocked[raw]}`);
        continue;
      }
      const item = valueAliases[raw] || raw;
      if (!allowed.has(item)) {
        itemErrors.push(`unknown value for ${name}: ${JSON.stringify(item)}`);
        continue;
      }
      output.push(item);
    }

    errors.push(...itemErrors);
    if (itemErrors.length === 0) {
      normalized[name] = isMany ? [...new Set(output)].sort() : output[0];
    }
  }

  const requirements = groups[convention].attributes || {};
  for (const [name, req] of Object.entries(requirements)) {
    if (req === "required" && !(name in normalized)) {
      errors.push(`missing required attribute: ${name}`);
    } else if (req === "recommended" && !(name in normalized)) {
      warnings.push(`missing recommended attribute: ${name}`);
    }
  }

  const failureClasses = [...new Set(errors.map(failureClass))];
  return {
    valid: errors.length === 0,
    normalized_attributes: normalized,
    failure_classes: failureClasses,
    errors,
    warnings,
  };
}

export function runConformanceSuite(standardRoot: string): Record<string, any> {
  const { manifest, registry } = loadVerifiedRelease(standardRoot);
  const conformanceRoot = join(resolve(standardRoot), "conformance");
  const suite = readJson<{ cases: any[] }>(join(conformanceRoot, "manifest.json"), "conformance manifest");

  const caseResults: any[] = [];
  for (const c of suite.cases || []) {
    const fixture = readJson<any>(join(conformanceRoot, c.input), `case ${c.id}`);
    const observed = validateAttributes(registry, fixture.convention || "", fixture.attributes || {});

    let matched = observed.valid === c.expected_valid;
    if (c.expected_valid) {
      const expectedNorm = canonicalJson(c.expected_normalized_attributes);
      const observedNorm = canonicalJson(observed.normalized_attributes);
      matched = matched && expectedNorm === observedNorm;
    } else {
      matched = matched && observed.failure_classes.includes(c.expected_failure_class);
    }

    caseResults.push({
      case_id: c.id,
      status: matched ? "PASS" : "FAIL",
      expected_valid: c.expected_valid,
      observed_valid: observed.valid,
      normalized_attributes: observed.normalized_attributes,
      failure_classes: observed.failure_classes,
    });
  }

  const allPass = caseResults.length > 0 && caseResults.every((c) => c.status === "PASS");

  return {
    schema: RESULT_SCHEMA,
    implementation: {
      id: "bns019-typescript",
      track: "independent_validator",
      language: "typescript",
    },
    standard: {
      id: STANDARD_ID,
      version: manifest.version,
      release_digest_sha256: manifest.release_digest_sha256,
    },
    status: allPass ? "PASS" : "FAIL",
    case_results: caseResults,
    claim_boundary: "Software-contract conformance only; not certification or biological validation.",
  };
}
