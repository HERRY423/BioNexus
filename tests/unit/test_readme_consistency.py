"""
README / docs honesty guards: marketing claims must not exceed the SSOT.

Validates:
1. Evidence grades advertised in the README skill table never exceed the grades
   recorded in the canonical `bionexus.registry.yaml` SSOT (no Grade-A
   marketing for Grade-C heuristic skills), and every canonical/heuristic
   skill is represented in the table.
2. Any Python version marked "Primary Active" in `docs/compatibility-matrix.md`
   must actually appear in the CI test matrix (`.github/workflows/ci.yml`).
3. README must not cite unverifiable static score badges (e.g. a hardcoded CRI
   percentage that no CI job produces).
"""

import re
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_README = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
_REGISTRY = yaml.safe_load((_REPO_ROOT / "bionexus.registry.yaml").read_text(encoding="utf-8"))
_COMPAT = (_REPO_ROOT / "docs" / "compatibility-matrix.md").read_text(encoding="utf-8")
_CI = yaml.safe_load((_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))

# Higher rank = stronger claim. README may claim at most the SSOT rank.
_GRADE_RANK = {"A": 3, "B": 2, "C": 1, "refuse": 1}


def _registry_skill_grades():
    """name -> registry grade for canonical + heuristic skills (SSOT).

    Grade 'outline' entries (start, scientific-problem-selection, ...) are
    session/orientation skills rather than analytical claims and are exempt
    from the README completeness requirement.
    """
    skills = _REGISTRY.get("skills", {})
    graded = {}
    for section in ("canonical", "heuristics"):
        for entry in skills.get(section, []) or []:
            grade = str(entry.get("grade", "")).strip()
            if grade and grade != "outline":
                graded[entry["name"]] = grade
    return graded


def _readme_skill_rows():
    """[(skill_name, [claimed grade letters])] parsed from the README skill table."""
    pattern = re.compile(
        r"^\|\s*\[`([a-z0-9-]+)`\]\([^)]*\)\s*\|[^|]+\|\s*\*\*Grade\s+([A-C](?:\s*/\s*[A-C])*)\*\*",
        re.MULTILINE,
    )
    return [(m.group(1), [g.strip() for g in m.group(2).split("/")]) for m in pattern.finditer(_README)]


def test_readme_skill_table_matches_registry_ssot():
    """README grade claims must not overclaim the registry SSOT grades."""
    registry = _registry_skill_grades()
    assert registry, "registry SSOT must define canonical + heuristic skills"

    rows = _readme_skill_rows()
    assert rows, "README skill table must be parseable"
    readme_names = {name for name, _ in rows}
    missing = sorted(set(registry) - readme_names)
    assert not missing, f"Skills missing from README table: {missing}"

    for name, claimed_letters in rows:
        reg_grade = registry.get(name)
        assert reg_grade is not None, f"README lists unknown skill '{name}' not in registry SSOT"
        reg_rank = _GRADE_RANK.get(reg_grade)
        assert reg_rank is not None, f"Registry grade '{reg_grade}' for '{name}' not rankable"
        for letter in claimed_letters:
            claimed_rank = _GRADE_RANK[letter]
            assert claimed_rank <= reg_rank, (
                f"README overclaims '{name}': advertises Grade {letter} but registry SSOT says "
                f"Grade {reg_grade}. Align the README to bionexus.registry.yaml (or fix the SSOT)."
            )


def test_readme_does_not_cite_unverifiable_static_scores():
    """README must not carry static score numbers that no CI job produces."""
    # The eval CRI is environment-dependent and must be cited from a generated
    # report, never hardcoded in a badge or feature list.
    assert not re.search(r"CRI[^\n]{0,24}\d{1,3}\.\d\s*%", _README), (
        "README cites a hardcoded CRI percentage; cite the generated report instead "
        "(evals/reports/benchmark_report.md)."
    )
    # Test counts drift with the suite; badge must not pin a stale number.
    assert not re.search(r"Tests-\d+\+?\s*Passed", _README), (
        "README badge pins a static test-pass count; remove the number or generate it in CI."
    )


def test_primary_active_python_versions_exist_in_ci_matrix():
    """Any 'Primary Active' Python claim must be covered by the CI test matrix."""
    ci_versions = set()
    for job in (_CI.get("jobs") or {}).values():
        matrix = job.get("strategy", {}).get("matrix") or {}
        for pv in matrix.get("python-version", []) or []:
            ci_versions.add(str(pv))

    assert ci_versions, "CI test matrix must declare python-version entries"

    for line in _COMPAT.splitlines():
        if "Primary Active" in line:
            m = re.search(r"\*\*Python\s+(\d+\.\d+)\*\*", line)
            assert m, f"Unparseable Primary Active row: {line}"
            assert m.group(1) in ci_versions, (
                f"compatibility-matrix.md marks Python {m.group(1)} as 'Primary Active' but the CI "
                f"matrix only covers {sorted(ci_versions)}. Add it to ci.yml or downgrade the claim."
            )
