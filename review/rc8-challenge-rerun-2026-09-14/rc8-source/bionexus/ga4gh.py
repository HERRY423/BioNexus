"""
BioNexus GA4GH Standards Module (BNS-016 §GA4GH).

Provides native implementations for:
1. GA4GH Data Repository Service (DRS) v1.2.0:
   - Content-based addressable data objects across local/multi-cloud genomics.
   - SHA-256 and MD5 checksum integrity seals.
   - Access methods for POSIX file, S3, GCS, and HTTPS endpoints.
2. GA4GH Phenopackets v2:
   - High-integrity clinical and phenotypic donor characterization.
   - Standardized mappings to Human Phenotype Ontology (HPO), MONDO, and NCIT.
   - Fail-closed validation for CURIE identifiers, donor IDs, and controlled sex vocabularies.
"""

from __future__ import annotations

import datetime
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# ==============================================================================
# GA4GH DRS (Data Repository Service) v1.2.0
# ==============================================================================

VALID_CHECKSUM_TYPES = ("sha-256", "md5", "sha-512", "etag")
VALID_ACCESS_TYPES = ("file", "s3", "gs", "https", "ftp")
CURIE_REGEX = re.compile(r"^[A-Za-z0-9_\-\.]+:[A-Za-z0-9_\-\./#]+$")


@dataclass(frozen=True)
class DRSChecksum:
    """Cryptographic hash for DRS object integrity verification."""

    type: str
    checksum: str

    def __post_init__(self) -> None:
        c_type = self.type.lower()
        if c_type not in VALID_CHECKSUM_TYPES:
            raise ValueError(f"Invalid checksum type '{self.type}'. Must be one of {VALID_CHECKSUM_TYPES}")
        if not re.match(r"^[a-fA-F0-9]+$", self.checksum):
            raise ValueError(f"Checksum '{self.checksum}' is not a valid hex digest.")
        if c_type == "sha-256" and len(self.checksum) != 64:
            raise ValueError(f"sha-256 checksum must be 64 hex characters (got {len(self.checksum)}).")
        if c_type == "md5" and len(self.checksum) != 32:
            raise ValueError(f"md5 checksum must be 32 hex characters (got {len(self.checksum)}).")

    def to_dict(self) -> Dict[str, str]:
        return {"type": self.type.lower(), "checksum": self.checksum.lower()}


@dataclass(frozen=True)
class DRSAccessURL:
    """Direct URL and optional headers to retrieve object bytes."""

    url: str
    headers: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"url": self.url}
        if self.headers:
            d["headers"] = dict(self.headers)
        return d


@dataclass(frozen=True)
class DRSAccessMethod:
    """Protocol-specific access mechanism to fetch bytes for a DRS object."""

    type: str
    access_url: Optional[DRSAccessURL] = None
    access_id: Optional[str] = None
    region: Optional[str] = None

    def __post_init__(self) -> None:
        m_type = self.type.lower()
        if m_type not in VALID_ACCESS_TYPES:
            raise ValueError(f"Invalid access method type '{self.type}'. Must be one of {VALID_ACCESS_TYPES}")
        if not self.access_url and not self.access_id:
            raise ValueError("DRSAccessMethod requires either access_url or access_id.")

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"type": self.type.lower()}
        if self.access_url:
            d["access_url"] = self.access_url.to_dict()
        if self.access_id:
            d["access_id"] = self.access_id
        if self.region:
            d["region"] = self.region
        return d


@dataclass
class DRSObject:
    """Canonical GA4GH DRS Object (v1.2.0)."""

    id: str
    name: str
    self_uri: str
    size: int
    created_time: str
    updated_time: str
    version: str = "v1"
    mime_type: Optional[str] = None
    checksums: List[DRSChecksum] = field(default_factory=list)
    access_methods: List[DRSAccessMethod] = field(default_factory=list)
    description: Optional[str] = None
    aliases: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id or not isinstance(self.id, str):
            raise ValueError("DRSObject id must be a non-empty string.")
        if self.size < 0:
            raise ValueError(f"DRSObject size cannot be negative ({self.size}).")
        if not self.self_uri.startswith("drs://"):
            raise ValueError(f"DRS self_uri must start with 'drs://' (got '{self.self_uri}').")
        if not self.checksums:
            raise ValueError("DRSObject must contain at least one cryptographic checksum.")

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "self_uri": self.self_uri,
            "size": self.size,
            "created_time": self.created_time,
            "updated_time": self.updated_time,
            "version": self.version,
            "checksums": [c.to_dict() for c in self.checksums],
            "access_methods": [m.to_dict() for m in self.access_methods],
        }
        if self.mime_type:
            d["mime_type"] = self.mime_type
        if self.description:
            d["description"] = self.description
        if self.aliases:
            d["aliases"] = list(self.aliases)
        return d


