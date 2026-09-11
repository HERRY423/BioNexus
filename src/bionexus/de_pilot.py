"""Local DE shadow-review bundles and descriptive, human-reported pilot outcomes.

No execution, networking, automatic scientific approval, or external certification.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bionexus.de_bundle import IMMUTABLE_ARTIFACTS, INTEGRITY_PROFILE, MAX_ARTIFACT_BYTES, verify_de_bundle
from bionexus.pilot_costs import empty_costs, summarize_costs
from bionexus.versions import VERSION


def _json(value: Any) -> str:
    def scalar(item: Any) -> Any:
        import numpy as np

        if isinstance(item, np.generic):
            return item.item()
        raise TypeError(f"Unsupported review value: {type(item).__name__}")

    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False, default=scalar) + "\n"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot_inputs(paths: dict[str, Any]) -> dict[str, Any]:
    """Hash supplied files without copying research data into the review bundle."""
    return {role: {"name": Path(p).name, "sha256": _sha(Path(p))}
            for role, p in paths.items() if p is not None}


def demo_inputs() -> dict[str, Any]:
    import pandas as pd

    # Explicitly synthetic: deliberately omit adjusted p-values and execution evidence.
    return {
        "de_table": pd.DataFrame({"gene": ["DEMO_GENE_1", "DEMO_GENE_2"], "pvalue": [0.01, 0.03]}),
        "sample_metadata": pd.DataFrame({"donor": [f"DEMO_D{i}" for i in range(1, 7)],
                                         "condition": ["control"] * 3 + ["treated"] * 3}),
        "claim_text": "These genes are significantly differentially expressed after FDR correction.",
    }


def _finding_ids(audit: dict[str, Any]) -> list[str]:
    return [f"F{i:03d}" for i, _ in enumerate(audit["findings"], 1)]


def render_review(audit: dict[str, Any], case_id: str, synthetic: bool, claim: str | None = None) -> str:
    lines = [f"# 投稿前 DE 影子审阅 · {case_id}", "",
             "目标：定位可能影响声明的问题，供研究者复核；本报告不批准分析或投稿。",
             f"审计状态：`{audit['overall_status']}`。净收益：**尚未评估**。"]
    if synthetic:
        lines += ["", "**合成教学示例：不是真实研究，不能计入实验室收益。**"]
    lines += ["", f"待审声明：{claim or '未提供；当前仅审阅产物与证据缺口。'}"]
    lines += ["", "## 先处理这些问题", ""]
    priorities = {"BLOCKER": 0, "HIGH_IMPACT": 1, "ADVISORY": 2}
    findings = list(zip(_finding_ids(audit), audit["findings"]))
    findings.sort(key=lambda item: priorities.get(item[1]["severity"], 3))
    for fid, finding in findings[:3]:
        lines += [f"### {fid} · {finding['title']}", "",
                  f"影响：{finding['impact_on_conclusion']}", "",
                  f"定位：{finding.get('sample_or_donor') or finding.get('step_or_location') or '未定位到具体对象；需要复核'}",
                  "", "最小下一步：", ""]
        fix = finding["minimal_fix"]
        lines += ["```text", fix, "```", ""] if "\n" in fix else [fix, ""]
    if not findings:
        lines += ["未产生具体发现；这不代表缺失证据已被核查。", ""]
    if len(findings) > 3:
        lines += [f"另有 {len(findings) - 3} 项发现，见 [完整审计](audit-full.md)。", ""]
    missing = [c for c in audit.get("checks", []) if c["status"] in {"MISSING_EVIDENCE", "PARSE_FAILED"}]
    if missing:
        lines += ["## 还缺哪些证据", ""]
        lines += [f"- {c['title']}：{c['summary']}" for c in missing]
    boundary = audit.get("claim_boundary") or {}
    lines += ["", "## 当前如何表述", "", boundary.get("allowed_scope", "未评估"), "",
              boundary.get("prohibited_scope", ""), "",
              "## 负责人需要复核", ""]
    for decision in audit.get("pi_decisions", []):
        lines += [f"- {decision['decision_id']}：{decision['title']} — {decision['context']}"]
    if not audit.get("pi_decisions"):
        lines += ["没有额外生成方法权衡项；仍需由研究者确认发现与声明。"]
    lines += ["", "## 完成审阅", "",
              "打开 [review.json](review.json)，记录人工判定、漏检、审阅时间与是否愿意复用。",
              "未完成的评审保留 PENDING；独立参考审阅应在看本报告之前完成。",
              "需要修改分析时，在原工作流修复，再生成新的审阅目录。旧报告与未解决问题继续保留。",
              "", "[完整证据与全部发现](audit-full.md) · [机器结果](audit.json) · [输入指纹](manifest.json)"]
    return "\n".join(lines) + "\n"


def write_bundle(result: Any, destination: str | Path, *, inputs: dict[str, Any],
                 claim: str | None, synthetic: bool = False) -> Path:
    directory = Path(destination)
    audit = result.to_dict()
    audit_text = _json(audit)
    audit_hash = hashlib.sha256(audit_text.encode("utf-8")).hexdigest()
    origin = "SYNTHETIC_DEMO" if synthetic else "USER_SUPPLIED_UNVERIFIED"
    manifest = {"schema": "bionexus.de-shadow-bundle.v1", "created_at": datetime.now(timezone.utc).isoformat(),
                "bionexus_version": VERSION, "audit_sha256": audit_hash, "inputs": inputs,
                "claim": claim, "data_origin": origin, "scientific_authorization": "NONE"}
    review = {
        "schema": "bionexus.de-pilot-review.v1", "case_id": directory.name,
        "site_id": None, "audit_sha256": audit_hash, "data_origin": origin,
        "review_status": "PENDING", "reviewer_name": None,
        "reference_review": {"reviewer_name": None, "reviewed_before_audit": None, "issues": None},
        "finding_judgments": [{"finding_id": fid, "rule_id": f["rule_id"], "title": f["title"],
                               "judgment": None, "reference_issue_id": None, "note": None}
                              for fid, f in zip(_finding_ids(audit), audit["findings"])],
        "timing": {"comparison": None, "baseline_review_minutes": None, "assisted_review_minutes": None,
                   "setup_minutes": None, "repair_minutes": None},
        "costs": empty_costs(),
        "author_help_count": None, "report_understood": None, "claim_changed": None,
        "would_reuse": None, "reviewer_note": None,
    }
    files = {"audit.json": audit_text, "audit-full.md": result.to_markdown(),
             "REVIEW.md": render_review(audit, directory.name, synthetic, claim),
             "review.json": _json(review),
             "reference-review.json": _json(review["reference_review"])}
    # Additive v1 fields: old readers continue reading audit_sha256. New readers
    # distinguish historic audit-only bundles from complete report integrity.
    manifest["integrity_profile"] = INTEGRITY_PROFILE
    manifest["immutable_artifacts"] = {
        name: hashlib.sha256(files[name].encode("utf-8")).hexdigest() for name in IMMUTABLE_ARTIFACTS
    }
    files["manifest.json"] = _json(manifest)
    if any(len(files[name].encode("utf-8")) > MAX_ARTIFACT_BYTES for name in (*IMMUTABLE_ARTIFACTS, "manifest.json")):
        raise ValueError("Review bundle exceeds the 8 MiB per-artifact compatibility limit")
    # Refuse even an existing empty directory: old observations are never overwritten.
    directory.mkdir(parents=True, exist_ok=False)
    for name, content in files.items():
        # Hash and persist identical UTF-8 bytes on Windows and Unix.
        (directory / name).write_bytes(content.encode("utf-8"))
    return directory


def _text(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} requires a nonempty human-entered value")


def _number(value: Any, field: str) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                              or not math.isfinite(value) or value < 0):
        raise ValueError(f"{field} must be null or a finite nonnegative number")


def summarize_reviews(paths: list[str | Path]) -> dict[str, Any]:
    """Describe supplied observations; never infer independent review or net benefit."""
    cases, seen = [], set()
    for value in paths:
        path = Path(value)
        integrity = verify_de_bundle(path.parent)
        if integrity["status"] not in {"CONSISTENT", "LEGACY_LIMITED"}:
            raise ValueError(f"Bundle integrity failed: {integrity['issues']}")
        review = json.loads(path.read_text(encoding="utf-8-sig"))
        manifest = json.loads((path.parent / "manifest.json").read_text(encoding="utf-8-sig"))
        if not isinstance(review, dict) or not isinstance(manifest, dict):
            raise ValueError("Review and manifest must be JSON objects")
        audit_path = path.parent / "audit.json"
        if review.get("schema") != "bionexus.de-pilot-review.v1":
            raise ValueError(f"Unsupported review schema: {path}")
        if manifest.get("schema") != "bionexus.de-shadow-bundle.v1":
            raise ValueError(f"Unsupported bundle schema: {path}")
        digest = _sha(audit_path)
        if review.get("audit_sha256") != digest or manifest.get("audit_sha256") != digest:
            raise ValueError(f"Audit changed or review belongs to another audit: {path}")
        origin = manifest.get("data_origin")
        if origin not in {"SYNTHETIC_DEMO", "USER_SUPPLIED_UNVERIFIED"} or review.get("data_origin") != origin:
            raise ValueError(f"Data origin mismatch: {path}")
        _text(review.get("case_id"), "case_id")
        identity = (review.get("site_id"), review["case_id"])
        audit_identity = (review.get("site_id"), digest)
        if identity in seen or audit_identity in seen:
            raise ValueError(f"Duplicate case or same-site audit: {path}")
        seen.update((identity, audit_identity))
        status = review.get("review_status")
        if status not in {"PENDING", "COMPLETE"}:
            raise ValueError("review_status must be PENDING or COMPLETE")
        case = {"case_id": review["case_id"], "site_id": review.get("site_id"), "status": status,
                "bundle_integrity": integrity["status"],
                "data_origin": origin, "review_sha256": _sha(path), "audit_sha256": digest}
        if status == "PENDING" or origin == "SYNTHETIC_DEMO":
            case["excluded_reason"] = "synthetic_demo" if origin == "SYNTHETIC_DEMO" else "pending_review"
            cases.append(case)
            continue
        _text(review.get("site_id"), "site_id")
        _text(review.get("reviewer_name"), "reviewer_name")
        reference = review.get("reference_review", {})
        _text(reference.get("reviewer_name"), "reference_review.reviewer_name")
        if reference.get("reviewed_before_audit") is not True:
            raise ValueError("Complete pilot observations require a reference review made before seeing the audit")
        if not isinstance(reference.get("issues"), list):
            raise ValueError("reference_review.issues must be an explicit list (empty only if reviewed and no issues)")
        issues = {}
        for issue in reference["issues"]:
            _text(issue.get("issue_id"), "reference issue_id")
            _text(issue.get("description"), "reference description")
            if issue["issue_id"] in issues:
                raise ValueError("Duplicate reference issue")
            issues[issue["issue_id"]] = issue
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        expected = dict(zip(_finding_ids(audit), audit["findings"]))
        judged, detected, uncertain = set(), set(), set()
        alarms = unresolved = 0
        for judgment in review.get("finding_judgments", []):
            fid = judgment.get("finding_id")
            if fid not in expected or fid in judged or judgment.get("rule_id") != expected[fid]["rule_id"]:
                raise ValueError("Unknown, duplicate, or mismatched finding judgment")
            judged.add(fid)
            verdict, issue = judgment.get("judgment"), judgment.get("reference_issue_id")
            _text(judgment.get("note"), "finding judgment note")
            if verdict not in {"CONFIRMED", "FALSE_ALARM", "UNRESOLVED"}:
                raise ValueError("Each finding needs CONFIRMED, FALSE_ALARM, or UNRESOLVED")
            if issue is not None and issue not in issues:
                raise ValueError("Unknown reference_issue_id")
            if verdict == "CONFIRMED":
                if issue is None:
                    raise ValueError("Confirmed findings must link a reference issue")
                detected.add(issue)
            elif verdict == "FALSE_ALARM":
                if issue is not None:
                    raise ValueError("False alarms cannot link a confirmed reference issue")
                alarms += 1
            else:
                unresolved += 1
                if issue is not None:
                    uncertain.add(issue)
        if judged != set(expected):
            raise ValueError("Complete review must retain and judge every audit finding")
        timing = review.get("timing", {})
        for key in ("baseline_review_minutes", "assisted_review_minutes", "setup_minutes", "repair_minutes"):
            _number(timing.get(key), key)
        comparison = timing.get("comparison")
        if comparison not in {None, "PAIRED_SAME_CASE", "UNPAIRED"}:
            raise ValueError("timing.comparison must be null, PAIRED_SAME_CASE, or UNPAIRED")
        for key in ("report_understood", "claim_changed", "would_reuse"):
            if review.get(key) is not None and type(review[key]) is not bool:
                raise ValueError(f"{key} must be null or boolean")
        help_count = review.get("author_help_count")
        if help_count is not None and (type(help_count) is not int or help_count < 0):
            raise ValueError("author_help_count must be null or a nonnegative integer")
        baseline, assisted = timing.get("baseline_review_minutes"), timing.get("assisted_review_minutes")
        delta = baseline - assisted if comparison == "PAIRED_SAME_CASE" and baseline is not None and assisted is not None else None
        case.update({"reference_issue_count": len(issues),
                     "full_costs": summarize_costs(review.get("costs")),
                     "detected_reference_issues": len(detected), "missed_reference_issues": len(set(issues) - detected - uncertain),
                     "unresolved_reference_issues": len(uncertain - detected), "false_alarm_findings": alarms,
                     "unresolved_findings": unresolved, "review_minutes_saved": delta,
                     "timing": timing, "author_help_count": help_count,
                     **{k: review.get(k) for k in ("report_understood", "claim_changed", "would_reuse")}})
        cases.append(case)
    included = [c for c in cases if "excluded_reason" not in c]
    paired = [c for c in included if c["review_minutes_saved"] is not None]
    # Includes setup and repair only when measured for that same case; never fill missing with zero.
    costed = [c for c in paired if all(c["timing"].get(k) is not None for k in ("setup_minutes", "repair_minutes"))]
    fully_costed = [c for c in included if c["full_costs"]["minutes_saved"] is not None]
    return {
        "schema": "bionexus.de-pilot-summary.v2", "evidence_status": "REPORTED_OBSERVATIONS" if included else "NOT_ASSESSED",
        "net_benefit": "NOT_ESTABLISHED", "external_validation": "NOT_ESTABLISHED",
        "submitted_cases": len(cases), "included_cases": len(included),
        "reported_sites": len({c["site_id"] for c in included}), "paired_timing_cases": len(paired),
        "mean_review_minutes_saved": sum(c["review_minutes_saved"] for c in paired) / len(paired) if paired else None,
        "fully_costed_cases": len(fully_costed),
        "setup_and_repair_costed_cases": len(costed),
        "mean_full_person_minutes_saved": sum(c["full_costs"]["minutes_saved"] for c in fully_costed) / len(fully_costed) if fully_costed else None,
        "mean_minutes_saved_after_setup_and_repair": sum(c["review_minutes_saved"] - c["timing"]["setup_minutes"]
            - c["timing"]["repair_minutes"] for c in costed) / len(costed) if costed else None,
        "counts": {key: sum(c[key] for c in included) for key in (
            "detected_reference_issues", "missed_reference_issues", "unresolved_reference_issues",
            "false_alarm_findings", "unresolved_findings")},
        "feedback": {key: {"answered": sum(c[key] is not None for c in included),
                            "yes": sum(c[key] is True for c in included),
                            "no": sum(c[key] is False for c in included)}
                     for key in ("report_understood", "claim_changed", "would_reuse")},
        "reference_negative_cases": sum(c["reference_issue_count"] == 0 for c in included),
        "reference_negative_cases_with_false_alarms": sum(c["reference_issue_count"] == 0
                                                         and c["false_alarm_findings"] > 0 for c in included),
        "cases": cases,
        "limitations": ["Human-entered observations; identity, independence and timing are not authenticated.",
                        "Pending cases and synthetic demonstrations are excluded, never scored as successes.",
                        "Time differences are descriptive paired self-reports, not causal benefit estimates.",
                        "Missing costs remain unknown. No adoption, scientific authorization or calibration is granted."],
    }


def render_summary(summary: dict[str, Any]) -> str:
    lines = ["# DE 影子审计试点观察", "", "净收益尚未确立；以下是人工填报的描述性观察。", "",
             f"提交 {summary['submitted_cases']} 例；纳入 {summary['included_cases']} 例；"
             f"填报实验室 {summary['reported_sites']} 个。", "",
             f"配对审阅用时：{summary['paired_timing_cases']} 例；平均节省分钟："
             f"{summary['mean_review_minutes_saved'] if summary['mean_review_minutes_saved'] is not None else '未评估'}。",
             f"仅含接入与修复成本（旧口径）：{summary['setup_and_repair_costed_cases']} 例；平均节省分钟："
             f"{summary['mean_minutes_saved_after_setup_and_repair'] if summary['mean_minutes_saved_after_setup_and_repair'] is not None else '未评估'}。",
             f"双臂五项完整人工成本：{summary['fully_costed_cases']} 例；平均节省人分钟："
             f"{summary['mean_full_person_minutes_saved'] if summary['mean_full_person_minutes_saved'] is not None else '未评估'}。",
             "", "正数表示节省，负数表示增加时间。不同指标的分母不同，不能相互替代。", "",
             "| 分析 | 实验室 | 状态 | 误报发现 | 漏检参考问题 | 未解决发现 |", "|---|---|---|---|---|---|"]
    for case in summary["cases"]:
        cell = lambda v: str(v).replace("|", "\\|").replace("\n", " ")  # noqa: E731
        lines += ["| " + " | ".join(cell(v) for v in (
            case["case_id"], case["site_id"] or "未填写", case.get("excluded_reason", case["status"]),
            case.get("false_alarm_findings", "—"), case.get("missed_reference_issues", "—"),
            case.get("unresolved_findings", "—"))) + " |"]
    reuse = summary["feedback"]["would_reuse"]
    lines += ["", f"复用意愿：{reuse['answered']} 人次回答，愿意 {reuse['yes']}，不愿意 {reuse['no']}。",
              "", "身份、独立性和用时未经外部核验；结果不改变任何科学授权或校准状态。"]
    return "\n".join(lines) + "\n"
