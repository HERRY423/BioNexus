"""
BioNexus Claim–Evidence Ledger (BNS-012).

A scientific claim is not a sentence — it is a node in a dependency graph:

    Claim -> supported_by (evidence refs)
          -> contradicted_by (evidence refs)
          -> depends_on (datasets, transformations, method runs)
          -> evidence_status (maturity)

This module implements ONLY the data structure: plain dataclasses,
JSON round-trip, and a PROV-O flavored JSON-LD projection. No graph
database, no UI, no platform — the ledger stays a plugin artifact.

Status resolution is fail-closed (BNS-005): any non-empty contradiction
forces CONFLICTED; otherwise the claim inherits the minimum maturity of
its supporting evidence, clamped by the capability's ABI evidence ceiling.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from bionexus.abi import enforce_evidence_ceiling
from bionexus.attestation_authority import (
    canonical_json_bytes,
    canonical_json_sha256,
    generate_tsa_timestamp_token,
    load_private_key_from_env,
    verify_tsa_timestamp_token,
)
from bionexus.contracts import ConclusionMaturity

MATURITY_RANKS = {
    ConclusionMaturity.ABSTAIN.value: 0,
    ConclusionMaturity.UNASSESSED.value: 0,
    ConclusionMaturity.PRELIMINARY.value: 1,
    ConclusionMaturity.FRAGILE.value: 2,
    ConclusionMaturity.CONFLICTED.value: 2,
    ConclusionMaturity.SUPPORTED.value: 3,
    ConclusionMaturity.ROBUST.value: 4,
    ConclusionMaturity.REPLICATED.value: 5,
}

EVIDENCE_KINDS = (
    "dataset",            # primary input data (with content hash)
    "transformation",     # QC / normalization / preprocessing step
    "method_run",         # an executed analytical run (backend + parameters)
    "statistical_result", # test statistic, effect size, corrected p-value
    "database",           # external knowledge source (ClinVar, UniProt, ...)
    "literature",         # paper/preprint result; retrieval is not independent validation
    "inspection",         # sequence/structure/slide observation; no causal promotion
    "cross_method",       # concordance evidence from an alternative method
    "causal_dag",         # structural causal graph / d-separation validation
    "spatial_colocalization", # spatial adjacency / colocalization evidence
    "ligand_receptor",    # ligand-receptor expression / communication inference
    "perturbation",       # functional knockout / knockdown / rescue evidence
    "temporal_kinetics",  # longitudinal / time-series kinetics
    "claim_semantics",    # parsed claim IR / warrant engine record
)

VALIDATION_ROLES = (
    "supporting",
    "context_only",
    "external_validation",
    "reference_ground_truth",
)

_INDEPENDENCE_BASES = {
    "independent_dataset",
    "held_out_cohort",
    "orthogonal_assay",
    "blinded_external_evaluation",
}


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


@dataclass
class EvidenceRef:
    """One node of evidence the ledger can cite."""

    ref_id: str
    kind: str  # EVIDENCE_KINDS
    summary: str = ""
    maturity: str = ConclusionMaturity.PRELIMINARY.value
    provenance: Dict[str, Any] = field(default_factory=dict)
    validation_role: str = "supporting"

    def __post_init__(self) -> None:
        if self.kind not in EVIDENCE_KINDS:
            raise ValueError(f"Evidence kind '{self.kind}' not in {EVIDENCE_KINDS}")
        if self.maturity not in MATURITY_RANKS:
            raise ValueError(f"Unknown maturity '{self.maturity}'")
        if self.validation_role not in VALIDATION_ROLES:
            raise ValueError(f"Validation role '{self.validation_role}' not in {VALIDATION_ROLES}")
        if self.validation_role == "external_validation":
            self._validate_external_qualification()
        elif self.validation_role == "reference_ground_truth":
            self._validate_reference_qualification()

    def _validate_review(self) -> None:
        receipt_hash = self.provenance.get("review_receipt_sha256")
        if (
            self.provenance.get("review_status") != "approved"
            or not self.provenance.get("reviewer_id")
            or not _is_sha256(receipt_hash)
        ):
            raise ValueError(
                f"Evidence '{self.ref_id}' requires review_status='approved', a named reviewer_id, "
                "and review_receipt_sha256"
            )

    def _validate_external_qualification(self) -> None:
        self._validate_review()
        basis = self.provenance.get("independence_basis")
        if basis not in _INDEPENDENCE_BASES:
            raise ValueError(f"Evidence '{self.ref_id}' has unsupported independence_basis '{basis}'")
        target_hash = self.provenance.get("validation_target_sha256")
        evidence_hash = self.provenance.get("validation_evidence_sha256")
        if not _is_sha256(target_hash) or not _is_sha256(evidence_hash):
            raise ValueError(
                f"Evidence '{self.ref_id}' requires validation_target_sha256 and validation_evidence_sha256"
            )
        if target_hash == evidence_hash:
            raise ValueError(f"Evidence '{self.ref_id}' cannot validate an artifact against itself")

    def _validate_reference_qualification(self) -> None:
        self._validate_review()
        required = ("reference_release", "reference_scope", "reference_artifact_sha256")
        missing = [name for name in required if not self.provenance.get(name)]
        if missing or not _is_sha256(self.provenance.get("reference_artifact_sha256")):
            raise ValueError(f"Evidence '{self.ref_id}' has incomplete reference qualification: {missing}")

    @property
    def qualifies_as_external_validation(self) -> bool:
        try:
            if self.validation_role == "external_validation":
                self._validate_external_qualification()
                return True
            if self.validation_role == "reference_ground_truth":
                self._validate_reference_qualification()
                return True
        except ValueError:
            return False
        return False

    @property
    def is_reference_ground_truth(self) -> bool:
        if self.validation_role != "reference_ground_truth":
            return False
        try:
            self._validate_reference_qualification()
        except ValueError:
            return False
        return True


@dataclass
class ClaimRecord:
    """A scientific claim and its evidence dependencies (BNS-012 §2)."""

    claim_id: str
    statement: str
    capability_id: Optional[str] = None
    supported_by: List[str] = field(default_factory=list)
    contradicted_by: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    evidence_status: str = ConclusionMaturity.UNASSESSED.value
    provenance: Dict[str, Any] = field(default_factory=dict)
    causal_evaluation: Optional[Dict[str, Any]] = None
    structured_claim: Optional[Dict[str, Any]] = None
    warrant_evaluation: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ClaimLedger:
    """
    The claim–evidence graph as a plain data structure (BNS-012 §1).

    Deliberately NOT a graph platform: dict-of-records with integrity
    checks, JSON persistence, and a PROV-O JSON-LD projection.
    """

    def __init__(self) -> None:
        self.evidence: Dict[str, EvidenceRef] = {}
        self.claims: Dict[str, ClaimRecord] = {}
        self.cryptographic_seal: Optional[Dict[str, Any]] = None

    # -- construction ------------------------------------------------------

    def add_evidence(self, ref: EvidenceRef) -> EvidenceRef:
        if ref.ref_id in self.evidence:
            raise ValueError(f"Duplicate evidence ref '{ref.ref_id}'")
        self.evidence[ref.ref_id] = ref
        return ref

    def add_claim(self, claim: ClaimRecord, *, resolve: bool = True) -> ClaimRecord:
        if claim.claim_id in self.claims:
            raise ValueError(f"Duplicate claim '{claim.claim_id}'")
        self._assert_refs_exist(claim)
        self.claims[claim.claim_id] = claim
        if resolve:
            self.resolve_status(claim.claim_id)
        return claim

    def _assert_refs_exist(self, claim: ClaimRecord) -> None:
        missing = [
            r
            for r in (*claim.supported_by, *claim.contradicted_by, *claim.depends_on)
            if r not in self.evidence and not r.startswith("DATASET-")
        ]
        # DATASET- refs may be raw content hashes without an EvidenceRef node
        if missing:
            raise KeyError(f"Claim '{claim.claim_id}' references unknown evidence: {missing}")

    # -- resolution (fail-closed) -------------------------------------------

    def resolve_status(self, claim_id: str) -> str:
        """
        Resolve a claim's evidence status (BNS-012 §3).

        - any contradiction               -> CONFLICTED
        - no supporting evidence          -> ABSTAIN (claims need evidence)
        - otherwise                       -> min(supporting maturity), clamped
                                             by the capability's ABI ceiling
        """
        claim = self.claims[claim_id]

        if claim.contradicted_by:
            claim.evidence_status = ConclusionMaturity.CONFLICTED.value
            return claim.evidence_status

        supporting = [self.evidence[r] for r in claim.supported_by if r in self.evidence]
        if not supporting:
            claim.evidence_status = ConclusionMaturity.ABSTAIN.value
            return claim.evidence_status

        min_rank = min(MATURITY_RANKS.get(e.maturity, 0) for e in supporting)
        min_maturity = next(m for m, r in MATURITY_RANKS.items() if r == min_rank)

        if claim.capability_id:
            has_ext = any(
                self.evidence[r].qualifies_as_external_validation
                for r in claim.supported_by
                if r in self.evidence
            )
            min_maturity = enforce_evidence_ceiling(
                claim.capability_id, min_maturity, has_external_validation=has_ext
            )

        if claim.causal_evaluation:
            causal_ceiling = claim.causal_evaluation.get("maturity_ceiling")
            if causal_ceiling and MATURITY_RANKS.get(causal_ceiling, 0) < MATURITY_RANKS.get(min_maturity, 0):
                min_maturity = causal_ceiling

        # Semantic Claim IR & Deterministic Warrant Evaluation (BNS-017)
        if claim.structured_claim or claim.statement:
            try:
                from bionexus.claim_semantics import (
                    DeterministicClaimParser,
                    DeterministicWarrantEngine,
                    EvidenceProfile,
                )

                if claim.structured_claim:
                    # If already structured dict, rehydrate into ScientificClaimIR or evaluate
                    claim_ir = DeterministicClaimParser.parse(claim.statement, claim_id=claim.claim_id)
                else:
                    claim_ir = DeterministicClaimParser.parse(claim.statement, claim_id=claim.claim_id)

                # Assemble EvidenceProfile from supporting evidence nodes
                ev_profile = EvidenceProfile(
                    observational_data=bool(supporting),
                    spatial_colocalization=any(self.evidence[r].kind == "spatial_colocalization" for r in claim.supported_by if r in self.evidence),
                    ligand_receptor_inference=any(self.evidence[r].kind == "ligand_receptor" for r in claim.supported_by if r in self.evidence),
                    perturbation=any(self.evidence[r].kind == "perturbation" for r in claim.supported_by if r in self.evidence),
                    temporal_evidence=any(self.evidence[r].kind == "temporal_kinetics" for r in claim.supported_by if r in self.evidence),
                    independent_validation=any(
                        self.evidence[r].qualifies_as_external_validation
                        for r in claim.supported_by
                        if r in self.evidence
                    ),
                    reference_ground_truth=any(
                        self.evidence[r].is_reference_ground_truth
                        for r in claim.supported_by
                        if r in self.evidence
                    ),
                    cross_method_concordance=any(self.evidence[r].kind == "cross_method" for r in claim.supported_by if r in self.evidence),
                    causal_identification_status="BACKDOOR_SATISFIED" if any(self.evidence[r].kind == "causal_dag" for r in claim.supported_by if r in self.evidence) else "UNASSESSED",
                )

                w_result = DeterministicWarrantEngine.evaluate(claim_ir, ev_profile)
                claim.warrant_evaluation = w_result.to_dict()
                claim.structured_claim = claim_ir.to_dict()

                warrant_ceiling = w_result.evidence_ceiling
                if MATURITY_RANKS.get(warrant_ceiling, 0) < MATURITY_RANKS.get(min_maturity, 0):
                    min_maturity = warrant_ceiling
            except Exception:
                pass

        claim.evidence_status = min_maturity
        return claim.evidence_status

    # -- cryptographic seal (BNS-012/BNS-024) --------------------------------

    def compute_canonical_payload_sha256(self) -> str:
        """Calculate canonical SHA-256 digest of the claims and evidence in this ledger."""
        data = {
            "evidence": {rid: asdict(ref) for rid, ref in sorted(self.evidence.items())},
            "claims": {cid: c.to_dict() for cid, c in sorted(self.claims.items())},
        }
        return canonical_json_sha256(data)

    def seal(
        self,
        signer_name: str,
        signer_email: str,
        signing_reason: str = "SEAL_CLAIM_EVIDENCE_LEDGER",
        private_key: Optional[ed25519.Ed25519PrivateKey | str] = None,
        include_tsa_token: bool = True,
        tsa_private_key: Optional[ed25519.Ed25519PrivateKey] = None,
    ) -> Dict[str, Any]:
        """
        Seal content with Ed25519 and an optional local timestamp-shaped fixture.
        The embedded key and declared signer are not external identity evidence.
        """
        payload_sha256 = self.compute_canonical_payload_sha256()

        priv: ed25519.Ed25519PrivateKey
        is_ephemeral = False
        if isinstance(private_key, ed25519.Ed25519PrivateKey):
            priv = private_key
        elif isinstance(private_key, str) and private_key.strip():
            loaded = load_private_key_from_env(private_key)
            if loaded is None:
                try:
                    loaded = serialization.load_pem_private_key(private_key.encode("ascii"), password=None)
                except Exception:
                    pass
            if isinstance(loaded, ed25519.Ed25519PrivateKey):
                priv = loaded
            else:
                priv = ed25519.Ed25519PrivateKey.generate()
                is_ephemeral = True
        else:
            env_key = load_private_key_from_env("BIONEXUS_SIGNING_KEY")
            if env_key is not None:
                priv = env_key
            else:
                priv = ed25519.Ed25519PrivateKey.generate()
                is_ephemeral = True

        pub = priv.public_key()
        pub_pem = pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
        key_id = f"sha256:{hashlib.sha256(pub_pem.encode('ascii')).hexdigest()}"

        timestamp_iso = datetime.now(timezone.utc).isoformat()
        seal_id = f"seal_{abs(hash(payload_sha256)) % 1000000:06d}"

        seal_payload = canonical_json_bytes({
            "schema_version": "bionexus.claim-ledger-seal.v1",
            "seal_id": seal_id,
            "ledger_payload_sha256": payload_sha256,
            "signer_name": signer_name,
            "signer_email": signer_email,
            "signing_reason": signing_reason,
            "timestamp_utc": timestamp_iso,
            "public_key_pem": pub_pem,
            "key_id": key_id,
        })
        raw_sig = priv.sign(seal_payload)
        sig_b64 = base64.b64encode(raw_sig).decode("ascii")

        tsa_token = None
        if include_tsa_token:
            try:
                tsa_token = generate_tsa_timestamp_token(
                    study_id=seal_id,
                    raw_signature=raw_sig,
                    tsa_private_key=tsa_private_key,
                    timestamp_iso=timestamp_iso,
                )
            except Exception:
                tsa_token = None

        seal_dict = {
            "schema_version": "bionexus.claim-ledger-seal.v1",
            "seal_id": seal_id,
            "ledger_payload_sha256": payload_sha256,
            "signer_name": signer_name,
            "signer_email": signer_email,
            "signing_reason": signing_reason,
            "timestamp_utc": timestamp_iso,
            "public_key_pem": pub_pem,
            "key_id": key_id,
            "signature_algorithm": "ed25519",
            "signature_bytes_b64": sig_b64,
            "tsa_timestamp_token": tsa_token,
            "is_ephemeral_key": is_ephemeral,
        }
        self.cryptographic_seal = seal_dict
        return seal_dict

    def verify_seal(
        self,
        expected_public_key_pem: Optional[str] = None,
        tsa_public_key_pem: Optional[str] = None,
        *,
        require_tsa_token: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """Verify the cryptographic seal against current ledger contents."""
        if self.cryptographic_seal is None:
            return False, "Ledger has not been sealed with a cryptographic signature"

        seal = self.cryptographic_seal
        if not isinstance(seal, dict):
            return False, "Invalid ledger seal record"
        if seal.get("schema_version") != "bionexus.claim-ledger-seal.v1":
            return False, "Unsupported or missing ledger seal schema_version"
        if seal.get("signature_algorithm") != "ed25519":
            return False, "Unsupported or missing seal signature_algorithm"
        for name in ("seal_id", "ledger_payload_sha256", "signer_name", "signer_email",
                     "signing_reason", "timestamp_utc", "public_key_pem", "key_id", "signature_bytes_b64"):
            if not isinstance(seal.get(name), str) or not seal[name].strip():
                return False, f"Seal missing required field: {name}"
        try:
            if datetime.fromisoformat(seal["timestamp_utc"].replace("Z", "+00:00")).tzinfo is None:
                return False, "Seal timestamp must include a timezone"
        except ValueError:
            return False, "Invalid seal timestamp"
        current_hash = self.compute_canonical_payload_sha256()
        if seal.get("ledger_payload_sha256") != current_hash:
            return False, f"Ledger content modified after sealing: expected {seal.get('ledger_payload_sha256')}, actual {current_hash}"

        pub_pem = seal.get("public_key_pem", "")
        if not pub_pem:
            return False, "Seal missing public_key_pem"

        if expected_public_key_pem is not None and pub_pem.strip() != expected_public_key_pem.strip():
            return False, "Seal signer public key mismatch"
        if seal["key_id"] != "sha256:" + hashlib.sha256(pub_pem.encode("utf-8")).hexdigest():
            return False, "Seal key_id does not match public key"

        try:
            pubkey = serialization.load_pem_public_key(pub_pem.encode("ascii"))
            if not isinstance(pubkey, ed25519.Ed25519PublicKey):
                return False, f"Unsupported seal key type: {type(pubkey).__name__}"

            raw_sig = base64.b64decode(seal.get("signature_bytes_b64", ""), validate=True)
            seal_payload = canonical_json_bytes({
                "schema_version": seal.get("schema_version"),
                "seal_id": seal.get("seal_id"),
                "ledger_payload_sha256": seal.get("ledger_payload_sha256"),
                "signer_name": seal.get("signer_name"),
                "signer_email": seal.get("signer_email"),
                "signing_reason": seal.get("signing_reason"),
                "timestamp_utc": seal.get("timestamp_utc"),
                "public_key_pem": pub_pem,
                "key_id": seal.get("key_id"),
            })
            pubkey.verify(raw_sig, seal_payload)
        except InvalidSignature:
            return False, "Invalid seal digital signature: payload was tampered"
        except Exception as ex:
            return False, f"Seal verification error: {str(ex)}"

        if tsa_public_key_pem is not None or require_tsa_token:
            if not isinstance(seal.get("tsa_timestamp_token"), dict) or not seal["tsa_timestamp_token"]:
                return False, "Required TSA timestamp token is missing"
            if not tsa_public_key_pem:
                return False, "Required TSA verification needs an explicit public key"
            valid_tsa, tsa_errs = verify_tsa_timestamp_token(
                token=seal["tsa_timestamp_token"],
                raw_signature=raw_sig,
                tsa_public_key_pem=tsa_public_key_pem,
            )
            if not valid_tsa:
                return False, f"TSA timestamp verification failed: {'; '.join(tsa_errs)}"

        return True, None

    # -- serialization -------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "evidence": {rid: asdict(ref) for rid, ref in self.evidence.items()},
            "claims": {cid: c.to_dict() for cid, c in self.claims.items()},
        }
        if self.cryptographic_seal is not None:
            data["cryptographic_seal"] = self.cryptographic_seal
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClaimLedger":
        ledger = cls()
        for rid, ref in data.get("evidence", {}).items():
            if ref.get("ref_id") != rid:
                raise ValueError("Evidence dictionary key does not match ref_id")
            ledger.evidence[rid] = EvidenceRef(**ref)
        for cid, c in data.get("claims", {}).items():
            if c.get("claim_id") != cid:
                raise ValueError("Claim dictionary key does not match claim_id")
            ledger.claims[cid] = ClaimRecord(**c)
        ledger.cryptographic_seal = data.get("cryptographic_seal")
        return ledger

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return p

    @classmethod
    def load(cls, path: str | Path) -> "ClaimLedger":
        def unique_object(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
            obj: Dict[str, Any] = {}
            for key, value in pairs:
                if key in obj:
                    raise ValueError(f"Duplicate ledger JSON key: {key}")
                obj[key] = value
            return obj

        return cls.from_dict(json.loads(
            Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique_object,
        ))

    def to_jsonld(self) -> Dict[str, Any]:
        """
        PROV-O flavored JSON-LD projection (BNS-012 §4).

        Claims are prov:Entity entities wasDerivedFrom their dependencies and
        wasGeneratedBy the capability activity; evidence refs are entities.
        Deliberately minimal: one @context, plain node references, no
        external graph vocabulary beyond prov.
        """
        context = {
            "prov": "http://www.w3.org/ns/prov#",
            "bns": "https://bionexus.dev/ns#",
            "bns:evidenceStatus": {"@id": "bns:evidenceStatus"},
        }
        graph: List[Dict[str, Any]] = []

        for rid, ref in self.evidence.items():
            graph.append(
                {
                    "@id": f"bns:{rid}",
                    "@type": "prov:Entity",
                    "bns:evidenceKind": ref.kind,
                    "bns:summary": ref.summary,
                    "bns:maturity": ref.maturity,
                    "bns:validationRole": ref.validation_role,
                }
            )

        for cid, claim in self.claims.items():
            node: Dict[str, Any] = {
                "@id": f"bns:{cid}",
                "@type": ["prov:Entity", "bns:Claim"],
                "bns:statement": claim.statement,
                "bns:evidenceStatus": claim.evidence_status,
                "prov:wasDerivedFrom": [f"bns:{r}" for r in (*claim.supported_by, *claim.depends_on)],
            }
            if claim.capability_id:
                node["prov:wasGeneratedBy"] = f"bns:capability/{claim.capability_id}"
            if claim.contradicted_by:
                node["bns:contradictedBy"] = [f"bns:{r}" for r in claim.contradicted_by]
            graph.append(node)

        return {"@context": context, "@graph": graph}
