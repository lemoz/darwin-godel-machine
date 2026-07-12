from self_modification.mutation_guard import ConstrainedMutationGuard


PARENT = b"""class Agent:
    def _is_task_complete(self, response, task):
        return response.endswith("Task complete")

    def solve_task(self, task):
        return "old"
"""


def test_disabled_baseline_admits_protocol_change():
    child = PARENT.replace(
        b'return response.endswith("Task complete")',
        b"return True",
    )
    decision = ConstrainedMutationGuard(enabled=False).inspect(
        before_snapshot={"agent.py": PARENT},
        after_snapshot={"agent.py": child},
        changed_code_files=["agent.py"],
    )

    assert decision.admitted is True
    assert decision.failure_mode is None


def test_constrained_lane_rejects_protocol_change():
    child = PARENT.replace(
        b'return response.endswith("Task complete")',
        b"return True",
    )
    decision = ConstrainedMutationGuard(enabled=True).inspect(
        before_snapshot={"agent.py": PARENT},
        after_snapshot={"agent.py": child},
        changed_code_files=["agent.py"],
    )

    assert decision.admitted is False
    assert decision.failure_mode == "completion/protocol failure"
    assert decision.protected_symbol_changes == (
        "agent.py:Agent._is_task_complete",
    )


def test_constrained_lane_admits_non_protocol_change():
    child = PARENT.replace(b'return "old"', b'return "improved"')
    decision = ConstrainedMutationGuard(enabled=True).inspect(
        before_snapshot={"agent.py": PARENT},
        after_snapshot={"agent.py": child},
        changed_code_files=["agent.py"],
    )

    assert decision.admitted is True
    assert decision.failure_mode is None


def test_constrained_lane_rejects_invalid_python():
    decision = ConstrainedMutationGuard(enabled=True).inspect(
        before_snapshot={"agent.py": PARENT},
        after_snapshot={"agent.py": b"class Agent(:\n"},
        changed_code_files=["agent.py"],
    )

    assert decision.admitted is False
    assert decision.failure_mode == "invalid Python"


def test_constrained_lane_tags_noop():
    decision = ConstrainedMutationGuard(enabled=True).inspect(
        before_snapshot={"agent.py": PARENT},
        after_snapshot={"agent.py": PARENT},
        changed_code_files=[],
    )

    assert decision.admitted is False
    assert decision.failure_mode == "no-op"


def test_constrained_lane_tags_import_only_change_as_noop():
    child = PARENT.replace(b"class Agent:", b"import traceback\nclass Agent:")
    decision = ConstrainedMutationGuard(enabled=True).inspect(
        before_snapshot={"agent.py": PARENT},
        after_snapshot={"agent.py": child},
        changed_code_files=["agent.py"],
    )

    assert decision.admitted is False
    assert decision.failure_mode == "no-op"
    assert "only changed imports" in decision.reasons[0]
