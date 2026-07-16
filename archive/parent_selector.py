"""
Parent selection for the Darwin Gödel Machine.

Implements the paper's parent-selection formula exactly:
  s_i = 1 / (1 + exp(-lambda * (alpha_i - alpha_0)))
  h_i = 1 / (1 + n_i)   where n_i = number of valid children of agent i
  w_i = s_i * h_i
  p_i = w_i / sum(w_j)
  sample without replacement when n_parents > 1
"""

import math
import random
from typing import List, Optional

from .agent_archive import AgentArchive, ArchivedAgent


class ParentSelector:
    """
    Selects parent agents from the archive using the DGM paper formula.

    Constructor args:
        lam: lambda parameter for the sigmoid (default 10)
        alpha_0: midpoint of the sigmoid (default 0.5)
        require_non_regression: when true, exclude children that regress
            relative to their parent on average score and do not improve overall.
        require_per_benchmark_non_regression: when true, exclude a child if any
            parent benchmark score regresses, even when its average improves.
        regression_tolerance: small tolerance for floating-point score deltas.
        reject_score_ties: when true, exclude children whose average score ties
            their parent's score instead of improving it.
        elite_selection_probability: optional probability of selecting the
            highest-scoring eligible parent for single-parent draws before
            falling back to the paper's stochastic formula.
        focus_agent_ids: optional list of agent IDs to exploit before falling
            back to the paper's stochastic formula.
        focus_include_descendants: when true, eligible descendants of focused
            roots participate in the focused exploitation pool.
        focus_selection_probability: probability of selecting from
            focus_agent_ids for single-parent draws when any focused agent is
            eligible.
    """

    def __init__(
        self,
        lam: float = 10.0,
        alpha_0: float = 0.5,
        require_non_regression: bool = False,
        require_per_benchmark_non_regression: bool = False,
        regression_tolerance: float = 0.0,
        reject_score_ties: bool = False,
        elite_selection_probability: float = 0.0,
        focus_agent_ids: Optional[List[str]] = None,
        focus_selection_probability: float = 0.0,
        focus_include_descendants: bool = False,
    ):
        self.lam = lam
        self.alpha_0 = alpha_0
        self.require_non_regression = require_non_regression
        self.require_per_benchmark_non_regression = (
            require_per_benchmark_non_regression
        )
        self.regression_tolerance = regression_tolerance
        self.reject_score_ties = reject_score_ties
        self.elite_selection_probability = max(
            0.0,
            min(1.0, elite_selection_probability),
        )
        self.focus_agent_ids = set(focus_agent_ids or [])
        self.focus_include_descendants = focus_include_descendants
        self.focus_selection_probability = max(
            0.0,
            min(1.0, focus_selection_probability),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select_parents(
        self,
        archive: AgentArchive,
        n_parents: int = 1
    ) -> List[ArchivedAgent]:
        """
        Select parent agents from the archive.

        Args:
            archive: AgentArchive instance (agents have .agent_id, .parent_id,
                     .average_score, .is_valid).
            n_parents: How many parents to select (without replacement when > 1).

        Returns:
            List of selected ArchivedAgent objects (may be shorter than n_parents
            if the archive has fewer valid agents).
        """
        eligible = [
            a
            for a in archive.agents.values()
            if a.is_valid and self._passes_regression_filter(a, archive)
        ]
        if not eligible:
            return []

        # Build child-count map: count VALID children per agent
        child_counts: dict = {a.agent_id: 0 for a in eligible}
        for a in archive.agents.values():
            if a.is_valid and a.parent_id and a.parent_id in child_counts:
                child_counts[a.parent_id] += 1

        k = min(n_parents, len(eligible))
        if (
            k == 1
            and self.focus_agent_ids
            and self.focus_selection_probability > 0
        ):
            focused = [
                a
                for a in eligible
                if self._is_focused_agent(a, archive)
            ]
            if focused and random.random() < self.focus_selection_probability:
                return [
                    max(
                        focused,
                        key=lambda a: (
                            a.average_score,
                            -child_counts.get(a.agent_id, 0),
                            -a.generation,
                        ),
                    )
                ]

        if k == 1 and self.elite_selection_probability > 0:
            if random.random() < self.elite_selection_probability:
                return [max(eligible, key=lambda a: (a.average_score, -a.generation))]

        # Compute weights
        weights = []
        for a in eligible:
            s_i = 1.0 / (1.0 + math.exp(-self.lam * (a.average_score - self.alpha_0)))
            h_i = 1.0 / (1.0 + child_counts[a.agent_id])
            weights.append(s_i * h_i)

        total_w = sum(weights)
        if total_w == 0.0:
            # Degenerate: all weights zero → uniform
            weights = [1.0 / len(eligible)] * len(eligible)
            total_w = 1.0

        # Normalised probabilities
        probs = [w / total_w for w in weights]

        # Sample without replacement
        if k == 1:
            # Fast path for the common single-parent case
            r = random.random()
            cumulative = 0.0
            selected_agent = eligible[-1]
            for agent, p in zip(eligible, probs):
                cumulative += p
                if r <= cumulative:
                    selected_agent = agent
                    break
            return [selected_agent]

        # Weighted sampling without replacement via repeated normalised draws
        pool = list(zip(eligible, probs))
        selected = []
        for _ in range(k):
            if not pool:
                break
            agents_p, ps = zip(*pool)
            total = sum(ps)
            normalised = [p / total for p in ps]
            r = random.random()
            cumulative = 0.0
            chosen_idx = len(agents_p) - 1
            for idx, p in enumerate(normalised):
                cumulative += p
                if r <= cumulative:
                    chosen_idx = idx
                    break
            selected.append(agents_p[chosen_idx])
            pool = [(a, p) for i, (a, p) in enumerate(pool) if i != chosen_idx]

        return selected

    def _is_focused_agent(
        self,
        agent: ArchivedAgent,
        archive: AgentArchive,
    ) -> bool:
        """Return whether an agent is a focused root or its descendant."""
        current: Optional[ArchivedAgent] = agent
        seen = set()
        while current is not None and current.agent_id not in seen:
            seen.add(current.agent_id)
            if current.agent_id in self.focus_agent_ids:
                return True
            if not self.focus_include_descendants or not current.parent_id:
                return False
            current = archive.get_agent(current.parent_id)
        return False

    def _passes_regression_filter(
        self,
        agent: ArchivedAgent,
        archive: AgentArchive,
    ) -> bool:
        """Return whether an agent can be selected under the regression gate."""
        if not self.require_non_regression:
            return True
        if not agent.parent_id:
            return True

        parent = archive.get_agent(agent.parent_id)
        if parent is None:
            return True

        tolerance = self.regression_tolerance
        if self.require_per_benchmark_non_regression:
            for benchmark, parent_score in parent.benchmark_scores.items():
                child_score = agent.benchmark_scores.get(benchmark, 0.0)
                if child_score < parent_score - tolerance:
                    return False

        if agent.average_score > parent.average_score + tolerance:
            return True

        if agent.average_score < parent.average_score - tolerance:
            return False

        if self.reject_score_ties:
            return False

        for benchmark, parent_score in parent.benchmark_scores.items():
            child_score = agent.benchmark_scores.get(benchmark, 0.0)
            if child_score < parent_score - tolerance:
                return False

        return True
