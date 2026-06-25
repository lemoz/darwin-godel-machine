"""
Unit tests for archive management: AgentArchive and ParentSelector.

Covers the real APIs after the fixer rewrites:
  - AgentArchive.add_agent / get_agent / save+load round-trip / atomicity
  - ParentSelector: hand-computed weights, sampling without replacement,
    empty / all-invalid archive
"""

import math
import random
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import pytest

from archive.agent_archive import AgentArchive, ArchivedAgent
from archive.lineage_visualizer import (
    render_archive_lineage_html,
    render_archive_lineage_svg,
)
from archive.parent_selector import ParentSelector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent_file(tmp_path: Path, name: str = "agent.py") -> Path:
    """Write a minimal agent.py and return its path."""
    p = tmp_path / name
    p.write_text("# minimal\n")
    return p


def _add_agent(archive: AgentArchive, agent_file: Path, **kwargs) -> ArchivedAgent:
    """Thin wrapper so tests don't repeat keyword noise."""
    return archive.add_agent(agent_path=str(agent_file), **kwargs)


def _archived_agent(
    agent_id: str,
    parent_id: Optional[str],
    generation: int,
    score: float,
    is_valid: bool = True,
) -> ArchivedAgent:
    return ArchivedAgent(
        agent_id=agent_id,
        parent_id=parent_id,
        generation=generation,
        source_path=f"/tmp/{agent_id}",
        created_at=f"2026-06-12T00:00:0{generation}",
        benchmark_scores={"bench": score},
        average_score=score,
        is_valid=is_valid,
        metadata={},
    )


# ---------------------------------------------------------------------------
# AgentArchive tests
# ---------------------------------------------------------------------------

