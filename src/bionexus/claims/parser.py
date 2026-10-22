"""
Deterministic Claim Parser and Lexicon-based Linguistic Extraction (BNS-017).
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Union

from bionexus.claims.models import (
    AssociationType,
    CausalStrength,
    ClaimRelationshipType,
    ClinicalActionability,
    Directionality,
    GeneralizationScope,
    MechanismDepth,
    ScientificClaimIR,
    ScientificEntity,
)
from bionexus.evidence_model import ClaimClass

# Explicit clause boundaries shared by disclaimer scope and the causal detector.
# This is a bounded lexical rule, not a general parser.
_CLAUSE_BOUNDARY_RE = re.compile(
    r"[,，;；。!?！？\n\r:]|\.(?:\s+|$)|"
    r"\b(?:but|however|yet|and|therefore|thus|although|whereas|because)\b|"
    r"\bsince\b|"
    r"但(?:是)?|然而|并且|因此|所以|尽管|因为|由于",
    re.IGNORECASE,
)


class DeterministicClaimParser:
    """
    Deterministic scientific claim parser.

    Transforms raw statements into canonical `ScientificClaimIR` representations
    without relying on stochastic LLM calls.
    """

    # Causal & Mechanistic Action Verbs (word-boundary compiled below)
    _CAUSAL_VERBS_FORWARD = [
        r"因果驱动",
        r"主导",
        r"\bserv(?:e|es|ed|ing)\s+as\s+(?:a|an|the)?\s*(?:primary\s+)?engine\s+(?:for|of)\b",
        r"证明了",
        r"证实了",
        r"导致了?",
        r"促使了?",
        r"诱导了?",
        r"引起了?",
        r"驱动了?",
        r"促发了?",
        r"介导了?",
        r"重塑了?",
        r"决定了?",
        r"调控了?",
        r"作为主要推手",
        r"起决定性作用",
        r"起关键作用",
        r"扮演关键角色",
        r"导致",
        r"促使",
        r"诱导",
        r"引起",
        r"驱动",
        r"介导",
        r"重塑",
        r"调控",
        r"决定",
        r"\bdrives?\b",
        r"\bcauses?\b",
        r"\binduces?\b",
        r"\btriggers?\b",
        r"\bpromotes?\b",
        r"\bactivates?\b",
        r"\brepresses?\b",
        r"\bsuppress(?:es)?\b",
        r"\binhibits?\b",
        r"\bmodulates?\b",
        r"\bregulates?\b",
        r"\bup-?regulates?\b",
        r"\bdown-?regulates?\b",
        r"\benhances?\b",
        r"\battenuates?\b",
        r"\bconfers?\b",
        r"\baccelerates?\b",
        r"\bimpairs?\b",
        r"\babrogates?\b",
        r"\bleads?\s+to\b",
        r"\bresults?\s+in\b",
        r"\bpolarizes?\b",
        r"\bprograms?\b",
        r"\bcontrols?\b",
        r"\bmediates?\b",
        r"\bshapes?\b",
        r"\bdictates?\b",
        r"\borchestrates?\b",
        r"\bremodels?\b",
        r"\bre-?programs?\b",
        r"\bfuels?\b",
        r"\bsteers?\b",
        r"\bshifts?\b",
        r"\bgoverns?\b",
        r"\binstigates?\b",
        r"\belicits?\b",
        r"\bengenders?\b",
        r"\bcatalyzes?\b",
        r"\bpropels?\b",
        r"\bprimes?\b",
        r"\bfosters?\b",
        r"\bpotentiates?\b",
        r"\bskews?\b",
        r"\bbiases?\b",
        r"\bgive(?:s|n|ing)?\s+rise\s+to\b",
        r"\blay(?:s|d|ing)?\s+the\s+foundation\s+for\b",
        r"\bunderl(?:ies|y|ying)?\b",
        r"\b(?:is|are|was|were)\s+(?:pivotal|instrumental|essential|responsible|central|critical|vital|indispensable)\s+(?:for|in)\b",
        r"\b(?:is|are|was|were)\s+the\s+(?:primary|main|key|principal)?\s*(?:culprits?|drivers?|factors?)\s+(?:behind|for|in)\b",
        r"\bplay(?:s|ed|ing)?\s+(?:a|an)?\s*(?:critical|pivotal|key|essential|central|causal|decisive|major|vital|indispensable)?\s*role\s+in\b",
        r"\bact(?:s|ed|ing)?\s+as\s+(?:a|an)?\s*(?:master\s+regulator|key\s+regulator|key\s+driver|primary\s+driver|driver|trigger|switch|initiator|catalyst)\s+(?:of|for|in)\b",
        r"\bserv(?:es|ed|ing)?\s+as\s+(?:a|an)?\s*(?:master\s+regulator|key\s+regulator|key\s+driver|primary\s+driver|driver|trigger|switch|initiator|catalyst)\s+(?:of|for|in)\b",
    ]

    _CAUSAL_VERBS_PASSIVE = [
        r"是由.*?介导的?",
        r"是由.*?驱动的?",
        r"受.*?调控",
        r"由.*?介导",
        r"由.*?驱动",
        r"由.*?引起",
        r"依赖于",
        r"\b(?:is|are|was|were)\s+driven\s+by\b",
        r"\b(?:is|are|was|were)\s+caused\s+by\b",
        r"\b(?:is|are|was|were)\s+induced\s+by\b",
        r"\b(?:is|are|was|were)\s+triggered\s+by\b",
        r"\b(?:is|are|was|were)\s+regulated\s+by\b",
        r"\b(?:is|are|was|were)\s+mediated\s+by\b",
        r"\b(?:is|are|was|were)\s+orchestrated\s+by\b",
        r"\b(?:is|are|was|were)\s+shaped\s+by\b",
        r"\b(?:is|are|was|were)\s+dictated\s+by\b",
        r"\b(?:is|are|was|were)\s+remodeled\s+by\b",
        r"\b(?:is|are|was|were)\s+steered\s+by\b",
        r"\b(?:is|are|was|were)\s+fueled\s+by\b",
        r"\b(?:is|are|was|were)\s+governed\s+by\b",
        r"\b(?:is|are|was|were)\s+primed\s+by\b",
        r"\b(?:is|are|was|were)\s+elicited\s+by\b",
        r"\b(?:is|are|was|were)\s+fostered\s+by\b",
        r"\b(?:is|are|was|were)\s+reprogrammed\s+by\b",
        r"\bdepends?\s+on\b",
    ]

    # Associational & Correlational Verbs
    _ASSOCIATIONAL_VERBS = [
        r"相关",
        r"关联",
        r"共定位",
        r"共表达",
        r"\bcorrelates?\s+with\b",
        r"\bassociates?\s+with\b",
        r"\bis\s+associated\s+with\b",
        r"\bco-?occurs?\s+with\b",
        r"\bco-?localizes?\s+with\b",
        r"\bco-?expressed\s+with\b",
        r"\bexhibits?\b",
        r"\bshows?\b",
        r"\bdisplays?\b",
    ]

    # Identity / Cluster Assignment Verbs
    _IDENTITY_VERBS = [
        r"\bcluster\s*\d+\s*(?:is|represents|corresponds\s*to|identified\s*as|assigned\s*as|defines)\b",
        r"\bcluster\s*\d+\s*:\s*",
        r"\bidentified\s+as\b",
        r"\brepresents?\b",
    ]

    # Clinical / Regulatory Action Verbs
    _CLINICAL_VERBS = [
        r"预测",
        r"诊断",
        r"治疗反应",
        r"免疫治疗",
        r"\bdiagnos(?:es|ed|is|tic)\b",
        r"\btreat(?:s|ed|ment)\s+recommendation\b",
        r"\bpatient\s+(?:treatment|therapy|prescription)\b",
        r"\b21\s*cfr\s*part\s*11\b",
        r"\bclia\b",
        r"\bcap\s+accredited\b",
    ]

    # Epistemic Hedges & Qualifiers
    _QUALIFIERS = [
        "candidate",
        "putative",
        "unverified",
        "hypothesized",
        "exploratory",
        "suggests",
        "suggesting",
        "potential",
        "preliminary",
        "indicates",
        "possibly",
        "likely",
    ]

    # Word-boundary qualifier matcher: fixes substring false hedges such as
    # "unlikely" matching "likely".
    _QUALIFIER_RE = re.compile(r"\b(?:" + "|".join(_QUALIFIERS) + r")\b", re.IGNORECASE)

    # Modal/verbal hedge window: a causal verb preceded within the same clause
    # by an epistemic modal is hypothesized, not asserted.
    _HEDGE_MODAL_RE = re.compile(
        r"\b(?:may|might|could|appears?\s+to|seems?\s+to|is\s+thought\s+to|"
        r"are\s+thought\s+to|putatively|presumably)\b",
        re.IGNORECASE,
    )
    _HEDGE_WINDOW_CHARS = 64

    # Negation Markers: strictly partitioned into Absence of Evidence vs Evidence of Absence
    _ABSENCE_OF_EVIDENCE_PATTERNS = [
        r"不能(?:证明|推断|得出|建立)",
        r"无法(?:证明|推断|得出|建立)",
        r"并未(?:证明|显示|发现)",
        r"没有证据(?:表明|支持|证明)",
        r"不足以(?:证明|推断|得出)",
        r"缺乏证据",
        r"\bcannot\s+(?:prove|demonstrate|establish|confirm|conclude)\b",
        r"\bcan\s+not\s+(?:prove|demonstrate|establish|confirm|conclude)\b",
        r"\bcould\s+not\s+(?:prove|demonstrate|establish|confirm|conclude)\b",
        r"\bunable\s+to\s+(?:prove|demonstrate|establish|confirm|conclude)\b",
        r"\bdoes\s+not\s+(?:prove|demonstrate|establish|imply)\b",
        r"\bdo\s+not\s+(?:prove|demonstrate|establish|imply)\b",
        r"\bdid\s+not\s+(?:prove|demonstrate|establish|imply)\b",
        r"\bnot\s+(?:proven|established|sufficient)\b",
        r"\bno\s+evidence\s+(?:for|of|that)\b",
        r"\bwithout\s+evidence\s+(?:of|for)\b",
        r"\bfails?\s+to\s+(?:demonstrate|prove|establish)\b",
        r"\bnot\s+sufficient\s+to\s+(?:prove|establish|infer|conclude|claim)\b",
    ]

    _EVIDENCE_OF_ABSENCE_PATTERNS = [
        r"不(?:存在|构成|具备|引起|导致|诱导|改变|影响)",
        r"没有差异",
        r"无(?:效应|作用|差异|影响)",
        r"(?:等效|非劣效|不劣于)",
        r"\b(?:no|zero|without)\s+(?:biological\s+|causal\s+)?(?:effect|effects|difference|differences|association)\b",
        r"\b(?:equivalent|equivalence|non[- ]?inferior|non[- ]?inferiority)\b",
        r"\bdoes\s+not\s+(?:cause|drive|induce|show|affect|alter|correlate|associate|change)\b",
        r"\bdo\s+not\s+(?:cause|drive|induce|show|affect|alter|correlate|associate|change)\b",
        r"\bdid\s+not\s+(?:cause|drive|induce|affect|change|alter|show)\b",
        r"\bnever\s+(?:cause|drive|induce)\b",
        r"\bnot\s+causal\b",
        r"\b(?:is|are)\s+not\s+(?:associated|correlated|linked)\s+with\b",
        r"\bfails?\s+to\s+(?:show|induce|cause|drive|reveal)\b",
    ]

    _NEGATION_PATTERNS = _ABSENCE_OF_EVIDENCE_PATTERNS + _EVIDENCE_OF_ABSENCE_PATTERNS

    @classmethod
    def strip_reporting_preamble(cls, text: str) -> str:
        """Remove a bounded non-scientific reporting/context preamble."""
        return re.sub(
            r"^\s*(?:(?:in|for)\s+(?:our|this|the)\s+(?:completed\s+)?(?:cohort|study|analysis)"
            r"|(?:our|the)\s+reported\s+conclusion\s+is|本研究中)[,，:]\s*",
            "",
            text,
            flags=re.I,
        )

    @classmethod
    def is_scoped_disclaimer(cls, text: str) -> bool:
        """Bounded disclaimer recognition; a limitation cannot license another clause.

        Ambiguous compound prose requires separate review. This checks language,
        not the truth of a literature-wide assertion that no evidence exists.
        """
        # Allow bounded reporting/context preambles that do not assert an
        # additional scientific proposition.  Other clauses before punctuation
        # still force separate review.
        text = cls.strip_reporting_preamble(text)
        clauses = [c.strip() for c in _scope_clauses(text) if c.strip()]
        return bool(clauses) and all(
            any(re.search(p, clause, re.I) for p in cls._ABSENCE_OF_EVIDENCE_PATTERNS)
            for clause in clauses
        )

    # Population & Context Scopes
    _POPULATION_PATTERNS = [
        r"普遍存在",
        r"患者普遍",
        r"人群普遍",
        r"总体效应",
        r"全群",
        r"\bin\s+([A-Z0-9_-]+(?:\s+[A-Z0-9_-]+)?)\b",  # in NSCLC, in PBMC
        r"\bacross\s+([A-Z0-9_-]+(?:\s+[A-Z0-9_-]+)?)\b",
        r"\bin\s+(human|mouse|murine|patient|tumor|tme|cancer|normal|healthy)\s*([a-zA-Z0-9_-]*)",
    ]

    # Generic words that must never become a population scope ("in this study").
    _POPULATION_STOPWORDS = {
        "this", "study", "our", "the", "these", "those", "their", "its",
        "vitro", "vivo", "silico", "each", "both", "same", "other",
        "sample", "samples", "dataset", "data", "analysis", "model", "cohort",
    }

    @classmethod
    def parse(
        cls,
        text: str,
        claim_id: Optional[str] = None,
        explicit_claim_class: Optional[Union[str, ClaimClass]] = None,
        data_metadata: Optional[Dict[str, Any]] = None,
    ) -> ScientificClaimIR:
        """
        Parse a single natural-language claim into a structured ScientificClaimIR.
        """
        clean_text = text.strip()
        cid = claim_id or f"CLAIM-{abs(hash(clean_text)) % 1000000:06d}"

        # 1. Negation detection: strictly decouple Absence of Evidence vs Evidence of Absence
        is_epistemic_disclaimer = any(re.search(pat, clean_text, re.IGNORECASE) for pat in cls._ABSENCE_OF_EVIDENCE_PATTERNS)
        is_negative_assertion = any(re.search(pat, clean_text, re.IGNORECASE) for pat in cls._EVIDENCE_OF_ABSENCE_PATTERNS)
        negated = is_epistemic_disclaimer or is_negative_assertion
        negation_type = (
            "ABSENCE_OF_EVIDENCE"
            if is_epistemic_disclaimer
            else ("EVIDENCE_OF_ABSENCE" if is_negative_assertion else "NONE")
        )

        # 2. Qualifiers / Hedges extraction (word-boundary exact)
        text_lower = clean_text.lower()
        qualifiers = [q for q in cls._QUALIFIER_RE.findall(clean_text)]

        # 3. Population Scope extraction (stopword-guarded)
        population_scope = ""
        for pat in cls._POPULATION_PATTERNS:
            match = re.search(pat, clean_text, re.IGNORECASE)
            if not match:
                continue
            if pat.startswith(r"\bin\s+") or pat.startswith(r"\bacross\s+"):
                candidate = re.sub(r"^(?:in|across)\s+", "", match.group(0), flags=re.IGNORECASE).strip()
            else:
                candidate = match.group(0).strip()
            first_token = candidate.split()[0].lower() if candidate.split() else ""
            if candidate and first_token not in cls._POPULATION_STOPWORDS:
                population_scope = candidate
                break

        # 4. Generalization scope
        if (population_scope and any(
            p in population_scope.lower()
            for p in ("nsclc", "human", "cancer", "tumor", "patient", "disease", "cohort", "普遍", "患者", "人群")
        )) or any(k in clean_text for k in ("普遍存在", "患者普遍", "人群普遍", "总体效应", "全群")):
            gen_scope = GeneralizationScope.POPULATION_GENERAL
            if not population_scope:
                population_scope = "population"
        elif "cluster" in text_lower:
            gen_scope = GeneralizationScope.STRATUM_SPECIFIC
        elif "sample" in text_lower:
            gen_scope = GeneralizationScope.SAMPLE_SPECIFIC
        else:
            gen_scope = GeneralizationScope.COHORT_SPECIFIC

        # 5. Clinical Actionability
        clinical_act = ClinicalActionability.NONE
        if any(re.search(pat, clean_text, re.IGNORECASE) for pat in cls._CLINICAL_VERBS) or any(k in clean_text for k in ("预测", "治疗反应", "用药", "预后")):
            if "diagnos" in text_lower or "诊断" in clean_text:
                clinical_act = ClinicalActionability.DIAGNOSTIC_ASSERTION
            elif "treat" in text_lower or "prescrib" in text_lower or "治疗" in clean_text or "用药" in clean_text:
                clinical_act = ClinicalActionability.PRESCRIPTIVE_TREATMENT
            elif "biomarker" in text_lower or "预测" in clean_text or "反应" in clean_text:
                clinical_act = ClinicalActionability.EXPLORATORY_BIOMARKER

        # 6. Entity & Predicate Extraction
        subject_name = "Subject"
        object_name = None
        direction = Directionality.UNDIRECTED
        rel_type = ClaimRelationshipType.CORRELATION
        causal_strength = CausalStrength.ASSOCIATIONAL
        mech_depth = MechanismDepth.BLACK_BOX
        assoc_type = AssociationType.OBSERVATIONAL_CORRELATION
        claim_class = ClaimClass.ASSOCIATION
        adversarial_evasion_detected = False

        # Check for Cell Identity claim
        if any(re.search(pat, clean_text, re.IGNORECASE) for pat in cls._IDENTITY_VERBS):
            rel_type = ClaimRelationshipType.IDENTITY_ASSERTION
            claim_class = ClaimClass.CELL_IDENTITY
            causal_strength = CausalStrength.NONE
            # Extract cluster and cell type
            m = re.search(r"\b(cluster\s*\d+)\b.*?(?:is|represents|corresponds\s*to|:)\s*(?:a|an|the)?\s*([a-zA-Z0-9_\+\-\s]+)", clean_text, re.IGNORECASE)
            if m:
                subject_name = m.group(1).strip()
                object_name = m.group(2).split(".")[0].split(",")[0].strip()

        # Check for Causal / Forward Action Claim (e.g. "A drives B in C")
        else:
            forward_verb_match = None
            for verb_pat in cls._CAUSAL_VERBS_FORWARD:
                for m in re.finditer(verb_pat, clean_text, re.IGNORECASE):
                    if m.group(0).lower().startswith("control"):
                        # Ensure 'control' is not acting as a comparison/experimental condition noun
                        start, end = m.span()
                        before = clean_text[:start].lower()
                        after = clean_text[end:].lower()
                        if any(before.rstrip().endswith(w) for w in ("versus", "vs", "vs.", "-", "negative", "positive", "healthy", "untreated")):
                            continue
                        if any(after.lstrip().startswith(w) for w in ("group", "sample", "condition", "arm", "cell", "donor", "result", "level", "cohort", "well", "plate", "run")):
                            continue
                    forward_verb_match = m
                    break
                if forward_verb_match:
                    break

            passive_verb_match = None
            for verb_pat in cls._CAUSAL_VERBS_PASSIVE:
                m = re.search(verb_pat, clean_text, re.IGNORECASE)
                if m:
                    passive_verb_match = m
                    break

            assoc_verb_match = None
            for verb_pat in cls._ASSOCIATIONAL_VERBS:
                m = re.search(verb_pat, clean_text, re.IGNORECASE)
                if m:
                    assoc_verb_match = m
                    break

            def _hedged(verb_start: int) -> bool:
                """Hypothesized vs asserted: any word-boundary epistemic qualifier,
                or an epistemic modal immediately preceding the causal verb."""
                if cls._QUALIFIER_RE.search(clean_text):
                    return True
                window_start = max(0, verb_start - cls._HEDGE_WINDOW_CHARS)
                return bool(cls._HEDGE_MODAL_RE.search(clean_text[window_start:verb_start]))

            if forward_verb_match:
                start, end = forward_verb_match.span()
                raw_subj = clean_text[:start].strip()
                raw_obj = clean_text[end:].strip()
                # Clean subject and object
                if population_scope:
                    raw_obj = re.sub(rf"\b(?:in|across)\s+{re.escape(population_scope)}\b.*", "", raw_obj, flags=re.IGNORECASE).strip()
                # Strip common gerund prefixes left over from periphrastic verbs like "is pivotal in shaping", "play a role in polarizing"
                raw_obj = re.sub(
                    r"^(?:the\s+)?(?:shaping|driving|regulating|modulating|inducing|polarizing|mediating|orchestrating|promoting|causing|remodeling|steering)\s+(?:of\s+)?",
                    "",
                    raw_obj,
                    flags=re.IGNORECASE,
                ).strip()
                raw_obj = re.sub(r"^(?:towards?|to|into)\s+(?:an?\s+)?", "", raw_obj, flags=re.IGNORECASE).strip()
                raw_obj = raw_obj.rstrip(". ,;")

                subject_name = raw_subj or "Entity A"
                object_name = raw_obj or "Entity B"
                direction = Directionality.DIRECTED_FORWARD

                causal_strength = (
                    CausalStrength.HYPOTHESIZED_CAUSAL if _hedged(start) else CausalStrength.COUNTERFACTUAL_CAUSAL
                )

                # Discern relationship type & depth
                if any(w in text_lower for w in ("polariz", "differentiat", "fate", "exhaustion", "activation", "remodel")):
                    rel_type = ClaimRelationshipType.PHENOTYPE_DRIVER
                    mech_depth = MechanismDepth.SIGNALING_CASCADE
                    claim_class = ClaimClass.MECHANISTIC
                elif any(w in text_lower for w in ("express", "degs", "transcript", "down-regulat", "up-regulat")):
                    rel_type = ClaimRelationshipType.REGULATORY_EFFECT
                    mech_depth = MechanismDepth.PATHWAY_ENRICHMENT
                    claim_class = ClaimClass.CAUSAL
                elif any(w in text_lower for w in ("cell", "t cell", "macrophage", "monocyte", "b cell")):
                    rel_type = ClaimRelationshipType.CELL_CELL_INTERACTION
                    mech_depth = MechanismDepth.SIGNALING_CASCADE
                    claim_class = ClaimClass.MECHANISTIC
                else:
                    rel_type = ClaimRelationshipType.REGULATORY_EFFECT
                    claim_class = ClaimClass.CAUSAL

            elif passive_verb_match:
                start, end = passive_verb_match.span()
                raw_obj = clean_text[:start].strip()
                raw_subj = clean_text[end:].strip()
                if population_scope:
                    raw_subj = re.sub(rf"\b(?:in|across)\s+{re.escape(population_scope)}\b.*", "", raw_subj, flags=re.IGNORECASE).strip()
                    raw_obj = re.sub(rf"\b(?:in|across)\s+{re.escape(population_scope)}\b.*", "", raw_obj, flags=re.IGNORECASE).strip()

                raw_obj = raw_obj.rstrip(". ,;")
                raw_subj = raw_subj.rstrip(". ,;")
                subject_name = raw_subj or "Entity A"
                object_name = raw_obj or "Entity B"
                direction = Directionality.DIRECTED_FORWARD
                causal_strength = (
                    CausalStrength.HYPOTHESIZED_CAUSAL if _hedged(start) else CausalStrength.COUNTERFACTUAL_CAUSAL
                )
                if any(w in text_lower for w in ("polariz", "differentiat", "fate", "exhaustion", "activation", "remodel")):
                    rel_type = ClaimRelationshipType.PHENOTYPE_DRIVER
                    mech_depth = MechanismDepth.SIGNALING_CASCADE
                    claim_class = ClaimClass.MECHANISTIC
                elif any(w in text_lower for w in ("express", "degs", "transcript", "down-regulat", "up-regulat")):
                    rel_type = ClaimRelationshipType.REGULATORY_EFFECT
                    mech_depth = MechanismDepth.PATHWAY_ENRICHMENT
                    claim_class = ClaimClass.CAUSAL
                else:
                    rel_type = ClaimRelationshipType.REGULATORY_EFFECT
                    claim_class = ClaimClass.CAUSAL

            elif assoc_verb_match:
                start, end = assoc_verb_match.span()
                subject_name = clean_text[:start].strip()
                raw_obj = clean_text[end:].strip()
                if population_scope:
                    raw_obj = re.sub(rf"\b(?:in|across)\s+{re.escape(population_scope)}\b.*", "", raw_obj, flags=re.IGNORECASE).strip()
                object_name = raw_obj.rstrip(". ,;")
                direction = Directionality.UNDIRECTED
                causal_strength = CausalStrength.ASSOCIATIONAL
                rel_type = ClaimRelationshipType.CORRELATION
                claim_class = ClaimClass.ASSOCIATION

            else:
                # Adversarial Evasion Shield (Fail-Closed):
                # If a statement asserts an unhedged biological link or phenotypic transition
                # without observational qualifiers ("associated with", "correlated with"),
                # refuse silent downgrade to DESCRIPTIVE.
                has_phenotype_transition = any(w in text_lower for w in (
                    "polariz", "differentiat", "fate", "exhaustion", "activation", "remodel", "plasticity",
                    "极化", "分化", "活化", "耗竭", "重塑"
                ))
                has_causal_intent_marker = any(w in text_lower for w in (
                    "culprit", "culprits", "mastermind", "responsible", "key factor", "primary factor",
                    "switch", "push", "pivot", "主要推手", "幕后黑手", "祸首", "决定性"
                ))
                # Merely naming two entities or a phenotype is not a causal assertion.
                # The fallback requires an actual causal-intent marker; ordinary
                # enrichment/descriptive statements retain their evidence requirements.
                if has_causal_intent_marker and not is_epistemic_disclaimer:
                    direction = Directionality.DIRECTED_FORWARD
                    causal_strength = CausalStrength.COUNTERFACTUAL_CAUSAL
                    if has_phenotype_transition:
                        rel_type = ClaimRelationshipType.PHENOTYPE_DRIVER
                        mech_depth = MechanismDepth.SIGNALING_CASCADE
                        claim_class = ClaimClass.MECHANISTIC
                    else:
                        rel_type = ClaimRelationshipType.REGULATORY_EFFECT
                        mech_depth = MechanismDepth.SIGNALING_CASCADE
                        claim_class = ClaimClass.CAUSAL

                    parts = re.split(r"\b(?:behind|for|of|in|to|towards?)\b", clean_text, maxsplit=1, flags=re.I)
                    subject_name = parts[0].strip() or clean_text
                    object_name = parts[1].strip() if len(parts) > 1 else None
                    if population_scope and object_name:
                        object_name = re.sub(rf"\b(?:in|across)\s+{re.escape(population_scope)}\b.*", "", object_name, flags=re.IGNORECASE).strip()
                    if object_name:
                        object_name = object_name.rstrip(". ,;")
                    adversarial_evasion_detected = True
                else:
                    # Default fallback extraction
                    subject_name = clean_text
                    object_name = None
                    direction = Directionality.UNDIRECTED
                    causal_strength = CausalStrength.ASSOCIATIONAL
                    rel_type = ClaimRelationshipType.CORRELATION
                    claim_class = ClaimClass.DESCRIPTIVE

        # Only a scoped epistemic limitation suppresses asserted causality.
        # Negative biological assertions retain their requested evidence burden.
        if is_epistemic_disclaimer and not is_negative_assertion and cls.is_scoped_disclaimer(clean_text) and causal_strength in (
            CausalStrength.COUNTERFACTUAL_CAUSAL,
            CausalStrength.HYPOTHESIZED_CAUSAL,
            CausalStrength.MECHANISTIC_DRIVER,
        ):
            causal_strength = CausalStrength.NONE
            rel_type = ClaimRelationshipType.CORRELATION
            claim_class = ClaimClass.DESCRIPTIVE
            mech_depth = MechanismDepth.BLACK_BOX

        # Association type fine-tuning
        if "spatial" in text_lower or "colocaliz" in text_lower or "moran" in text_lower or "niche" in text_lower:
            assoc_type = AssociationType.SPATIAL_COLOCALIZATION
            if claim_class == ClaimClass.ASSOCIATION:
                claim_class = ClaimClass.SPATIAL_DEPENDENCY
        elif "ligand" in text_lower or "receptor" in text_lower or "cellchat" in text_lower or "cellphone" in text_lower:
            assoc_type = AssociationType.LIGAND_RECEPTOR_INFERENCE
        elif "deg" in text_lower or "differential" in text_lower or "deseq" in text_lower:
            assoc_type = AssociationType.DIFFERENTIAL_EXPRESSION
            if gen_scope == GeneralizationScope.POPULATION_GENERAL:
                claim_class = ClaimClass.POPULATION_EFFECT
        elif "hazard" in text_lower or "survival" in text_lower or "kaplan" in text_lower:
            assoc_type = AssociationType.SURVIVAL_HAZARD

        # Model substitution check
        if any(m in text_lower for m in ("esm-2", "alphafold", "protbert")) and any(
            h in text_lower for h in ("blosum", "heuristic", "substitution matrix")
        ):
            rel_type = ClaimRelationshipType.MODEL_FIDELITY

        # Subject entity features
        features = []
        token_matches = re.findall(r"\b([A-Za-z0-9_]+[\+\-]?)", subject_name)
        for tok in token_matches:
            if tok.endswith(("+", "-")) or any(m in tok.upper() for m in ("CD8", "CD4", "CD3", "CD19", "CD20", "CD14", "CD56", "CD68", "CXCL13", "FOXP3", "PD1", "CTLA4")):
                if tok not in features and tok.lower() not in ("cells", "t", "b"):
                    features.append(tok)

        subj_entity = ScientificEntity(
            name=subject_name,
            entity_type="cell_population" if "cell" in subject_name.lower() else "biological_entity",
            features=features,
            raw_span=subject_name,
        )

        obj_entity = None
        if object_name:
            obj_features = []
            obj_token_matches = re.findall(r"\b([A-Za-z0-9_]+[\+\-]?)", object_name)
            for tok in obj_token_matches:
                if tok.endswith(("+", "-")) or any(m in tok.upper() for m in ("CD8", "CD4", "CD3", "CD19", "CD20", "CD14", "CD56", "CD68", "CXCL13", "FOXP3", "PD1", "CTLA4")):
                    if tok not in obj_features and tok.lower() not in ("cells", "t", "b"):
                        obj_features.append(tok)

            obj_entity = ScientificEntity(
                name=object_name,
                entity_type="phenotype" if "polariz" in object_name.lower() or "differentiat" in object_name.lower() else "biological_entity",
                features=obj_features,
                raw_span=object_name,
            )

        # Explicit claim class resolution & conflict preservation
        meta_dict = dict(data_metadata or {})
        if explicit_claim_class is None and data_metadata:
            explicit_claim_class = data_metadata.get("claim_class") or data_metadata.get("requested_claim_class")

        has_claim_conflict = False
        conflict_details = None

        if explicit_claim_class is not None:
            norm_explicit = explicit_claim_class
            if isinstance(norm_explicit, str):
                s = norm_explicit.lower().strip()
                if s in ("population", "population_effect"):
                    norm_explicit = ClaimClass.POPULATION_EFFECT
                elif s == "causal":
                    norm_explicit = ClaimClass.CAUSAL
                elif s in ("clinical", "clinical_actionability"):
                    norm_explicit = ClaimClass.CLINICAL_ACTIONABILITY
                elif s == "mechanistic":
                    norm_explicit = ClaimClass.MECHANISTIC
                elif s in ("spatial", "spatial_dependency"):
                    norm_explicit = ClaimClass.SPATIAL_DEPENDENCY
                elif s == "cell_identity":
                    norm_explicit = ClaimClass.CELL_IDENTITY
                elif s == "association":
                    norm_explicit = ClaimClass.ASSOCIATION
                elif s == "descriptive":
                    norm_explicit = ClaimClass.DESCRIPTIVE
                else:
                    try:
                        norm_explicit = ClaimClass(s)
                    except ValueError:
                        # Model fidelity is a relationship, not a supported
                        # claim class. Preserve unsupported input for review;
                        # never invent a class or silently infer an easier one.
                        norm_explicit = ClaimClass.UNSPECIFIED
                        meta_dict["unsupported_explicit_claim_class"] = str(explicit_claim_class)

            if isinstance(norm_explicit, ClaimClass):
                if norm_explicit != claim_class:
                    has_claim_conflict = True
                    conflict_details = (
                        f"Explicit claim class '{norm_explicit.value}' differs from text-inferred "
                        f"class '{claim_class.value}'. Preserving explicit '{norm_explicit.value}' without silent downgrade."
                    )
                # CRITICAL: Preserve explicit claim class! Never silently downgrade to descriptive!
                claim_class = norm_explicit
                if claim_class == ClaimClass.POPULATION_EFFECT:
                    gen_scope = GeneralizationScope.POPULATION_GENERAL
                elif claim_class in (ClaimClass.CAUSAL, ClaimClass.MECHANISTIC):
                    if causal_strength in (CausalStrength.NONE, CausalStrength.ASSOCIATIONAL):
                        causal_strength = CausalStrength.COUNTERFACTUAL_CAUSAL
                elif claim_class == ClaimClass.CLINICAL_ACTIONABILITY:
                    if clinical_act == ClinicalActionability.NONE:
                        clinical_act = ClinicalActionability.EXPLORATORY_BIOMARKER

        if has_claim_conflict:
            meta_dict["has_claim_conflict"] = True
            meta_dict["conflict_details"] = conflict_details

        if adversarial_evasion_detected:
            meta_dict["adversarial_evasion_detected"] = True
            meta_dict["evasion_shield_rationale"] = (
                "Potential causal/mechanistic assertion with non-standard phrasing evaluated fail-closed"
            )

        return ScientificClaimIR(
            claim_id=cid,
            source_text=clean_text,
            subject_entity=subj_entity,
            object_entity=obj_entity,
            relationship=rel_type,
            direction=direction,
            population_scope=population_scope,
            generalization_scope=gen_scope,
            association_type=assoc_type,
            causal_strength=causal_strength,
            mechanism_depth=mech_depth,
            clinical_actionability=clinical_act,
            claim_class=claim_class,
            qualifiers=qualifiers,
            negated=negated,
            negation_type=negation_type,
            is_epistemic_disclaimer=is_epistemic_disclaimer,
            is_negative_assertion=is_negative_assertion,
            metadata=meta_dict,
        )


# ==============================================================================
# 2b. Assertive Causal-Language Detector (shared with BNS-013 verify)
# ==============================================================================

_ASSERTIVE_CAUSAL_RE = re.compile(
    r"\b(?:drives?|driven|causes?|caused|induces?|induced|triggers?|triggered|"
    r"proves?|proven|proving|mechanism of action|is causal|confers?)\b",
    re.IGNORECASE,
)

# A negation cue within the preceding window (same clause, <=48 chars) scopes
# the causal term into a disclaimer: "does not drive", "cannot prove ... caused".
_NEGATION_CUE_RE = re.compile(
    r"\b(?:not|no|never|cannot|can't|without|fails? to|unable to|"
    r"neither)\b[^.;]{0,48}$",
    re.IGNORECASE,
)


def _scope_clauses(text: str) -> List[str]:
    """Split supported independent clauses without splitting a dated subject preamble."""
    clauses = []
    start = 0
    for boundary in _CLAUSE_BOUNDARY_RE.finditer(text):
        prefix = text[start:boundary.start()]
        if (
            boundary.group(0).lower() == "since"
            and re.match(r"\s+(?:\d{4}|then)\b", text[boundary.end():], re.I)
            and not any(re.search(pattern, prefix, re.I) for pattern in DeterministicClaimParser._ABSENCE_OF_EVIDENCE_PATTERNS)
            and not _NEGATION_CUE_RE.search(prefix)
        ):
            # "Evidence gathered since 2020 cannot prove ..." is a single
            # limitation. Once a disclaimer has started, a later "since" must
            # end its scope even when the next assertion begins with a date.
            continue
        clauses.append(prefix)
        start = boundary.end()
    clauses.append(text[start:])
    return clauses


def detect_assertive_causal_language(text: str) -> Optional[str]:
    """
    Return the first ASSERTIVE causal-language hit in `text`, or None.

    Hits preceded by a negation cue (e.g. "does not drive", "cannot prove ...
    caused", "no evidence that X induces Y") are disclaimers, not assertions,
    and are skipped. This is the single shared detector behind `bionexus verify`
    so the firewall never flags honest negative findings as overclaims.
    Heuristic by design: documented precision/recall limits (INV-009).
    """
    # A limitation before "because", "since", "but", etc. cannot negate a
    # causal assertion in the following clause. Keep the existing short-window
    # heuristic inside each explicitly delimited clause, including local negation.
    for clause in _scope_clauses(text):
        for match in _ASSERTIVE_CAUSAL_RE.finditer(clause):
            window = clause[max(0, match.start() - 48):match.start()]
            if _NEGATION_CUE_RE.search(window):
                continue
            return match.group(0)
    return None


# ==============================================================================
# 3. Deterministic Warrant Engine
# ==============================================================================



def decompose_compound_claim(text: str) -> List[ScientificClaimIR]:
    """Decompose complex compound scientific prose into atomic ScientificClaimIR records.

    Splits multi-clause sentences linked by causal/mechanistic connectives (e.g.
    'which drives', 'and thereby induces', 'leading to', ';') and parses each
    atomic proposition while preserving relational context.
    """
    if not text or not text.strip():
        return []

    split_pattern = re.compile(
        r"(?:;|\bwhich\s+(?:in\s+turn\s+)?(?:drives|causes|induces|promotes|suppresses|mediates|suggests|indicates|leads\s+to)\b|"
        r"\band\s+thereby\b|\band\s+consequently\b|\band\s+therefore\b|\bmoreover,\s+|\bfurthermore,\s+)",
        re.IGNORECASE,
    )

    raw_clauses = split_pattern.split(text)
    clauses = [c.strip() for c in raw_clauses if c.strip() and len(c.strip()) > 3]

    if not clauses:
        clauses = [text.strip()]

    decomposed: List[ScientificClaimIR] = []

    for i, clause in enumerate(clauses):
        claim_id = f"atomic_claim_{i+1:02d}"
        atomic_ir = DeterministicClaimParser.parse(clause, claim_id=claim_id)
        if len(clauses) > 1:
            atomic_ir.qualifiers.append(f"decomposed_clause_{i+1}_of_{len(clauses)}")
            if i > 0:
                atomic_ir.qualifiers.append(f"upstream_clause:atomic_claim_{i:02d}")
        decomposed.append(atomic_ir)

    return decomposed



ScientificClaimParser = DeterministicClaimParser


class HybridClaimParser:
    """
    Two-stage hybrid parser combining deterministic rule-based parsing with
    an optional pluggable LLM-based claim extractor.

    Enforces Fail-Closed Semantic Reconciliation:
    - Fast path: Deterministic pattern matching + Adversarial Evasion Shield.
    - LLM path (optional): Pluggable high-capacity semantic parser (e.g. Ollama,
      vLLM, or proprietary LLMs).
    - Fail-Closed Reconciliation:
      If EITHER the rule-based shield OR the LLM extractor detects causal,
      mechanistic, or directional assertions, the claim is elevated to that
      higher epistemic class. A claim is NEVER downgraded to DESCRIPTIVE
      unless both systems agree it is purely descriptive and no adversarial
      evasion flags are raised.
    """

    def __init__(
        self,
        llm_extractor: Optional[Callable[[str], Dict[str, Any]]] = None,
        fail_closed: bool = True,
    ) -> None:
        self.llm_extractor = llm_extractor
        self.fail_closed = fail_closed

    def parse(
        self,
        text: str,
        claim_id: Optional[str] = None,
        explicit_claim_class: Optional[Union[str, ClaimClass]] = None,
        data_metadata: Optional[Dict[str, Any]] = None,
    ) -> ScientificClaimIR:
        """Parse claim using rule parser and harmonize with LLM extractor if provided."""
        rule_ir = DeterministicClaimParser.parse(
            text,
            claim_id=claim_id,
            explicit_claim_class=explicit_claim_class,
            data_metadata=data_metadata,
        )

        if not self.llm_extractor:
            return rule_ir

        try:
            llm_result = self.llm_extractor(text)
        except Exception as e:
            rule_ir.metadata["llm_extraction_error"] = str(e)
            return rule_ir

        if not isinstance(llm_result, dict):
            return rule_ir

        return self._harmonize(rule_ir, llm_result)

    def _harmonize(self, base_ir: ScientificClaimIR, llm_data: Dict[str, Any]) -> ScientificClaimIR:
        """Harmonize base rule IR with LLM extracted attributes under fail-closed semantics."""
        meta = dict(base_ir.metadata)
        meta["llm_extracted"] = True
        meta["llm_raw_output"] = llm_data

        target_claim_class = base_ir.claim_class
        target_causal_strength = base_ir.causal_strength
        target_relationship = base_ir.relationship
        target_direction = base_ir.direction
        target_subj = base_ir.subject_entity
        target_obj = base_ir.object_entity

        llm_claim_class_str = str(llm_data.get("claim_class", "")).lower().strip()
        llm_is_causal = any(c in llm_claim_class_str for c in ("causal", "mechanistic", "driver")) or bool(
            llm_data.get("is_causal")
        )

        rule_is_causal = (
            base_ir.claim_class in (ClaimClass.CAUSAL, ClaimClass.MECHANISTIC)
            or base_ir.causal_strength in (CausalStrength.COUNTERFACTUAL_CAUSAL, CausalStrength.MECHANISTIC_DRIVER)
        )

        if self.fail_closed:
            # If EITHER flags causality, fail closed to CAUSAL/MECHANISTIC
            if llm_is_causal or rule_is_causal:
                if "mechanistic" in llm_claim_class_str or base_ir.claim_class == ClaimClass.MECHANISTIC:
                    target_claim_class = ClaimClass.MECHANISTIC
                else:
                    target_claim_class = ClaimClass.CAUSAL

                if target_causal_strength in (CausalStrength.NONE, CausalStrength.ASSOCIATIONAL):
                    target_causal_strength = CausalStrength.COUNTERFACTUAL_CAUSAL
                if target_direction == Directionality.UNDIRECTED:
                    target_direction = Directionality.DIRECTED_FORWARD
                if target_relationship == ClaimRelationshipType.CORRELATION:
                    target_relationship = ClaimRelationshipType.REGULATORY_EFFECT
            elif llm_claim_class_str in ("spatial", "spatial_dependency"):
                target_claim_class = ClaimClass.SPATIAL_DEPENDENCY
        else:
            if "causal" in llm_claim_class_str:
                target_claim_class = ClaimClass.CAUSAL
            elif "mechanistic" in llm_claim_class_str:
                target_claim_class = ClaimClass.MECHANISTIC
            elif "spatial" in llm_claim_class_str:
                target_claim_class = ClaimClass.SPATIAL_DEPENDENCY

        # Entity refinement from LLM if base parser fell back to generic placeholders
        if target_subj.name in ("Subject", "Entity A", base_ir.source_text) and llm_data.get("subject"):
            target_subj = ScientificEntity(
                name=str(llm_data["subject"]).strip(),
                entity_type=target_subj.entity_type,
                features=target_subj.features,
                raw_span=str(llm_data["subject"]).strip(),
            )

        if (target_obj is None or target_obj.name in ("Entity B", None)) and llm_data.get("object"):
            target_obj = ScientificEntity(
                name=str(llm_data["object"]).strip(),
                entity_type="phenotype" if "polariz" in str(llm_data["object"]).lower() else "biological_entity",
                features=[],
                raw_span=str(llm_data["object"]).strip(),
            )

        base_ir.claim_class = target_claim_class
        base_ir.causal_strength = target_causal_strength
        base_ir.relationship = target_relationship
        base_ir.direction = target_direction
        base_ir.subject_entity = target_subj
        base_ir.object_entity = target_obj
        base_ir.metadata = meta

        return base_ir