def create_drs_object(
    file_path: Union[Path, str],
    drs_id: str,
    authority: str = "bionexus.local",
    name: Optional[str] = None,
    mime_type: Optional[str] = None,
    access_methods: Optional[List[DRSAccessMethod]] = None,
    description: Optional[str] = None,
    aliases: Optional[List[str]] = None,
) -> DRSObject:
    """Create a verified GA4GH DRS Object from an on-disk file.

    Fail-closed: file must exist, and SHA-256 / MD5 checksums are computed from bytes.
    """
    p = Path(file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"Cannot create DRS object for non-existent file: {p}")

    size = p.stat().st_size
    mtime = datetime.datetime.fromtimestamp(p.stat().st_mtime, tz=datetime.timezone.utc).isoformat()
    ctime = datetime.datetime.fromtimestamp(p.stat().st_ctime, tz=datetime.timezone.utc).isoformat()

    sha256 = hashlib.sha256()
    md5 = hashlib.md5()
    with open(p, "rb") as f:
        while chunk := f.read(1024 * 1024):
            sha256.update(chunk)
            md5.update(chunk)

    checksums = [
        DRSChecksum(type="sha-256", checksum=sha256.hexdigest()),
        DRSChecksum(type="md5", checksum=md5.hexdigest()),
    ]

    methods = list(access_methods) if access_methods else []
    if not methods:
        file_uri = p.as_uri()
        methods.append(
            DRSAccessMethod(
                type="file",
                access_url=DRSAccessURL(url=file_uri),
            )
        )

    clean_id = drs_id.strip()
    self_uri = f"drs://{authority}/{clean_id}"

    return DRSObject(
        id=clean_id,
        name=name or p.name,
        self_uri=self_uri,
        size=size,
        created_time=ctime,
        updated_time=mtime,
        mime_type=mime_type or "application/octet-stream",
        checksums=checksums,
        access_methods=methods,
        description=description or f"BioNexus DRS data object for {p.name}",
        aliases=aliases or [p.name],
    )


# ==============================================================================
# GA4GH Phenopackets v2
# ==============================================================================

VALID_SEXES = ("UNKNOWN_SEX", "FEMALE", "MALE", "OTHER_SEX")
DEFAULT_TAXONOMY = {"id": "NCBITaxon:9606", "label": "Homo sapiens"}


@dataclass(frozen=True)
class OntologyClass:
    """Ontology term identifier and label adhering to CURIE format."""

    id: str
    label: str

    def __post_init__(self) -> None:
        if not self.id or not isinstance(self.id, str):
            raise ValueError("OntologyClass id must be a non-empty string.")
        if not CURIE_REGEX.match(self.id):
            raise ValueError(f"OntologyClass id '{self.id}' does not match standard CURIE pattern (e.g. 'HP:0001250').")
        if not self.label:
            raise ValueError("OntologyClass label must be provided.")

    def to_dict(self) -> Dict[str, str]:
        return {"id": self.id, "label": self.label}


@dataclass
class PhenotypicFeature:
    """A phenotypic observation or absence (HPO-backed)."""

    type: OntologyClass
    excluded: bool = False
    onset: Optional[str] = None
    evidence: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "type": self.type.to_dict(),
            "excluded": self.excluded,
        }
        if self.onset:
            d["onset"] = {"ontology_class": {"id": self.onset, "label": self.onset}}
        if self.evidence:
            d["evidence"] = self.evidence
        return d


@dataclass
class Disease:
    """A diagnosed disease or condition (MONDO-backed)."""

    term: OntologyClass
    onset: Optional[str] = None
    clinical_stage: List[OntologyClass] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"term": self.term.to_dict()}
        if self.onset:
            d["onset"] = {"ontology_class": {"id": self.onset, "label": self.onset}}
        if self.clinical_stage:
            d["clinical_stage"] = [cs.to_dict() for cs in self.clinical_stage]
        return d


@dataclass
class Individual:
    """Individual subject / donor in a Phenopacket."""

    id: str
    alternate_ids: List[str] = field(default_factory=list)
    date_of_birth: Optional[str] = None
    sex: str = "UNKNOWN_SEX"
    karyotypic_sex: Optional[str] = None
    taxonomy: OntologyClass = field(default_factory=lambda: OntologyClass(id="NCBITaxon:9606", label="Homo sapiens"))

    def __post_init__(self) -> None:
        if not self.id or not isinstance(self.id, str):
            raise ValueError("Individual id must be a non-empty string.")
        if self.sex not in VALID_SEXES:
            raise ValueError(f"Invalid sex '{self.sex}'. Must be one of {VALID_SEXES}")

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": self.id,
            "sex": self.sex,
            "taxonomy": self.taxonomy.to_dict(),
        }
        if self.alternate_ids:
            d["alternate_ids"] = list(self.alternate_ids)
        if self.date_of_birth:
            d["date_of_birth"] = self.date_of_birth
        if self.karyotypic_sex:
            d["karyotypic_sex"] = self.karyotypic_sex
        return d


