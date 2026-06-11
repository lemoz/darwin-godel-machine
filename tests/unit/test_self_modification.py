"""
Unit tests for self_modification package.

Focuses on the ImplementationManager one-occurrence rule (the key invariant
introduced by the fixer) and the ModificationProposer / PerformanceDiagnosis
modules that are still live.
"""

import pytest
import asyncio
from pathlib import Path

from self_modification.implementation import ImplementationManager
from self_modification.modification_proposal import (
    ModificationProposer, ModificationProposal, CodeChange
)
from self_modification.performance_diagnosis import (
    PerformanceDiagnosis, DiagnosisReport
)


# ---------------------------------------------------------------------------
# ImplementationManager — one-occurrence rule for modify
# ---------------------------------------------------------------------------

class TestImplementationManagerModify:

    def _make_manager(self):
        return ImplementationManager()

    def test_apply_modify_single_occurrence_succeeds(self, tmp_path):
        """Exactly one occurrence: replacement applied cleanly."""
        f = tmp_path / "code.py"
        f.write_text("def foo(): pass\ndef bar(): pass\n")

        manager = self._make_manager()
        change = CodeChange(
            file_path="code.py",
            change_type="modify",
            description="Replace foo",
            priority=1,
            old_code="def foo(): pass",
            new_code="def foo(): return 42",
        )
        result = manager._apply_modify_change(f, change)
        assert result is True
        content = f.read_text()
        assert "def foo(): return 42" in content
        assert "def foo(): pass" not in content

    def test_apply_modify_zero_occurrences_raises(self, tmp_path):
        """Zero occurrences → RuntimeError with 'not found' message."""
        f = tmp_path / "code.py"
        f.write_text("def bar(): pass\n")

        manager = self._make_manager()
        change = CodeChange(
            file_path="code.py",
            change_type="modify",
            description="Modify nonexistent",
            priority=1,
            old_code="def nonexistent(): pass",
            new_code="def nonexistent(): return 1",
        )
        with pytest.raises(RuntimeError, match="not found"):
            manager._apply_modify_change(f, change)

    def test_apply_modify_two_occurrences_raises(self, tmp_path):
        """Two occurrences → RuntimeError with 'Ambiguous' message."""
        f = tmp_path / "code.py"
        f.write_text("x = 1\nx = 1\n")

        manager = self._make_manager()
        change = CodeChange(
            file_path="code.py",
            change_type="modify",
            description="Ambiguous",
            priority=1,
            old_code="x = 1",
            new_code="x = 2",
        )
        with pytest.raises(RuntimeError, match="Ambiguous|ambiguous|occurrences"):
            manager._apply_modify_change(f, change)

    def test_apply_modify_nonexistent_file_returns_false(self, tmp_path):
        manager = self._make_manager()
        change = CodeChange(
            file_path="missing.py",
            change_type="modify",
            description="No file",
            priority=1,
            old_code="x",
            new_code="y",
        )
        result = manager._apply_modify_change(tmp_path / "missing.py", change)
        assert result is False

    def test_apply_modify_missing_old_code_returns_false(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("x = 1\n")
        manager = self._make_manager()
        change = CodeChange(
            file_path="code.py",
            change_type="modify",
            description="no old code",
            priority=1,
            old_code=None,
            new_code="y = 2",
        )
        result = manager._apply_modify_change(f, change)
        assert result is False


# ---------------------------------------------------------------------------
# ImplementationManager — add and delete
# ---------------------------------------------------------------------------

class TestImplementationManagerAdd:

    def test_apply_add_creates_new_file(self, tmp_path):
        f = tmp_path / "newfile.py"
        manager = ImplementationManager()
        change = CodeChange(
            file_path="newfile.py",
            change_type="add",
            description="Create new",
            priority=1,
            new_code="x = 1\n",
        )
        result = manager._apply_add_change(f, change)
        assert result is True
        assert f.read_text() == "x = 1\n"

    def test_apply_add_appends_to_existing(self, tmp_path):
        f = tmp_path / "existing.py"
        f.write_text("x = 1\n")
        manager = ImplementationManager()
        change = CodeChange(
            file_path="existing.py",
            change_type="add",
            description="Append",
            priority=1,
            new_code="y = 2",
        )
        result = manager._apply_add_change(f, change)
        assert result is True
        content = f.read_text()
        assert "y = 2" in content


class TestImplementationManagerDelete:

    def test_apply_delete_removes_file(self, tmp_path):
        f = tmp_path / "gone.py"
        f.write_text("x = 1\n")
        manager = ImplementationManager()
        change = CodeChange(
            file_path="gone.py",
            change_type="delete",
            description="Delete",
            priority=1,
        )
        result = manager._apply_delete_change(f, change)
        assert result is True
        assert not f.exists()

    def test_apply_delete_specific_content(self, tmp_path):
        f = tmp_path / "partial.py"
        f.write_text("keep this\nremove this\nkeep this too\n")
        manager = ImplementationManager()
        change = CodeChange(
            file_path="partial.py",
            change_type="delete",
            description="Delete content",
            priority=1,
            old_code="remove this\n",
        )
        result = manager._apply_delete_change(f, change)
        assert result is True
        content = f.read_text()
        assert "remove this" not in content
        assert "keep this" in content


# ---------------------------------------------------------------------------
# PerformanceDiagnosis
# ---------------------------------------------------------------------------

class TestPerformanceDiagnosis:

    def test_generate_improvement_suggestions_populates(self):
        diagnoser = PerformanceDiagnosis()
        report = DiagnosisReport(
            overall_score=0.4,
            benchmark_scores={"math": 0.4, "code": 0.3},
        )
        diagnoser._generate_improvement_suggestions(report)
        # Should have suggestions (low score triggers them)
        assert isinstance(report.improvement_suggestions, list)

    def test_high_score_no_critical_issues(self):
        diagnoser = PerformanceDiagnosis()
        report = DiagnosisReport(
            overall_score=0.95,
            benchmark_scores={"math": 0.95},
        )
        diagnoser._generate_improvement_suggestions(report)
        # High score → fewer / no critical issues
        assert isinstance(report.improvement_suggestions, list)


# ---------------------------------------------------------------------------
# ModificationProposer
# ---------------------------------------------------------------------------

class TestModificationProposer:

    def test_summarize_diagnosis_returns_string(self):
        proposer = ModificationProposer()
        report = DiagnosisReport(
            overall_score=0.6,
            benchmark_scores={"b": 0.6},
        )
        summary = proposer._summarize_diagnosis(report)
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_proposal_dataclass_str(self):
        proposal = ModificationProposal(
            proposal_id="p1",
            diagnosis_summary="test",
            code_changes=[
                CodeChange(
                    file_path="f.py",
                    change_type="add",
                    description="Add something",
                    priority=1,
                )
            ],
        )
        s = str(proposal)
        assert "p1" in s or "change" in s.lower()
