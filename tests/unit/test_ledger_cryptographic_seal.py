"""Unit tests for ClaimLedger cryptographic sealing and verification (BNS-012/BNS-024)."""

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from bionexus.ledger import ClaimLedger, ClaimRecord, EvidenceRef


def test_claim_ledger_seal_and_verify(tmp_path: Path):
    ledger = ClaimLedger()
    ledger.add_evidence(
        EvidenceRef(
            ref_id="DS-001",
            kind="dataset",
            summary="PBMC single cell RNA-seq dataset",
            maturity="ROBUST",
        )
    )
    ledger.add_claim(
        ClaimRecord(
            claim_id="CLAIM-001",
            statement="CD8 T cells are associated with response",
            supported_by=["DS-001"],
            evidence_status="SUPPORTED",
        )
    )

    # Generate test keypairs
    signer_priv = ed25519.Ed25519PrivateKey.generate()
    signer_pub_pem = signer_priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")

    tsa_priv = ed25519.Ed25519PrivateKey.generate()
    tsa_pub_pem = tsa_priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")

    # Seal ledger
    seal = ledger.seal(
        signer_name="Dr. Principal Investigator",
        signer_email="pi@stanford.edu",
        signing_reason="PRE_SUBMISSION_EVIDENCE_LOCK",
        private_key=signer_priv,
        tsa_private_key=tsa_priv,
    )

    assert seal["schema_version"] == "bionexus.claim-ledger-seal.v1"
    assert seal["signer_email"] == "pi@stanford.edu"
    assert seal["signature_algorithm"] == "ed25519"
    assert len(seal["signature_bytes_b64"]) > 0
    assert seal["tsa_timestamp_token"] is not None

    # Verify seal
    valid, reason = ledger.verify_seal(
        expected_public_key_pem=signer_pub_pem,
        tsa_public_key_pem=tsa_pub_pem,
    )
    assert valid is True
    assert reason is None

    # Test round-trip save and load with seal intact
    save_file = tmp_path / "sealed_ledger.json"
    ledger.save(save_file)

    loaded_ledger = ClaimLedger.load(save_file)
    assert loaded_ledger.cryptographic_seal is not None
    valid_loaded, reason_loaded = loaded_ledger.verify_seal(
        expected_public_key_pem=signer_pub_pem,
        tsa_public_key_pem=tsa_pub_pem,
    )
    assert valid_loaded is True
    assert reason_loaded is None

    # Test tamper resistance: modifying evidence invalidates seal
    loaded_ledger.evidence["DS-001"].maturity = "REPLICATED"
    valid_tampered, reason_tampered = loaded_ledger.verify_seal(
        expected_public_key_pem=signer_pub_pem,
    )
    assert valid_tampered is False
    assert "Ledger content modified after sealing" in reason_tampered


def test_claim_ledger_seal_wrong_key_rejected():
    ledger = ClaimLedger()
    ledger.add_evidence(
        EvidenceRef(ref_id="EV-01", kind="method_run", summary="run1")
    )
    signer_priv = ed25519.Ed25519PrivateKey.generate()
    ledger.seal("Signer", "signer@lab.org", private_key=signer_priv)

    wrong_priv = ed25519.Ed25519PrivateKey.generate()
    wrong_pub_pem = wrong_priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")

    valid, reason = ledger.verify_seal(expected_public_key_pem=wrong_pub_pem)
    assert valid is False
    assert "Seal signer public key mismatch" in reason
