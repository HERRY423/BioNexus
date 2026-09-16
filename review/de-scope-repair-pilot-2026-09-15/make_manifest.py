"""Write a SHA-256 manifest for the completed remediation package."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "ARTIFACT_MANIFEST-FINAL.json"


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"refusing to overwrite {OUTPUT}")
    files = {}
    for path in sorted(HERE.rglob("*")):
        if not path.is_file() or path == OUTPUT or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        files[path.relative_to(HERE).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    aggregate = hashlib.sha256(
        "\n".join(f"{name} {files[name]}" for name in sorted(files)).encode()
    ).hexdigest()
    payload = {
        "schema": "bionexus.de-remediation-artifact-manifest.v1",
        "file_count": len(files),
        "aggregate_sha256": aggregate,
        "files": files,
        "evidence_ceiling": "LOCAL_DEVELOPER_LABELLED_REGRESSION_ONLY",
        "scientific_authorization": "NONE",
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("file_count", "aggregate_sha256")}, indent=2))


if __name__ == "__main__":
    main()
