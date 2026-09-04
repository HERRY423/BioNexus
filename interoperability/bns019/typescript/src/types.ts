/**
 * Type definitions for BNS-019 Scientific Semantic Conventions.
 */

export type ConventionType =
  | "scientific.observation"
  | "scientific.dataset"
  | "scientific.claim";

export type MatrixState =
  | "raw_counts"
  | "normalized_counts"
  | "log_normalized"
  | "scaled";

export type WarrantLevel =
  | "unassessed"
  | "fragile"
  | "preliminary"
  | "supported"
  | "robust"
  | "replicated";

export type WarrantStatus =
  | "unassessed"
  | "assessed"
  | "conflicted"
  | "abstained";

export type ClaimType =
  | "associative"
  | "causal"
  | "mechanistic"
  | "predictive";

export type AttributeValue = string | string[];

export interface AttributeMap {
  [key: string]: AttributeValue;
}

export interface SemanticEnvelope {
  schema_url: string;
  convention: ConventionType | string;
  producer: string;
  record_id: string | null;
  source_record_sha256: string | null;
  attributes: AttributeMap;
  semantic_fingerprint_sha256: string;
}

export interface ScientificObservationAttributes extends AttributeMap {
  "biological.unit"?: string;
  "matrix.state"?: MatrixState | string;
  "claim.type": ClaimType | string;
  "evidence.type": string[];
  "confound.type"?: string[];
  "warrant.level"?: WarrantLevel | string;
  "warrant.status"?: WarrantStatus | string;
}

export interface ScientificObservationEnvelope extends SemanticEnvelope {
  convention: "scientific.observation";
  attributes: ScientificObservationAttributes;
}

export interface ScientificDatasetEnvelope extends SemanticEnvelope {
  convention: "scientific.dataset";
  attributes: AttributeMap;
}

export interface ScientificClaimEnvelope extends SemanticEnvelope {
  convention: "scientific.claim";
  attributes: AttributeMap;
}

export interface AttributeValidationReport {
  valid: boolean;
  normalized_attributes: Record<string, any>;
  failure_classes: string[];
  errors: string[];
  warnings: string[];
}

export interface RegistryGroup {
  description: string;
  attributes: Record<string, "required" | "recommended" | "opt_in">;
}

export interface RegistryAttributeDefinition {
  cardinality: "one" | "many";
  description: string;
  values?: string[];
  stability: string;
}

export interface SemanticRegistry {
  schema: string;
  standard_id: string;
  schema_version: string;
  stability: string;
  canonical_namespace: string;
  extension_namespace_pattern: string;
  attribute_aliases: Record<string, string>;
  value_aliases: Record<string, Record<string, string>>;
  blocked_legacy_values: Record<string, Record<string, string>>;
  groups: Record<string, RegistryGroup>;
  attributes: Record<string, RegistryAttributeDefinition>;
}

export interface ReleaseManifestFileRecord {
  path: string;
  sha256: string;
  size_bytes: number;
}

export interface ReleaseManifest {
  schema: string;
  standard_id: string;
  artifact_name: string;
  version: string;
  status: string;
  digest_algorithm: string;
  files: ReleaseManifestFileRecord[];
  release_digest_sha256: string;
  claim_boundary: string;
}
