/**
 * Test envelope creation, producer helpers, and fingerprint calculation.
 */

import assert from "node:assert";
import {
  createObservationEnvelope,
  createDatasetEnvelope,
  createClaimEnvelope,
  computeSemanticFingerprint,
} from "../src/producer.ts";

function testProducerEnvelopeCreation() {
  const obs = createObservationEnvelope({
    producer: "test.producer",
    record_id: "obs-1",
    source_record_sha256: "0".repeat(64),
    attributes: {
      "biological.unit": "cell",
      "claim.type": "associative",
      "evidence.type": ["computational_result"],
      "matrix.state": "log_normalized",
    },
  });

  assert.strictEqual(obs.convention, "scientific.observation");
  assert.strictEqual(obs.producer, "test.producer");
  assert.strictEqual(obs.attributes["biological.unit"], "cell");
  assert.strictEqual(obs.semantic_fingerprint_sha256.length, 64);

  // Recalculate fingerprint manually and verify
  const expectedFingerprint = computeSemanticFingerprint(obs);
  assert.strictEqual(obs.semantic_fingerprint_sha256, expectedFingerprint);

  console.log("testProducerEnvelopeCreation: PASSED");
}

function testDatasetEnvelopeCreation() {
  const ds = createDatasetEnvelope({
    producer: "geo.importer",
    record_id: "GSE12345",
    source_record_sha256: "a".repeat(64),
    attributes: {
      "biological.unit": "spot",
      "matrix.state": "raw_counts",
    },
  });

  assert.strictEqual(ds.convention, "scientific.dataset");
  assert.strictEqual(ds.attributes["matrix.state"], "raw_counts");
  assert.strictEqual(ds.semantic_fingerprint_sha256.length, 64);

  console.log("testDatasetEnvelopeCreation: PASSED");
}

function main() {
  testProducerEnvelopeCreation();
  testDatasetEnvelopeCreation();
  console.log("All TypeScript producer tests passed!");
}

main();