class TestAgentArchive:

    def test_add_returns_archived_agent(self, tmp_path):
        archive = AgentArchive(archive_dir=str(tmp_path / "arc"))
        f = _make_agent_file(tmp_path)
        agent = _add_agent(archive, f, benchmark_scores={"b": 0.8})

        assert isinstance(agent, ArchivedAgent)
        assert agent.agent_id in archive.agents
        assert agent.average_score == pytest.approx(0.8)
        assert agent.generation == 0
        assert agent.parent_id is None
        assert agent.is_valid is True

    def test_generation_increments_with_parent(self, tmp_path):
        archive = AgentArchive(archive_dir=str(tmp_path / "arc"))
        f1 = _make_agent_file(tmp_path, "a1.py")
        f2 = _make_agent_file(tmp_path, "a2.py")
        parent = _add_agent(archive, f1)
        child = _add_agent(archive, f2, parent_id=parent.agent_id)

        assert child.parent_id == parent.agent_id
        assert child.generation == 1

    def test_average_score_multiple_benchmarks(self, tmp_path):
        archive = AgentArchive(archive_dir=str(tmp_path / "arc"))
        f = _make_agent_file(tmp_path)
        agent = _add_agent(archive, f, benchmark_scores={"b1": 0.6, "b2": 0.8})

        assert agent.average_score == pytest.approx(0.7)

    def test_average_score_no_benchmarks(self, tmp_path):
        archive = AgentArchive(archive_dir=str(tmp_path / "arc"))
        f = _make_agent_file(tmp_path)
        agent = _add_agent(archive, f)
        assert agent.average_score == 0.0

    def test_save_and_load_round_trip(self, tmp_path):
        arc_dir = tmp_path / "arc"
        archive = AgentArchive(archive_dir=str(arc_dir))
        f1 = _make_agent_file(tmp_path, "a1.py")
        f2 = _make_agent_file(tmp_path, "a2.py")
        a1 = _add_agent(archive, f1, benchmark_scores={"b": 0.5})
        a2 = _add_agent(archive, f2, parent_id=a1.agent_id, benchmark_scores={"b": 0.9})

        # Reload from disk
        archive2 = AgentArchive(archive_dir=str(arc_dir))
        assert len(archive2.agents) == 2
        assert a1.agent_id in archive2.agents
        assert a2.agent_id in archive2.agents
        reloaded_a2 = archive2.agents[a2.agent_id]
        assert reloaded_a2.parent_id == a1.agent_id
        assert reloaded_a2.average_score == pytest.approx(0.9)

    def test_atomic_save_metadata_file_exists(self, tmp_path):
        """Verify _save_archive writes the metadata file (atomicity mechanism present)."""
        arc_dir = tmp_path / "arc"
        archive = AgentArchive(archive_dir=str(arc_dir))
        f = _make_agent_file(tmp_path)
        _add_agent(archive, f)
        assert archive.metadata_file.exists()

    def test_get_agent(self, tmp_path):
        archive = AgentArchive(archive_dir=str(tmp_path / "arc"))
        f = _make_agent_file(tmp_path)
        a = _add_agent(archive, f)
        assert archive.get_agent(a.agent_id) is a
        assert archive.get_agent("nonexistent") is None

    def test_get_valid_agents(self, tmp_path):
        archive = AgentArchive(archive_dir=str(tmp_path / "arc"))
        f1 = _make_agent_file(tmp_path, "v.py")
        f2 = _make_agent_file(tmp_path, "i.py")
        valid = _add_agent(archive, f1, is_valid=True)
        invalid = _add_agent(archive, f2, is_valid=False)

        valids = archive.get_valid_agents()
        assert valid in valids
        assert invalid not in valids

    def test_get_top_agents(self, tmp_path):
        archive = AgentArchive(archive_dir=str(tmp_path / "arc"))
        scores = [0.5, 0.8, 0.3, 0.9, 0.7]
        for i, score in enumerate(scores):
            f = _make_agent_file(tmp_path, f"a{i}.py")
            _add_agent(archive, f, benchmark_scores={"b": score})

        top = archive.get_top_agents(n=3)
        assert len(top) == 3
        assert top[0].average_score == pytest.approx(0.9)
        assert top[1].average_score == pytest.approx(0.8)
        assert top[2].average_score == pytest.approx(0.7)

    def test_get_agent_lineage(self, tmp_path):
        archive = AgentArchive(archive_dir=str(tmp_path / "arc"))
        fa = _make_agent_file(tmp_path, "gp.py")
        fb = _make_agent_file(tmp_path, "p.py")
        fc = _make_agent_file(tmp_path, "c.py")
        gp = _add_agent(archive, fa)
        p = _add_agent(archive, fb, parent_id=gp.agent_id)
        c = _add_agent(archive, fc, parent_id=p.agent_id)

        lineage = archive.get_agent_lineage(c.agent_id)
        assert len(lineage) == 3
        assert lineage[0].agent_id == gp.agent_id
        assert lineage[1].agent_id == p.agent_id
        assert lineage[2].agent_id == c.agent_id

    def test_valid_children_counting(self, tmp_path):
        """Children of an agent increment get_agent_children."""
        archive = AgentArchive(archive_dir=str(tmp_path / "arc"))
        fp = _make_agent_file(tmp_path, "par.py")
        fc1 = _make_agent_file(tmp_path, "c1.py")
        fc2 = _make_agent_file(tmp_path, "c2.py")
        parent = _add_agent(archive, fp)
        _add_agent(archive, fc1, parent_id=parent.agent_id)
        _add_agent(archive, fc2, parent_id=parent.agent_id)

        children = archive.get_agent_children(parent.agent_id)
        assert len(children) == 2


class TestArchiveLineageVisualizer:

    def test_render_archive_lineage_svg_contains_nodes_and_edges(self):
        root = _archived_agent("root-agent", None, 0, 0.4)
        child = _archived_agent("child-agent", root.agent_id, 1, 0.8)

        svg = render_archive_lineage_svg([child, root])

        assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
        assert "agent root-age" in svg
        assert "agent child-ag" in svg
        assert "score 0.800" in svg
        assert "<path" in svg

    def test_render_archive_lineage_svg_empty_archive(self):
        svg = render_archive_lineage_svg([])
        assert "No archived agents yet" in svg

    def test_render_archive_lineage_html_contains_table(self):
        root = _archived_agent("root-agent", None, 0, 0.4)
        child = _archived_agent("child-agent", root.agent_id, 1, 0.8, is_valid=False)

        html = render_archive_lineage_html([root, child])

        assert "<!doctype html>" in html
        assert "<table>" in html
        assert "root-agent" in html
        assert "child-agent" in html
        assert "<td>no</td>" in html


