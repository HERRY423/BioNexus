"""Download public inputs only when missing; preserve and hash existing files."""
from pathlib import Path
import hashlib
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE96nnn/GSE96583/suppl/"
SPECS = {
    "GSE96583_RAW.tar": (ROOT / "data/flagship/kang2018_pbmc_ifnb", "e5d41a3248a813f99d68fd5c9eb9773de7f46a83680a67f4a02d683b8955fe80"),
    "GSE96583_batch2.total.tsne.df.tsv.gz": (ROOT / "data/flagship/kang2018_pbmc_ifnb", "1d57e72e92ca8695250e88cc0f1c3fa8c0be1175d974f8b427c58f1274dc6c09"),
    "GSE96583_batch2.genes.tsv.gz": (Path(__file__).parent, "93aa4e9b530ef9d6411ca129b416324c5cc1cc5a01a1fa6ed4f4a845480ed3ca"),
}

if __name__ == "__main__":
    for name, (folder, expected) in SPECS.items():
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        if not path.exists():
            temp = folder / (name + ".partial")
            if temp.exists():
                raise FileExistsError(f"Inspect prior partial download before retrying: {temp}")
            with urllib.request.urlopen(BASE + name, timeout=120) as response, temp.open("xb") as dest:
                while chunk := response.read(1024 * 1024):
                    dest.write(chunk)
            with temp.open("rb") as f:
                observed = hashlib.file_digest(f, "sha256").hexdigest()
            if observed != expected:
                raise ValueError(f"Downloaded content differs from frozen input: {temp}")
            temp.rename(path)
        with path.open("rb") as f:
            observed = hashlib.file_digest(f, "sha256").hexdigest()
        if observed != expected:
            raise ValueError(f"Existing input differs from frozen input: {path}")
        print(f"MATCH {name} {observed}")
