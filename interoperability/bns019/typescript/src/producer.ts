/**
 * Producer helper for constructing and signing BNS-019 scientific semantic envelopes.
 */

import { sha256CanonicalJson } from "./canonical_json.ts";
import type {
  AttributeMap,
  ConventionType,
  ScientificObservationAttributes,
  ScientificObservationEnvelope,
  ScientificDatasetEnvelope,
  ScientificClaimEnvelope,
  SemanticEnvelope,
} from "./types.ts";

export const SCHEMA_URL = "urn:bionexus:scientific-semantic-conventions:0.1.0";

export interface CreateEnvelopeOptions<TAttrs extends AttributeMap = AttributeMap> {
  producer: string;
  record_id?: string | null;
  source_record_sha256?: string | null;
  attributes: TAttrs;
}

export function computeSemanticFingerprint(
  envelope: Omit<SemanticEnvelope, "semantic_fingerprint_sha256">
): string {
  const payload = {
    schema_url: envelope.schema_url,
    convention: envelope.convention,
    producer: envelope.producer,
    record_id: envelope.record_id,
    source_record_sha256: envelope.source_record_sha256,
    attributes: envelope.attributes,
  };
  return sha256CanonicalJson(payload);
}

export function createEnvelope<TAttrs extends AttributeMap>(
  convention: ConventionType | string,
  options: CreateEnvelopeOptions<TAttrs>
): SemanticEnvelope {
  const base = {
    schema_url: SCHEMA_URL,
    convention,
    producer: options.producer,
    record_id: options.record_id ?? null,
    source_record_sha256: options.source_record_sha256 ?? null,
    attributes: options.attributes,
  };
  const fingerprint = computeSemanticFingerprint(base);
  return {
    ...base,
    semantic_fingerprint_sha256: fingerprint,
  };
}

export function createObservationEnvelope(
  options: CreateEnvelopeOptions<ScientificObservationAttributes>
): ScientificObservationEnvelope {
  return createEnvelope("scientific.observation", options) as ScientificObservationEnvelope;
}

export function createDatasetEnvelope(
  options: CreateEnvelopeOptions
): ScientificDatasetEnvelope {
  return createEnvelope("scientific.dataset", options) as ScientificDatasetEnvelope;
}

export function createClaimEnvelope(
  options: CreateEnvelopeOptions
): ScientificClaimEnvelope {
  return createEnvelope("scientific.claim", options) as ScientificClaimEnvelope;
}
