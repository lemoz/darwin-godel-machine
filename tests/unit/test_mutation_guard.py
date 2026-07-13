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


def test_constrained_lane_allows_bounded_iteration_increase():
    parent = b"max_iterations: int = 10\n"
    child = b"max_iterations: int = 15\n"
    decision = ConstrainedMutationGuard(
        enabled=True,
        max_agent_iterations=24,
    ).inspect(
        before_snapshot={"agent.py": parent},
        after_snapshot={"agent.py": child},
        changed_code_files=["agent.py"],
    )

    assert decision.admitted is True


def test_constrained_lane_rejects_iteration_amplification_over_limit():
    parent = b"max_iterations: int = 32\n"
    child = b"max_iterations: int = 48\n"
    decision = ConstrainedMutationGuard(
        enabled=True,
        max_agent_iterations=24,
    ).inspect(
        before_snapshot={"agent.py": parent},
        after_snapshot={"agent.py": child},
        changed_code_files=["agent.py"],
    )

    assert decision.admitted is False
    assert decision.failure_mode == "unsafe complexity"
    assert "32 to 48" in decision.reasons[0]
    assert "configured limit is 24" in decision.reasons[0]


def test_constrained_lane_rejects_runtime_iteration_floor_over_limit():
    parent = b"self.config.max_iterations = max(self.config.max_iterations, 15)\n"
    child = b"self.config.max_iterations = max(self.config.max_iterations, 40)\n"
    decision = ConstrainedMutationGuard(
        enabled=True,
        max_agent_iterations=24,
    ).inspect(
        before_snapshot={"agent.py": parent},
        after_snapshot={"agent.py": child},
        changed_code_files=["agent.py"],
    )

    assert decision.admitted is False
    assert decision.failure_mode == "unsafe complexity"


def test_constrained_lane_ignores_unrelated_large_literal():
    parent = b"def solve():\n    return 10\n"
    child = b"def solve():\n    return 48\n"
    decision = ConstrainedMutationGuard(
        enabled=True,
        max_agent_iterations=24,
    ).inspect(
        before_snapshot={"agent.py": parent},
        after_snapshot={"agent.py": child},
        changed_code_files=["agent.py"],
    )

    assert decision.admitted is True


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


PROMPT_PARENT = b'''class Agent:
    def _build_system_message(self, context):
        self_modification_instructions = "self modify"
        if context.task_id.startswith("self_modify"):
            self_modification_instructions = "mutate"
        base_instructions = f"""solution.py
Public samples are only smoke tests
CRITICAL COMPLETION REQUIREMENT
Task complete
Solution implemented
{self_modification_instructions}
"""
        return base_instructions
'''


def test_constrained_lane_allows_prompt_only_addition_with_protocol_markers():
    child = PROMPT_PARENT.replace(
        b"Public samples are only smoke tests",
        b"Estimate complexity before coding\nPublic samples are only smoke tests",
    )
    decision = ConstrainedMutationGuard(enabled=True).inspect(
        before_snapshot={"agent.py": PROMPT_PARENT},
        after_snapshot={"agent.py": child},
        changed_code_files=["agent.py"],
    )

    assert decision.admitted is True


def test_constrained_lane_rejects_prompt_change_removing_protocol_marker():
    child = PROMPT_PARENT.replace(b"Task complete", b"Finished")
    decision = ConstrainedMutationGuard(enabled=True).inspect(
        before_snapshot={"agent.py": PROMPT_PARENT},
        after_snapshot={"agent.py": child},
        changed_code_files=["agent.py"],
    )

    assert decision.admitted is False
    assert decision.failure_mode == "completion/protocol failure"


def test_constrained_lane_rejects_prompt_method_control_flow_change():
    child = PROMPT_PARENT.replace(
        b'context.task_id.startswith("self_modify")',
        b"True",
    )
    decision = ConstrainedMutationGuard(enabled=True).inspect(
        before_snapshot={"agent.py": PROMPT_PARENT},
        after_snapshot={"agent.py": child},
        changed_code_files=["agent.py"],
    )

    assert decision.admitted is False
    assert decision.failure_mode == "completion/protocol failure"