@dataclass
class MetaData:
    """Metadata describing the origin, ontologies, and schema version."""

    created: str
    created_by: str
    submitted_by: Optional[str] = None
    resources: List[Dict[str, Any]] = field(default_factory=list)
    phenopacket_schema_version: str = "2.0"

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "created": self.created,
            "created_by": self.created_by,
            "phenopacket_schema_version": self.phenopacket_schema_version,
            "resources": self.resources,
        }
        if self.submitted_by:
            d["submitted_by"] = self.submitted_by
        return d


@dataclass
class Phenopacket:
    """GA4GH Phenopackets v2 root document."""

    id: str
    subject: Individual
    phenotypic_features: List[PhenotypicFeature] = field(default_factory=list)
    diseases: List[Disease] = field(default_factory=list)
    meta_data: MetaData = field(
        default_factory=lambda: MetaData(
            created=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            created_by="BioNexus",
            resources=_default_phenopacket_resources(),
        )
    )
    measurements: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id or not isinstance(self.id, str):
            raise ValueError("Phenopacket id must be a non-empty string.")

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": self.id,
            "subject": self.subject.to_dict(),
            "phenotypic_features": [f.to_dict() for f in self.phenotypic_features],
            "diseases": [dis.to_dict() for dis in self.diseases],
            "meta_data": self.meta_data.to_dict(),
        }
        if self.measurements:
            d["measurements"] = self.measurements
        return d


def _default_phenopacket_resources() -> List[Dict[str, Any]]:
    return [
        {
            "id": "hp",
            "name": "Human Phenotype Ontology",
            "url": "http://purl.obolibrary.org/obo/hp.owl",
            "version": "2024-04-26",
            "namespace_prefix": "HP",
            "iri_prefix": "http://purl.obolibrary.org/obo/HP_",
        },
        {
            "id": "mondo",
            "name": "Mondo Disease Ontology",
            "url": "http://purl.obolibrary.org/obo/mondo.owl",
            "version": "2024-05-01",
            "namespace_prefix": "MONDO",
            "iri_prefix": "http://purl.obolibrary.org/obo/MONDO_",
        },
        {
            "id": "ncbitaxon",
            "name": "NCBI organismal classification",
            "url": "http://purl.obolibrary.org/obo/ncbitaxon.owl",
            "version": "2024-01-01",
            "namespace_prefix": "NCBITaxon",
            "iri_prefix": "http://purl.obolibrary.org/obo/NCBITaxon_",
        },
    ]


def export_donor_phenopacket(
    donor_id: str,
    sex: str = "UNKNOWN_SEX",
    disease_terms: Optional[List[Dict[str, str]]] = None,
    phenotype_terms: Optional[List[Dict[str, str]]] = None,
    measurements: Optional[List[Dict[str, Any]]] = None,
    meta_created_by: str = "BioNexus",
) -> Phenopacket:
    """Generate a valid GA4GH Phenopacket v2 document for a clinical study donor.

    Fail-closed: validates donor_id, sex controlled vocabulary, and CURIE identifiers.
    """
    if not donor_id or not donor_id.strip():
        raise ValueError("donor_id cannot be empty")

    ind = Individual(id=donor_id.strip(), sex=sex)

    diseases: List[Disease] = []
    if disease_terms:
        for dt in disease_terms:
            c_id = dt.get("id", "")
            c_lbl = dt.get("label", "")
            diseases.append(Disease(term=OntologyClass(id=c_id, label=c_lbl)))

    features: List[PhenotypicFeature] = []
    if phenotype_terms:
        for pt in phenotype_terms:
            c_id = pt.get("id", "")
            c_lbl = pt.get("label", "")
            excluded = bool(pt.get("excluded", False))
            features.append(PhenotypicFeature(type=OntologyClass(id=c_id, label=c_lbl), excluded=excluded))

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    meta = MetaData(
        created=now,
        created_by=meta_created_by,
        resources=_default_phenopacket_resources(),
        phenopacket_schema_version="2.0",
    )

    return Phenopacket(
        id=f"phenopacket_{donor_id.strip()}",
        subject=ind,
        phenotypic_features=features,
        diseases=diseases,
        meta_data=meta,
        measurements=measurements or [],
    )
