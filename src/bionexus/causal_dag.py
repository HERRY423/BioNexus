"""
BioNexus Causal Epistemic DAG & Structural Identifiability Engine.

Implements structural causal graph (SCM) analysis, d-separation, backdoor criterion,
collider stratification risk detection, and causal claim warrant evaluation.

Theoretical foundations:
- Pearl, J. (2009). Causality: Models, Reasoning, and Inference. Cambridge University Press.
- Hernán, M. A., & Robins, J. M. (2020). Causal Inference: What If. Chapman & Hall/CRC.
- Cinelli, C., Forney, A., & Pearl, J. (2022). A Crash Course in Good and Bad Controls.
  Sociological Methods & Research, 51(3), 1371-1404.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from bionexus.contracts import ConclusionMaturity
from bionexus.evidence_model import ClaimClass


class NodeType(str, Enum):
    """Semantic role of a variable in a biological causal graph."""

    TREATMENT = "treatment"  # Perturbation, drug, disease state, genotype
    OUTCOME = "outcome"  # Measured phenotype, expression, cell state, survival
    OBSERVED_CONFOUNDER = "observed_confounder"  # Batch, donor, sex, age, library depth
    UNOBSERVED_CONFOUNDER = "unobserved_confounder"  # Latent niche effect, microenvironment
    MEDIATOR = "mediator"  # Intermediate signaling molecule or downstream pathway
    COLLIDER_SELECTION = "collider_selection"  # Survival selection, cluster-subset filtering
    COVARIATE = "covariate"  # General precision covariate
    INSTRUMENT = "instrument"  # Instrumental variable (e.g. eQTL, Mendelian randomization variant)


class CausalViolationType(str, Enum):
    """Specific structural causal fallacies detected in biological workflows."""

    UNBLOCKED_BACKDOOR = "UNBLOCKED_BACKDOOR"
    UNOBSERVED_CONFOUNDING = "UNOBSERVED_CONFOUNDING"
    COLLIDER_STRATIFICATION = "COLLIDER_STRATIFICATION"
    MEDIATOR_OVERADJUSTMENT = "MEDIATOR_OVERADJUSTMENT"
    DESCENDANT_OF_TREATMENT_ADJUSTED = "DESCENDANT_OF_TREATMENT_ADJUSTED"
    CYCLIC_STRUCTURE_DETECTED = "CYCLIC_STRUCTURE_DETECTED"
    UNDEFINED_TREATMENT_OR_OUTCOME = "UNDEFINED_TREATMENT_OR_OUTCOME"
    INVALID_INSTRUMENT_NOT_ASSOCIATED = "INVALID_INSTRUMENT_NOT_ASSOCIATED"
    INVALID_INSTRUMENT_EXCLUSION_VIOLATED = "INVALID_INSTRUMENT_EXCLUSION_VIOLATED"
    INVALID_INSTRUMENT_CONFOUNDED = "INVALID_INSTRUMENT_CONFOUNDED"
    FRONTDOOR_CONDITIONS_VIOLATED = "FRONTDOOR_CONDITIONS_VIOLATED"


@dataclass
class CausalNode:
    """A node in the biological causal DAG."""

    name: str
    node_type: NodeType = NodeType.COVARIATE
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CausalEdge:
    """A directed causal influence X -> Y in the graph."""

    source: str
    target: str
    directed: bool = True
    mechanism: str = ""


@dataclass
class CausalWarrantResult:
    """Verdict on whether a causal or associational claim is structurally warranted."""

    is_warranted: bool
    requested_claim_class: str
    warranted_claim_class: str
    maturity_ceiling: str
    violations: List[str] = field(default_factory=list)
    open_backdoor_paths: List[List[str]] = field(default_factory=list)
    collider_risk_paths: List[List[str]] = field(default_factory=list)
    recommended_adjustment_set: List[str] = field(default_factory=list)
    identification_method: str = "backdoor"  # "backdoor", "frontdoor", "instrumental_variable", "unidentifiable"
    frontdoor_mediator: Optional[str] = None
    valid_instrument: Optional[str] = None
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_warranted": self.is_warranted,
            "requested_claim_class": self.requested_claim_class,
            "warranted_claim_class": self.warranted_claim_class,
            "maturity_ceiling": self.maturity_ceiling,
            "violations": self.violations,
            "open_backdoor_paths": self.open_backdoor_paths,
            "collider_risk_paths": self.collider_risk_paths,
            "recommended_adjustment_set": self.recommended_adjustment_set,
            "identification_method": self.identification_method,
            "frontdoor_mediator": self.frontdoor_mediator,
            "valid_instrument": self.valid_instrument,
            "rationale": self.rationale,
        }


class CausalDAG:
    """Directed Acyclic Graph with structural causal reasoning capabilities."""

    def __init__(self, name: str = "BioCausalDAG") -> None:
        self.name = name
        self.nodes: Dict[str, CausalNode] = {}
        self.edges: List[CausalEdge] = []
        self._adj_out: Dict[str, Set[str]] = {}
        self._adj_in: Dict[str, Set[str]] = {}
        self._undirected_adj: Dict[str, Set[str]] = {}

    def add_node(
        self,
        name: str,
        node_type: Union[NodeType, str] = NodeType.COVARIATE,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CausalNode:
        if isinstance(node_type, str):
            node_type = NodeType(node_type)
        node = CausalNode(
            name=name,
            node_type=node_type,
            description=description,
            metadata=metadata or {},
        )
        self.nodes[name] = node
        self._adj_out.setdefault(name, set())
        self._adj_in.setdefault(name, set())
        self._undirected_adj.setdefault(name, set())
        return node

    def add_edge(
        self,
        source: str,
        target: str,
        directed: bool = True,
        mechanism: str = "",
    ) -> CausalEdge:
        if source not in self.nodes:
            self.add_node(source)
        if target not in self.nodes:
            self.add_node(target)

        edge = CausalEdge(source=source, target=target, directed=directed, mechanism=mechanism)
        self.edges.append(edge)

        self._adj_out[source].add(target)
        self._adj_in[target].add(source)
        self._undirected_adj[source].add(target)
        self._undirected_adj[target].add(source)

        if not directed:
            self._adj_out[target].add(source)
            self._adj_in[source].add(target)

        return edge

    def parents(self, node: str) -> Set[str]:
        return set(self._adj_in.get(node, set()))

    def children(self, node: str) -> Set[str]:
        return set(self._adj_out.get(node, set()))

    def ancestors(self, node: str) -> Set[str]:
        visited: Set[str] = set()
        queue = list(self.parents(node))
        while queue:
            curr = queue.pop(0)
            if curr not in visited:
                visited.add(curr)
                queue.extend(self.parents(curr) - visited)
        return visited

    def descendants(self, node: str) -> Set[str]:
        visited: Set[str] = set()
        queue = list(self.children(node))
        while queue:
            curr = queue.pop(0)
            if curr not in visited:
                visited.add(curr)
                queue.extend(self.children(curr) - visited)
        return visited

    def all_simple_paths(self, start: str, end: str) -> List[List[str]]:
        """Find all simple undirected paths between start and end."""
        if start not in self.nodes or end not in self.nodes:
            return []

        paths: List[List[str]] = []

        def _dfs(current: str, target: str, current_path: List[str], visited: Set[str]) -> None:
            if current == target:
                paths.append(list(current_path))
                return
            for neighbor in self._undirected_adj.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    current_path.append(neighbor)
                    _dfs(neighbor, target, current_path, visited)
                    current_path.pop()
                    visited.remove(neighbor)

        _dfs(start, end, [start], {start})
        return paths

    def all_directed_paths(self, start: str, end: str) -> List[List[str]]:
        """Find all directed causal paths from start to end (following arrows)."""
        if start not in self.nodes or end not in self.nodes:
            return []

        paths: List[List[str]] = []

        def _dfs(current: str, target: str, current_path: List[str], visited: Set[str]) -> None:
            if current == target:
                paths.append(list(current_path))
                return
            for child in self.children(current):
                if child not in visited:
                    visited.add(child)
                    current_path.append(child)
                    _dfs(child, target, current_path, visited)
                    current_path.pop()
                    visited.remove(child)

        _dfs(start, end, [start], {start})
        return paths

    def is_path_blocked(self, path: List[str], conditioning_set: Set[str]) -> bool:
        """Evaluate if an undirected path is blocked given conditioning_set under d-separation rules.

        For each consecutive triple (p_{i-1}, p_i, p_{i+1}):
        - Chain (-> p_i -> or <- p_i <-) or Fork (<- p_i ->): blocked IF p_i in conditioning_set.
        - Collider (-> p_i <-): blocked IF neither p_i NOR any descendant of p_i is in conditioning_set.
        A path is blocked if AT LEAST ONE triple is blocked.
        """
        if len(path) <= 2:
            return False

        for i in range(1, len(path) - 1):
            prev_node = path[i - 1]
            curr_node = path[i]
            next_node = path[i + 1]

            arrow_in_from_prev = curr_node in self.children(prev_node)
            arrow_in_from_next = curr_node in self.children(next_node)

            is_collider = arrow_in_from_prev and arrow_in_from_next

            if is_collider:
                # Collider: inactive (blocks path) if neither curr_node nor its descendants are conditioned on
                curr_and_desc = {curr_node} | self.descendants(curr_node)
                if not (curr_and_desc & conditioning_set):
                    return True  # Collider is closed -> path is blocked here
            else:
                # Chain or Fork: inactive (blocks path) if curr_node IS conditioned on
                if curr_node in conditioning_set:
                    return True  # Non-collider is conditioned on -> path is blocked here

        return False

    def is_d_separated(self, X: Set[str], Y: Set[str], Z: Set[str]) -> bool:
        """Check whether set X and set Y are d-separated given conditioning set Z."""
        for x in X:
            for y in Y:
                paths = self.all_simple_paths(x, y)
                for path in paths:
                    if not self.is_path_blocked(path, Z):
                        return False
        return True

    def find_backdoor_paths(self, treatment: str, outcome: str) -> List[List[str]]:
        """Find all paths between treatment and outcome that start with an arrow into treatment."""
        paths = self.all_simple_paths(treatment, outcome)
        backdoor_paths: List[List[str]] = []
        for path in paths:
            if len(path) >= 2:
                first_step = path[1]
                # Path enters treatment if treatment is child of first_step (i.e. treatment <- first_step)
                if treatment in self.children(first_step):
                    backdoor_paths.append(path)
        return backdoor_paths

    def backdoor_criterion(
        self,
        treatment: str,
        outcome: str,
        adjustment_set: Set[str],
    ) -> Tuple[bool, List[str], List[List[str]]]:
        """Test if adjustment_set satisfies the Backdoor Criterion for (treatment, outcome).

        Conditions:
        1. No node in adjustment_set is a descendant of treatment.
        2. adjustment_set blocks every backdoor path between treatment and outcome.
        """
        violations: List[str] = []
        open_paths: List[List[str]] = []

        # Condition 1
        treatment_descendants = self.descendants(treatment)
        desc_overlap = adjustment_set & treatment_descendants
        if desc_overlap:
            violations.append(
                f"{CausalViolationType.DESCENDANT_OF_TREATMENT_ADJUSTED.value}: "
                f"Adjustment set contains descendants of treatment: {sorted(desc_overlap)}"
            )

        # Condition 2
        backdoor_paths = self.find_backdoor_paths(treatment, outcome)
        for path in backdoor_paths:
            if not self.is_path_blocked(path, adjustment_set):
                open_paths.append(path)

        if open_paths:
            violations.append(
                f"{CausalViolationType.UNBLOCKED_BACKDOOR.value}: "
                f"{len(open_paths)} unblocked backdoor path(s) remain open."
            )

        return (len(violations) == 0, violations, open_paths)

    def find_minimal_adjustment_set(
        self,
        treatment: str,
        outcome: str,
    ) -> Optional[Set[str]]:
        """Find a minimal sufficient adjustment set using observed confounders/covariates."""
        treatment_desc = self.descendants(treatment)
        candidate_nodes = [
            name
            for name, node in self.nodes.items()
            if name != treatment
            and name != outcome
            and name not in treatment_desc
            and node.node_type != NodeType.UNOBSERVED_CONFOUNDER
        ]

        # Test candidate sets from size 0 upwards
        from itertools import combinations

        for k in range(len(candidate_nodes) + 1):
            for subset in combinations(candidate_nodes, k):
                adj_set = set(subset)
                satisfied, _, _ = self.backdoor_criterion(treatment, outcome, adj_set)
                if satisfied:
                    return adj_set

        return None

    def detect_collider_stratification(
        self,
        treatment: str,
        outcome: str,
        conditioned_set: Set[str],
    ) -> Tuple[bool, List[List[str]]]:
        """Detect if conditioning on any variable opens an otherwise closed collider path."""
        collider_paths: List[List[str]] = []
        paths = self.all_simple_paths(treatment, outcome)

        for path in paths:
            # Check if this path was naturally blocked by a collider but is NOW OPEN
            # due to conditioning on the collider or its descendant
            if self.is_path_blocked(path, set()) and not self.is_path_blocked(path, conditioned_set):
                collider_paths.append(path)

        return (len(collider_paths) > 0, collider_paths)

    def detect_mediator_overadjustment(
        self,
        treatment: str,
        outcome: str,
        conditioned_set: Set[str],
    ) -> List[str]:
        """Detect if conditioning set contains intermediate mediators on direct causal paths."""
        mediators = {
            name
            for name, node in self.nodes.items()
            if node.node_type == NodeType.MEDIATOR
            or (name in self.descendants(treatment) and outcome in self.descendants(name))
        }
        overadjusted = mediators & conditioned_set
        if overadjusted:
            return [
                f"{CausalViolationType.MEDIATOR_OVERADJUSTMENT.value}: "
                f"Controlling for mediator(s) {sorted(overadjusted)} eliminates total causal effect."
            ]
        return []

    def frontdoor_criterion(
        self,
        treatment: str,
        outcome: str,
        mediator: str,
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """Test if mediator satisfies Pearl's Frontdoor Criterion for (treatment, outcome).

        Conditions (Pearl, 1995):
        1. Mediator intercepts all directed paths from treatment to outcome.
        2. There is no unblocked backdoor path from treatment to mediator.
        3. All backdoor paths from mediator to outcome are blocked by {treatment}.
        """
        violations: List[str] = []
        details: Dict[str, Any] = {"mediator": mediator}

        if treatment not in self.nodes or outcome not in self.nodes or mediator not in self.nodes:
            violations.append("All of treatment, outcome, and mediator must exist in DAG.")
            return False, violations, details

        # Condition 1: Intercept all directed paths
        directed_ty = self.all_directed_paths(treatment, outcome)
        if not directed_ty:
            violations.append(
                f"{CausalViolationType.FRONTDOOR_CONDITIONS_VIOLATED.value}: "
                f"No directed causal path exists from treatment '{treatment}' to outcome '{outcome}'."
            )
        else:
            for path in directed_ty:
                if mediator not in path:
                    violations.append(
                        f"{CausalViolationType.FRONTDOOR_CONDITIONS_VIOLATED.value}: "
                        f"Mediator '{mediator}' fails to intercept directed path {path}."
                    )
                    break

        # Condition 2: No unblocked backdoor path from treatment to mediator
        backdoors_tm = self.find_backdoor_paths(treatment, mediator)
        open_tm: List[List[str]] = []
        for path in backdoors_tm:
            if not self.is_path_blocked(path, set()):
                open_tm.append(path)
        if open_tm:
            violations.append(
                f"{CausalViolationType.FRONTDOOR_CONDITIONS_VIOLATED.value}: "
                f"Open backdoor path exists between treatment and mediator: {open_tm}"
            )

        # Condition 3: All backdoor paths from mediator to outcome are blocked by {treatment}
        backdoors_my = self.find_backdoor_paths(mediator, outcome)
        open_my: List[List[str]] = []
        for path in backdoors_my:
            if not self.is_path_blocked(path, {treatment}):
                open_my.append(path)
        if open_my:
            violations.append(
                f"{CausalViolationType.FRONTDOOR_CONDITIONS_VIOLATED.value}: "
                f"Backdoor path from mediator to outcome is not blocked by treatment: {open_my}"
            )

        details["open_treatment_mediator_backdoors"] = open_tm
        details["open_mediator_outcome_backdoors"] = open_my
        details["intercepts_all_directed_paths"] = len(violations) == 0

        return len(violations) == 0, violations, details

    def instrumental_variable_criterion(
        self,
        instrument: str,
        treatment: str,
        outcome: str,
        conditioning_set: Optional[Set[str]] = None,
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """Test if instrument satisfies Instrumental Variable / Mendelian Randomization conditions.

        Conditions:
        1. Relevance: Instrument has a direct or indirect causal path to treatment.
        2. Exclusion Restriction: Instrument affects outcome ONLY through treatment
           (no direct Z -> Y edge, and all directed paths from Z to Y pass through treatment).
        3. Independence / Unconfoundedness: Instrument is independent of unmeasured confounders of (T, Y).
        """
        violations: List[str] = []
        conditioned = set(conditioning_set or set())
        details: Dict[str, Any] = {"instrument": instrument}

        if instrument not in self.nodes or treatment not in self.nodes or outcome not in self.nodes:
            violations.append("All of instrument, treatment, and outcome must exist in DAG.")
            return False, violations, details

        # 1. Relevance
        directed_zt = self.all_directed_paths(instrument, treatment)
        if not directed_zt:
            violations.append(
                f"{CausalViolationType.INVALID_INSTRUMENT_NOT_ASSOCIATED.value}: "
                f"Instrument '{instrument}' does not causally influence treatment '{treatment}'."
            )

        # 2. Exclusion Restriction: No direct edge Z -> Y, and all paths Z -> Y go through treatment
        if outcome in self.children(instrument):
            violations.append(
                f"{CausalViolationType.INVALID_INSTRUMENT_EXCLUSION_VIOLATED.value}: "
                f"Instrument '{instrument}' has a direct pleiotropic edge to outcome '{outcome}'."
            )

        directed_zy = self.all_directed_paths(instrument, outcome)
        for path in directed_zy:
            if treatment not in path:
                violations.append(
                    f"{CausalViolationType.INVALID_INSTRUMENT_EXCLUSION_VIOLATED.value}: "
                    f"Direct pleiotropic causal path {path} bypasses treatment '{treatment}'."
                )
                break

        # 3. Independence / Unconfoundedness: Check for open backdoor between Z and Y
        backdoors_zy = self.find_backdoor_paths(instrument, outcome)
        open_zy = [path for path in backdoors_zy if not self.is_path_blocked(path, conditioned)]
        if open_zy:
            violations.append(
                f"{CausalViolationType.INVALID_INSTRUMENT_CONFOUNDED.value}: "
                f"Instrument '{instrument}' shares unblocked confounders with outcome: {open_zy}"
            )

        details["directed_paths_to_treatment"] = directed_zt
        details["open_instrument_backdoors"] = open_zy

        return len(violations) == 0, violations, details

    def evaluate_causal_claim(
        self,
        treatment: str,
        outcome: str,
        conditioned_set: Optional[Set[str]] = None,
        requested_claim_class: Union[ClaimClass, str] = ClaimClass.CAUSAL,
    ) -> CausalWarrantResult:
        """Formal epistemic evaluation of whether a causal claim is warranted by the graph."""
        if isinstance(requested_claim_class, str):
            requested_claim_class = ClaimClass(requested_claim_class)

        conditioned = set(conditioned_set or set())

        if treatment not in self.nodes or outcome not in self.nodes:
            return CausalWarrantResult(
                is_warranted=False,
                requested_claim_class=requested_claim_class.value,
                warranted_claim_class=ClaimClass.DESCRIPTIVE.value,
                maturity_ceiling=ConclusionMaturity.ABSTAIN.value,
                violations=[
                    f"{CausalViolationType.UNDEFINED_TREATMENT_OR_OUTCOME.value}: "
                    f"Treatment '{treatment}' or outcome '{outcome}' not present in DAG."
                ],
                rationale="Causal claim cannot be evaluated without defined treatment and outcome nodes.",
            )

        all_violations: List[str] = []
        is_backdoor_ok, backdoor_violations, open_backdoors = self.backdoor_criterion(
            treatment, outcome, conditioned
        )
        all_violations.extend(backdoor_violations)

        has_collider_risk, collider_paths = self.detect_collider_stratification(
            treatment, outcome, conditioned
        )
        if has_collider_risk:
            all_violations.append(
                f"{CausalViolationType.COLLIDER_STRATIFICATION.value}: "
                f"Conditioning on {sorted(conditioned)} activated {len(collider_paths)} collider path(s)."
            )

        mediator_violations = self.detect_mediator_overadjustment(treatment, outcome, conditioned)
        all_violations.extend(mediator_violations)

        # Check for unobserved confounders pointing directly to treatment and outcome
        unobserved = [
            name
            for name, node in self.nodes.items()
            if node.node_type == NodeType.UNOBSERVED_CONFOUNDER
            and treatment in self.children(name)
            and outcome in self.children(name)
        ]
        if unobserved:
            all_violations.append(
                f"{CausalViolationType.UNOBSERVED_CONFOUNDING.value}: "
                f"Unobserved confounder(s) {unobserved} introduce unblockable confounding bias."
            )

        # Compute recommended adjustment set
        rec_adj = self.find_minimal_adjustment_set(treatment, outcome)
        rec_adj_list = sorted(rec_adj) if rec_adj is not None else []

        # Claim class grading
        is_causal_requested = requested_claim_class in (
            ClaimClass.CAUSAL,
            ClaimClass.MECHANISTIC,
        )

        # Explore Alternative Causal Identifications if Backdoor fails
        frontdoor_candidate: Optional[str] = None
        instrument_candidate: Optional[str] = None

        if all_violations and is_causal_requested:
            # Check Frontdoor Criterion across potential mediators
            potential_mediators = [
                name
                for name, node in self.nodes.items()
                if (node.node_type == NodeType.MEDIATOR or name in self.children(treatment))
                and name != treatment
                and name != outcome
            ]
            for m in potential_mediators:
                fd_ok, _, _ = self.frontdoor_criterion(treatment, outcome, m)
                if fd_ok:
                    frontdoor_candidate = m
                    break

            # Check Instrumental Variable across instruments
            potential_instruments = [
                name
                for name, node in self.nodes.items()
                if node.node_type == NodeType.INSTRUMENT or name in self.parents(treatment)
            ]
            for z in potential_instruments:
                iv_ok, _, _ = self.instrumental_variable_criterion(z, treatment, outcome, conditioned)
                if iv_ok:
                    instrument_candidate = z
                    break

        if not all_violations:
            # Backdoor satisfied, no collider or unobserved confounding
            warranted_class = requested_claim_class.value
            maturity_ceiling = ConclusionMaturity.ROBUST.value
            is_warranted = True
            identification_method = "backdoor"
            rationale = (
                f"Structural Causal Identifiability (Backdoor): Backdoor criterion satisfied for {treatment} -> {outcome}. "
                f"No open backdoor or collider bias detected with conditioning set {sorted(conditioned)}."
            )
        elif frontdoor_candidate:
            # Frontdoor Criterion satisfied despite unobserved confounding!
            warranted_class = requested_claim_class.value
            maturity_ceiling = ConclusionMaturity.SUPPORTED.value
            is_warranted = True
            identification_method = "frontdoor"
            rationale = (
                f"Structural Causal Identifiability (Frontdoor): Causal effect of {treatment} -> {outcome} is identifiable "
                f"via mediator '{frontdoor_candidate}' despite unobserved confounding (Pearl 1995 Frontdoor Criterion)."
            )
        elif instrument_candidate:
            # Instrumental Variable satisfied!
            warranted_class = requested_claim_class.value
            maturity_ceiling = ConclusionMaturity.SUPPORTED.value
            is_warranted = True
            identification_method = "instrumental_variable"
            rationale = (
                f"Structural Causal Identifiability (Instrumental Variable / Mendelian Randomization): "
                f"Causal effect of {treatment} -> {outcome} is identifiable using valid instrument '{instrument_candidate}'."
            )
        else:
            identification_method = "unidentifiable"
            is_warranted = not is_causal_requested
            if is_causal_requested:
                warranted_class = ClaimClass.ASSOCIATION.value
                maturity_ceiling = ConclusionMaturity.FRAGILE.value
                rationale = (
                    f"Causal claim '{requested_claim_class.value}' NOT warranted due to structural confounding / bias: "
                    f"{'; '.join(all_violations)}. Claim capped to '{warranted_class}'."
                )
            else:
                warranted_class = requested_claim_class.value
                maturity_ceiling = ConclusionMaturity.SUPPORTED.value
                rationale = (
                    f"Associational claim '{requested_claim_class.value}' permitted, but causal interpretation prohibited: "
                    f"{'; '.join(all_violations)}."
                )

        return CausalWarrantResult(
            is_warranted=is_warranted,
            requested_claim_class=requested_claim_class.value,
            warranted_claim_class=warranted_class,
            maturity_ceiling=maturity_ceiling,
            violations=all_violations,
            open_backdoor_paths=open_backdoors,
            collider_risk_paths=collider_paths,
            recommended_adjustment_set=rec_adj_list,
            identification_method=identification_method,
            frontdoor_mediator=frontdoor_candidate,
            valid_instrument=instrument_candidate,
            rationale=rationale,
        )
