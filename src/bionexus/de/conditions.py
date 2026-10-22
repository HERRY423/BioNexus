"""Executable, artifact-bound necessary conditions for narrowly specified DE claims.

No code in an evidence package is executed. Positive results establish only the
listed checks over supplied bytes, never authenticity, model adequacy or biology.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path, PureWindowsPath
from typing import Any

import jsonschema
import numpy as np
import pandas as pd

VERSION = "bionexus.de-claim-conditions.v1"
SAT = "SATISFIED"
UNSAT = "UNSATISFIED"
CONFLICT = "CONFLICT"
UNKNOWN = "NOT_ASSESSED"
ARTIFACT = "ARTIFACT_EXTRACTED"
RECORD = "EXTERNAL_RECORD_CHECKED"
DECLARED = "RESEARCHER_DECLARED"
MISSING = "MISSING"
SCOPES = ("table_observation", "cohort_association", "population_effect", "causal_effect")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _json(data: bytes) -> dict[str, Any]:
    def reject(value: str) -> None:
        raise ValueError(f"Non-finite JSON number: {value}")
    value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_object, parse_constant=reject)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _table(data: bytes, path: str) -> pd.DataFrame:
    delimiter = "\t" if Path(path).suffix.lower() == ".tsv" else ","
    text = data.decode("utf-8-sig")
    header = next(csv.reader(io.StringIO(text), delimiter=delimiter), [])
    if not header or len(set(header)) != len(header) or any(not x.strip() for x in header):
        raise ValueError("Missing or duplicate table columns")
    return pd.read_csv(io.StringIO(text), sep=delimiter, dtype=str, keep_default_na=False)


def _check(key: str, requirement: str, source: str, status: str, method: str,
           refs: list[dict[str, str]], observed: Any = None, *, coverage: str = "",
           repair: str = "") -> dict[str, Any]:
    return dict(condition_id=key, requirement=requirement, source=source, status=status,
                method=method, evidence_refs=refs, observed=observed, coverage=coverage, repair=repair)


def _status(checks: list[dict[str, Any]]) -> str:
    values = {c["status"] for c in checks}
    for state in (CONFLICT, UNSAT, UNKNOWN):
        if state in values:
            return state
    return SAT if checks else UNKNOWN


def _load_artifact(root: Path, role: str, spec: dict[str, str] | None,
                   pinned: Any = None) -> tuple[Any, dict[str, Any]]:
    requirement = f"Supply and bind the exact {role} artifact bytes."
    if spec is None:
        return None, _check(f"artifact_{role}", requirement, MISSING, UNKNOWN, "SHA-256", [],
                            repair=f"Export {role} and its SHA-256 in the contract.")
    ref = {"artifact": role, **spec}
    path = (root / spec["path"]).resolve()
    # Packages are portable; referenced paths cannot silently read arbitrary files.
    if (Path(spec["path"]).is_absolute() or PureWindowsPath(spec["path"]).drive
            or "\\" in spec["path"] or not path.is_relative_to(root)):
        return None, _check(f"artifact_{role}", requirement, RECORD, CONFLICT, "path containment", [ref],
                            repair="Use a relative artifact path inside the contract directory.")
    try:
        data = path.read_bytes()
    except OSError:
        return None, _check(f"artifact_{role}", requirement, MISSING, UNKNOWN, "read bytes", [ref],
                            repair="Supply the referenced readable file.")
    valid = _digest(data) == spec["sha256"]
    if pinned is not None:
        # Do not combine separately supplied audit inputs with a different package.
        valid = valid and isinstance(pinned, (str, Path)) and Path(pinned).read_bytes() == data
    if not valid:
        return None, _check(f"artifact_{role}", requirement, RECORD, CONFLICT, "SHA-256 and input equality",
                            [ref], {"actual_sha256": _digest(data)}, repair="Resolve the mismatched artifacts and rerun.")
    try:
        value = _json(data) if role == "model" else _table(data, spec["path"])
    except (ValueError, UnicodeError, pd.errors.ParserError) as exc:
        return None, _check(f"artifact_{role}", requirement, ARTIFACT, UNKNOWN, "parse exact bytes", [ref],
                            str(exc), repair="Export a valid, unambiguous artifact.")
    return value, _check(f"artifact_{role}", requirement, RECORD, SAT, "SHA-256 and parse exact bytes", [ref],
                         {"sha256": _digest(data)}, coverage="Byte identity only; producer and execution unauthenticated.")


def contrast_diagnostics(matrix: np.ndarray, contrast: np.ndarray) -> dict[str, Any]:
    """Test c in row(X) by SVD, retaining rank, tolerance and projection residual."""
    x, c = np.asarray(matrix, dtype=float), np.asarray(contrast, dtype=float)
    if x.ndim != 2 or not all(x.shape) or c.shape != (x.shape[1],):
        raise ValueError("Design/contrast dimensions do not match")
    if not np.isfinite(x).all() or not np.isfinite(c).all() or not np.any(c):
        raise ValueError("Design and nonzero contrast must be finite")
    # Column scaling avoids measuring numerical rank in arbitrary covariate units.
    scales = np.max(np.abs(x), axis=0)
    scales[scales == 0] = 1
    z = x / scales
    norms = np.linalg.norm(z, axis=0)
    norms[norms == 0] = 1
    z = z / norms
    with np.errstate(over="ignore", under="ignore", invalid="ignore", divide="ignore"):
        d = (c / np.max(np.abs(c))) / scales / norms
    if not np.isfinite(d).all() or not np.any(d):
        raise ValueError("Contrast scaling exceeds numeric range; rescale covariates and review")
    d = d / np.max(np.abs(d))
    _, singular, vt = np.linalg.svd(z, full_matrices=False)
    tolerance = max(z.shape) * np.finfo(float).eps * singular[0]
    rank = int(np.sum(singular > tolerance))
    basis = vt[:rank]
    residual = float(np.linalg.norm(d - basis.T @ (basis @ d)) / np.linalg.norm(d))
    return dict(rank=rank, columns=x.shape[1], rows=x.shape[0], residual_df=x.shape[0] - rank,
                full_rank=rank == x.shape[1], estimable=residual <= 1e-8,
                projection_residual=residual, estimability_tolerance=1e-8,
                rank_tolerance=float(tolerance), column_scaling="L2 norm")


def _design_checks(contract: dict[str, Any], model: Any, metadata: Any, design: Any,
                   refs: list[dict[str, str]]) -> list[dict[str, Any]]:
    requirements = {
        "model_binding": "Model record binds result, metadata, design, formula, cell set and contrast.",
        "sample_alignment": "Every model row maps uniquely to the declared sample and donor.",
        "design_encoding": "Actual matrix equals the declared additive model encoded from sample metadata.",
        "contrast_identity": "Numeric contrast estimates numerator minus denominator, with nuisance terms zero.",
        "contrast_estimability": "Target contrast lies in the row space of the actual design matrix.",
        "model_rank": "Supported fixed-effect model is full rank with positive residual degrees of freedom.",
        "statistical_unit": "Model rows account for donor repetition under the supported design.",
    }
    checks = {key: _check(key, req, MISSING, UNKNOWN, "not run; dependencies missing", refs,
                         repair="Supply a bound model, numeric design and sample-level metadata.")
              for key, req in requirements.items()}

    def put(key: str, status: str, method: str, observed: Any, repair: str = "") -> None:
        checks[key] = _check(key, requirements[key], RECORD if key == "model_binding" else ARTIFACT,
                             status, method, refs, observed, coverage="Supplied artifacts only.", repair=repair)

    if not isinstance(model, dict):
        return list(checks.values())
    try:
        jsonschema.validate(model, _schema()["$defs"]["model"])
    except jsonschema.ValidationError as exc:
        put("model_binding", UNKNOWN, "model schema", exc.message, "Export the supported model record schema.")
        return list(checks.values())
    analysis = contract["analysis"]
    if any(role not in contract["artifacts"] for role in ("results", "metadata", "design")):
        put("model_binding", UNKNOWN, "required artifact references", None,
            "Supply result, metadata and design references before comparing the model binding.")
        return list(checks.values())
    matches = all(model["artifact_sha256"].get(role) == contract["artifacts"].get(role, {}).get("sha256")
                  for role in ("results", "metadata", "design"))
    matches = matches and all(model[key] == analysis[key] for key in ("cell_type", "numerator", "denominator"))
    matches = matches and model["effect_measure"] == "log2_fold_change" and model["fit_status"] == "converged"
    put("model_binding", SAT if matches else CONFLICT, "cross-check model record and artifact digests",
        {key: model[key] for key in ("formula", "fit_status", "cell_type", "numerator", "denominator")},
        "Resolve record/claim mismatches; a declared successful fit alone cannot validate results.")
    if metadata is None or design is None:
        return list(checks.values())
    cols = contract["metadata_columns"]
    sid, donor, condition = (cols[key] for key in ("sample", "donor", "condition"))
    needed = {sid, donor, condition}
    if not needed <= set(metadata.columns) or "sample_id" not in design:
        put("sample_alignment", UNKNOWN, "required columns", sorted(needed), "Export sample, donor and condition columns.")
        return list(checks.values())
    aligned = (not metadata.empty and not metadata[list(needed)].eq("").any().any()
               and metadata[sid].is_unique and design["sample_id"].is_unique
               and set(metadata[sid]) == set(design["sample_id"]))
    put("sample_alignment", SAT if aligned else CONFLICT, "sample-ID bijection; align by ID, never by row position",
        {"metadata_rows": len(metadata), "design_rows": len(design)}, "Resolve duplicate, missing or extra sample IDs.")
    if not aligned:
        return list(checks.values())
    metadata = metadata.set_index(sid, drop=False).loc[design["sample_id"]]
    names, encodings = model["design_columns"], model["encodings"]
    if len(set(names)) != len(names) or set(design.columns) != {"sample_id", *names}:
        put("design_encoding", CONFLICT, "exact design column set", names, "Resolve actual and recorded columns.")
        return list(checks.values())
    try:
        x = design[names].to_numpy(dtype=float)
        c = np.array([model["contrast"][name] for name in names], dtype=float)
        diag = contrast_diagnostics(x, c)
    except (ValueError, KeyError, np.linalg.LinAlgError) as exc:
        put("contrast_estimability", UNKNOWN, "finite numeric matrix and contrast", str(exc), "Supply finite matching values.")
        return list(checks.values())
    put("contrast_estimability", SAT if diag["estimable"] else UNSAT, "SVD row-space projection", diag,
        "Redesign the confounded comparison or narrow the estimand; flags cannot repair non-estimability.")
    put("model_rank", SAT if diag["full_rank"] and diag["residual_df"] > 0 else UNSAT,
        "SVD rank and n-rank(X)", diag, "Resolve aliased columns or lack of residual degrees of freedom.")
    # Only explicit additive treatment coding is supported. Formula strings are never evaluated.
    formula = model["formula"].replace(" ", "")
    fields = {e["column"] for e in encodings.values() if e["kind"] != "intercept"}
    expected_formula = "~" + "+".join(["1", *sorted(fields)])
    formula_terms = formula[1:].split("+") if formula.startswith("~") else []
    supported = (len(formula_terms) == len(set(formula_terms))
                 and set(formula_terms) == {"1", *fields} and set(encodings) == set(names)
                 and sum(e["kind"] == "intercept" for e in encodings.values()) == 1
                 and set(model["contrast"]) == set(names))
    expected_cols, target = [], []
    try:
        for name in names:
            enc = encodings[name]
            if enc["kind"] == "intercept":
                expected_cols.append(np.ones(len(metadata)))
                target.append(0.)
            else:
                field = enc["column"]
                if metadata[field].eq("").any():
                    raise ValueError("Missing modeled covariate")
                if enc["kind"] == "numeric":
                    expected_cols.append(metadata[field].to_numpy(dtype=float))
                    target.append(0.)
                    supported = supported and field not in (condition, donor)
                else:
                    expected_cols.append((metadata[field] == enc["level"]).to_numpy(dtype=float))
                    target.append(float(enc["level"] == analysis["numerator"])
                                  - float(enc["level"] == analysis["denominator"]) if field == condition else 0.)
        # Every categorical factor uses exactly k-1 unique indicators from its observed levels.
        for field in fields:
            factor = [e for e in encodings.values() if e.get("column") == field]
            if any(e["kind"] == "categorical" for e in factor):
                levels = [e.get("level") for e in factor]
                observed = set(metadata[field])
                supported = supported and (all(e["kind"] == "categorical" for e in factor)
                    and len(levels) == len(set(levels)) == len(observed) - 1 and set(levels) < observed)
            else:
                supported = supported and len(factor) == 1
        encoded = np.column_stack(expected_cols)
        supported = supported and np.isfinite(encoded).all() and condition in fields
    except (KeyError, ValueError, TypeError):
        supported = False
        encoded = np.zeros_like(x)
    put("design_encoding", (SAT if np.allclose(x, encoded, rtol=1e-10, atol=1e-12) else CONFLICT)
        if supported else UNKNOWN, "rebuild supported additive treatment coding from metadata",
        {"formula": model["formula"], "supported_formula_shape": expected_formula},
        "Export explicit intercept plus additive numeric/categorical encodings; interactions and random effects need an adapter.")
    target_ok = (supported and np.any(target) and np.allclose(c, target, rtol=0, atol=1e-12)
                 and set(metadata[condition]) == {analysis["numerator"], analysis["denominator"]})
    put("contrast_identity", SAT if target_ok else (CONFLICT if supported else UNKNOWN),
        "derive condition contrast from factor encoding", {"recorded": c.tolist(), "expected": target},
        "Use the requested numerator-minus-denominator contrast with zero nuisance weights.")
    repeated = metadata[donor].duplicated().any()
    unit = model["statistical_unit"]
    paired = metadata.groupby(donor)[condition].agg(list)
    complete_pairs = all(len(v) == 2 and set(v) == {analysis["numerator"], analysis["denominator"]} for v in paired)
    unit_ok = ((unit == "independent_donor" and not repeated)
               or (unit == "paired_donor_fixed_effect" and complete_pairs and donor in fields and supported))
    put("statistical_unit", SAT if unit_ok else UNSAT, "donor multiplicity, complete pairs and donor fixed-effect coding",
        {"unit": unit, "unique_donors": int(metadata[donor].nunique()), "repeated_donors": bool(repeated)},
        "Aggregate technical repeats or export a supported paired donor model; general repeated measures require an adapter.")
    return list(checks.values())


def _schema() -> dict[str, Any]:
    return _json((Path(__file__).parents[1] / "data" / "de-claim-conditions.v1.schema.json").read_bytes())


def verify_de_claim_conditions(path: str | Path, *, de_table: Any = None,
                               sample_metadata: Any = None) -> dict[str, Any]:
    """Compile exact structured claims into checked prerequisites and scope alternatives.

    Missing files produce NOT_ASSESSED, contradictory artifacts produce CONFLICT.
    Invalid contract syntax raises ValueError; the audit adapter converts it into
    a required parse-failure check. Optional audit inputs must be identical files.
    """
    path = Path(path).resolve()
    data = path.read_bytes()
    contract = _json(data)
    try:
        jsonschema.validate(contract, _schema())
    except jsonschema.ValidationError as exc:
        raise ValueError(f"Invalid DE claim contract: {exc.message}") from exc
    ids = [c["claim_id"] for c in contract["claims"]]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate claim IDs")
    if contract["analysis"]["numerator"] == contract["analysis"]["denominator"]:
        raise ValueError("Numerator and denominator must differ")
    loaded, common = {}, []
    for role in ("results", "metadata", "design", "model"):
        value, check = _load_artifact(path.parent, role, contract["artifacts"].get(role),
                                     {"results": de_table, "metadata": sample_metadata}.get(role))
        loaded[role] = value
        common.append(check)
    refs = [ref for check in common for ref in check["evidence_refs"]]
    common += _design_checks(contract, loaded["model"], loaded["metadata"], loaded["design"], refs)
    analysis = contract["analysis"]
    reports = []
    for claim in contract["claims"]:
        checks = list(common)
        table = loaded["results"]
        row = None
        # Fixed exported column semantics avoid guessing which gene/contrast a row describes.
        selector = {"gene": claim["gene"], "cell_type": analysis["cell_type"],
                    "numerator": analysis["numerator"], "denominator": analysis["denominator"]}
        row_status, observation = UNKNOWN, None
        if table is not None and set(selector) <= set(table.columns):
            mask = np.ones(len(table), dtype=bool)
            for key, val in selector.items():
                mask &= table[key].to_numpy() == val
            rows = table.loc[mask]
            row_status = SAT if len(rows) == 1 else CONFLICT if len(rows) > 1 else UNKNOWN
            observation = {"matching_rows": len(rows), "selector": selector}
            if len(rows) == 1:
                row = rows.iloc[0]
        checks.append(_check("result_identity", "Exactly one result row matches gene, cell set and ordered comparison.",
                             ARTIFACT if table is not None else MISSING, row_status, "exact row selection", refs, observation,
                             repair="Export one uniquely identified row for this gene and ordered comparison."))
        numbers: dict[str, float] = {}
        for key in ("log2_fold_change", "padj", "ci_lower", "ci_upper", "ci_level"):
            try:
                value = float(row[key]) if row is not None else float("nan")
                if np.isfinite(value):
                    numbers[key] = value
            except (KeyError, ValueError, TypeError):
                pass
        effect = numbers.get("log2_fold_change")
        sign_ok = effect is not None and (effect > 0 if claim["direction"] == "up" else effect < 0)
        checks.append(_check("effect_direction", "Finite log2 fold change agrees with the requested direction.",
                             ARTIFACT if row is not None else MISSING,
                             (SAT if sign_ok else UNSAT) if effect is not None else UNKNOWN,
                             "signed effect, numerator minus denominator", refs, {"effect": effect},
                             repair="Correct the wording or the contrast; do not silently reverse a comparison."))
        valid_ci = all(key in numbers for key in ("ci_lower", "ci_upper", "ci_level", "log2_fold_change"))
        ci_state = UNKNOWN
        if valid_ci and effect is not None:
            low, high = numbers["ci_lower"], numbers["ci_upper"]
            if not (0 < numbers["ci_level"] < 1 and low <= effect <= high):
                ci_state = CONFLICT
            else:
                ci_state = SAT if (low > 0 if claim["direction"] == "up" else high < 0) else UNSAT
                if numbers["ci_level"] < 1 - claim["alpha"] - 1e-12:
                    ci_state = UNSAT
        checks.append(_check("effect_uncertainty", "Reported interval at the requested level excludes zero in the claimed direction.",
                             ARTIFACT if row is not None else MISSING, ci_state, "interval bounds, level and direction", refs,
                             {k: v for k, v in numbers.items() if k.startswith("ci_")},
                             coverage="Reported interval checked; interval construction and coverage not recomputed.",
                             repair="Export compatible effect and confidence interval; nonsignificance is not absence."))
        padj = numbers.get("padj")
        p_state = UNKNOWN if padj is None else CONFLICT if not 0 <= padj <= 1 else SAT if padj <= claim["alpha"] else UNSAT
        checks.append(_check("adjusted_significance", "Reported adjusted p-value meets the explicit claim threshold.",
                             ARTIFACT if row is not None else MISSING, p_state, "0 <= padj <= alpha <= 1", refs,
                             {"padj": padj, "alpha": claim["alpha"]}, coverage="Multiplicity procedure not recomputed.",
                             repair="Narrow to the observed estimate or supply the appropriate adjusted result."))
        declarations = contract.get("declarations", {})
        for key, requirement in (("population_transport", "Sampling and target-population transport assumptions need review."),
                                 ("causal_identification", "Intervention, confounding and identification assumptions need review.")):
            checks.append(_check(key, requirement, DECLARED if key in declarations else MISSING, UNKNOWN,
                                 "no executable adapter for this premise", [], declarations.get(key),
                                 repair="Provide claim-specific evidence for scientific review; declarations cannot satisfy this check."))
        by_id = {c["condition_id"]: c for c in checks}
        table_ids = ["artifact_results", "result_identity", "effect_direction"]
        cohort_ids = [c["condition_id"] for c in checks if c["condition_id"] not in ("population_transport", "causal_identification")]
        dependencies = {"table_observation": table_ids, "cohort_association": cohort_ids,
                        "population_effect": [*cohort_ids, "population_transport"],
                        "causal_effect": [*cohort_ids, "causal_identification"]}
        variants = []
        prefix = f"{claim['gene']} / {analysis['cell_type']} / {analysis['numerator']} versus {analysis['denominator']}"
        sentences = {
            "table_observation": f"The supplied table reports {prefix}: log2 fold change {effect}.",
            "cohort_association": f"Under the supplied model, {prefix} has a {claim['direction']}ward association in the analyzed cohort.",
            "population_effect": f"{prefix} has a {claim['direction']}ward effect in the target population.",
            "causal_effect": f"The condition causes a {claim['direction']}ward change in {prefix}.",
        }
        for scope, required in dependencies.items():
            state = _status([by_id[key] for key in required])
            variants.append(dict(scope=scope, statement=sentences[scope], status=state,
                                 supported_within_checked_scope=state == SAT, required_conditions=required,
                                 unmet_conditions=[key for key in required if by_id[key]["status"] != SAT]))
        requested = next(v for v in variants if v["scope"] == claim["scope"])
        reports.append(dict(claim=claim, canonical_statement=requested["statement"], status=requested["status"],
                            conditions=checks, scope_assessments=variants,
                            supported_statements=[v["statement"] for v in variants if v["supported_within_checked_scope"]]))
    return dict(schema_version=VERSION, contract_sha256=_digest(data), analysis=analysis,
                verifier={"implementation_sha256": _digest(Path(__file__).read_bytes()),
                          "schema_sha256": _digest((Path(__file__).parents[1] / "data" /
                                                    "de-claim-conditions.v1.schema.json").read_bytes()),
                          "numpy_version": np.__version__},
                status=_status(reports), claims=reports, scientific_authorization="NONE",
                producer_authentication="NOT_ESTABLISHED", analysis_execution_verification="NOT_PERFORMED",
                limitations=["Necessary conditions over supplied artifacts only; no biological validity or sufficiency proof.",
                             "Raw-count aggregation, fit, p-values and intervals are not recomputed.",
                             "Donor identity, model adequacy, sampling and causal assumptions need scientific review.",
                             "Structured canonical claims only; free prose is assessed separately."])


def render_conditions(report: dict[str, Any]) -> str:
    """Readable condition-by-condition output shared by CLI and review bundles."""
    lines = ["## 声明成立条件的可执行验证", "", "逐项产物检查；不构成科学授权或执行真实性认证。", ""]
    for claim in report.get("claims", []):
        lines += [f"### {claim['claim']['claim_id']} — {claim['status']}", claim["canonical_statement"], ""]
        for condition in claim["conditions"]:
            lines.append(f"- {condition['condition_id']}: {condition['source']} / {condition['status']} — {condition['requirement']}")
            if condition["status"] != SAT and condition["repair"]:
                lines.append(f"  修复或补充：{condition['repair']}")
        lines += ["", "当前支持的具体表述（限已检查范围）：", *[f"- {s}" for s in claim["supported_statements"]], ""]
    return "\n".join(lines)