# ---------------------------------------------------------------------------
# ParentSelector tests
# ---------------------------------------------------------------------------

class TestParentSelector:

    # ---- weight-math tests ----

    def _hand_compute_weights(self, scores, child_counts, lam=10.0, alpha_0=0.5):
        """Replicate the paper formula and return normalised probs."""
        weights = []
        for score, nc in zip(scores, child_counts):
            s = 1.0 / (1.0 + math.exp(-lam * (score - alpha_0)))
            h = 1.0 / (1.0 + nc)
            weights.append(s * h)
        total = sum(weights)
        return [w / total for w in weights]

    def _build_archive_with_agents(self, tmp_path, agent_specs):
        """
        agent_specs: list of (score, parent_id_or_None, is_valid)
        Returns (archive, list_of_archived_agents)
        """
        arc_dir = tmp_path / "arc"
        archive = AgentArchive(archive_dir=str(arc_dir))
        agents = []
        for i, (score, parent_id, is_valid) in enumerate(agent_specs):
            f = _make_agent_file(tmp_path, f"a{i}.py")
            a = archive.add_agent(
                agent_path=str(f),
                parent_id=parent_id,
                benchmark_scores={"b": score},
                is_valid=is_valid,
            )
            agents.append(a)
        return archive, agents

    def test_weight_math_three_agents(self, tmp_path):
        """
        Hand-compute expected weights for a 3-agent archive with known
        scores and child counts, then assert ParentSelector agrees.

        Archive:
          agent A: score=0.9, 0 valid children
          agent B: score=0.5, 1 valid child (agent C is child of B)
          agent C: score=0.3, 0 valid children

        lam=10, alpha_0=0.5
        """
        arc_dir = tmp_path / "arc"
        archive = AgentArchive(archive_dir=str(arc_dir))
        fa = _make_agent_file(tmp_path, "a.py")
        fb = _make_agent_file(tmp_path, "b.py")
        fc = _make_agent_file(tmp_path, "c.py")

        agent_a = archive.add_agent(str(fa), benchmark_scores={"b": 0.9}, is_valid=True)
        agent_b = archive.add_agent(str(fb), benchmark_scores={"b": 0.5}, is_valid=True)
        # C is a VALID child of B
        agent_c = archive.add_agent(
            str(fc), parent_id=agent_b.agent_id,
            benchmark_scores={"b": 0.3}, is_valid=True
        )

        # Hand-compute
        # eligible = [A, B, C] in insertion order
        # child counts: A=0, B=1 (C is valid child of B), C=0
        expected_probs = self._hand_compute_weights(
            scores=[0.9, 0.5, 0.3],
            child_counts=[0, 1, 0],
        )

        # Verify via many draws that empirical probs are close
        selector = ParentSelector(lam=10.0, alpha_0=0.5)
        random.seed(42)
        counts = {agent_a.agent_id: 0, agent_b.agent_id: 0, agent_c.agent_id: 0}
        n = 10_000
        for _ in range(n):
            chosen = selector.select_parents(archive, n_parents=1)
            counts[chosen[0].agent_id] += 1

        eligible = [agent_a, agent_b, agent_c]
        for agent, expected_p in zip(eligible, expected_probs):
            empirical_p = counts[agent.agent_id] / n
            assert abs(empirical_p - expected_p) < 0.03, (
                f"agent {agent.agent_id}: expected ~{expected_p:.3f}, got {empirical_p:.3f}"
            )

    def test_sampling_without_replacement_returns_distinct(self, tmp_path):
        arc_dir = tmp_path / "arc"
        archive = AgentArchive(archive_dir=str(arc_dir))
        for i in range(5):
            f = _make_agent_file(tmp_path, f"a{i}.py")
            archive.add_agent(str(f), benchmark_scores={"b": 0.1 * (i + 1)}, is_valid=True)

        selector = ParentSelector()
        random.seed(7)
        parents = selector.select_parents(archive, n_parents=3)
        assert len(parents) == 3
        ids = [p.agent_id for p in parents]
        assert len(set(ids)) == 3, "Parents should be distinct (sampling without replacement)"

    def test_empty_archive_returns_empty_list(self, tmp_path):
        archive = AgentArchive(archive_dir=str(tmp_path / "arc"))
        selector = ParentSelector()
        result = selector.select_parents(archive, n_parents=1)
        assert result == []

    def test_all_invalid_archive_returns_empty_list(self, tmp_path):
        archive = AgentArchive(archive_dir=str(tmp_path / "arc"))
        for i in range(3):
            f = _make_agent_file(tmp_path, f"i{i}.py")
            archive.add_agent(str(f), is_valid=False)

        selector = ParentSelector()
        result = selector.select_parents(archive, n_parents=1)
        assert result == []

    def test_n_parents_exceeds_eligible_returns_all(self, tmp_path):
        """If n_parents > eligible, return all eligible."""
        archive = AgentArchive(archive_dir=str(tmp_path / "arc"))
        for i in range(2):
            f = _make_agent_file(tmp_path, f"a{i}.py")
            archive.add_agent(str(f), benchmark_scores={"b": 0.5}, is_valid=True)

        selector = ParentSelector()
        parents = selector.select_parents(archive, n_parents=10)
        assert len(parents) == 2

    def test_higher_score_agent_selected_more_often(self, tmp_path):
        """Agent with high score (0.9) should be picked more than one with low score (0.1)."""
        archive = AgentArchive(archive_dir=str(tmp_path / "arc"))
        f_high = _make_agent_file(tmp_path, "high.py")
        f_low = _make_agent_file(tmp_path, "low.py")
        high = archive.add_agent(str(f_high), benchmark_scores={"b": 0.9}, is_valid=True)
        low = archive.add_agent(str(f_low), benchmark_scores={"b": 0.1}, is_valid=True)

        selector = ParentSelector()
        random.seed(0)
        counts = {high.agent_id: 0, low.agent_id: 0}
        for _ in range(1000):
            chosen = selector.select_parents(archive, n_parents=1)
            counts[chosen[0].agent_id] += 1

        assert counts[high.agent_id] > counts[low.agent_id] * 3, (
            "High-score agent should dominate selection"
        )

    def test_invalid_agents_excluded_from_selection(self, tmp_path):
        archive = AgentArchive(archive_dir=str(tmp_path / "arc"))
        fv = _make_agent_file(tmp_path, "valid.py")
        fi = _make_agent_file(tmp_path, "invalid.py")
        valid = archive.add_agent(str(fv), benchmark_scores={"b": 0.5}, is_valid=True)
        invalid = archive.add_agent(str(fi), benchmark_scores={"b": 0.9}, is_valid=False)

        selector = ParentSelector()
        random.seed(1)
        for _ in range(50):
            chosen = selector.select_parents(archive, n_parents=1)
            assert chosen[0].agent_id == valid.agent_id

    def test_non_regression_gate_excludes_child_with_benchmark_regression(self, tmp_path):
        archive = AgentArchive(archive_dir=str(tmp_path / "arc"))
        parent_file = _make_agent_file(tmp_path, "parent.py")
        regressed_file = _make_agent_file(tmp_path, "regressed.py")
        clean_file = _make_agent_file(tmp_path, "clean.py")
        parent = archive.add_agent(
            str(parent_file),
            benchmark_scores={"a": 1.0, "b": 0.0},
            is_valid=True,
        )
        archive.add_agent(
            str(regressed_file),
            parent_id=parent.agent_id,
            benchmark_scores={"a": 0.0, "b": 1.0},
            is_valid=True,
        )
        clean_child = archive.add_agent(
            str(clean_file),
            parent_id=parent.agent_id,
            benchmark_scores={"a": 1.0, "b": 1.0},
            is_valid=True,
        )

        selector = ParentSelector(require_non_regression=True)
        selected_ids = {
            agent.agent_id
            for agent in selector.select_parents(archive, n_parents=10)
        }

        assert parent.agent_id in selected_ids
        assert clean_child.agent_id in selected_ids
        assert len(selected_ids) == 2
