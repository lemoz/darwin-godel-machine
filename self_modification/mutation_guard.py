"""Pre-evaluation admission checks for constrained DGM mutations."""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence


FAILURE_MODES = (
    "no-op",
    "malformed edit",
    "invalid Python",
    "unsafe complexity",
    "timeout/provider failure",
    "hidden-test failure",
    "completion/protocol failure",
)

DEFAULT_PROTECTED_SYMBOLS: Dict[str, Sequence[str]] = {
    "agent.py": (
        "Agent._build_system_message",
        "Agent._is_task_complete",
        "Agent._extract_code_solution",
        "Agent._read_workspace_solution",
        "Agent._benchmark_completion_block_reason",
    ),
}

PROMPT_PROTOCOL_MARKERS = (
    "Task complete",
    "Solution implemented",
    "solution.py",
    "CRITICAL COMPLETION REQUIREMENT",
    "Public samples are only smoke tests",
)


@dataclass(frozen=True)
class MutationAdmission:
    """Structured result from the constrained mutation admission gate."""

    admitted: bool
    failure_mode: Optional[str]
    reasons: Sequence[str]
    protected_symbol_changes: Sequence[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "admitted": self.admitted,
            "failure_mode": self.failure_mode,
            "reasons": list(self.reasons),
            "protected_symbol_changes": list(self.protected_symbol_changes),
        }


class ConstrainedMutationGuard:
    """Reject invalid or protocol-damaging agent mutations before evaluation."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        protected_symbols: Optional[Mapping[str, Iterable[str]]] = None,
    ) -> None:
        self.enabled = bool(enabled)
        configured = protected_symbols or DEFAULT_PROTECTED_SYMBOLS
        self.protected_symbols = {
            str(path): tuple(str(symbol) for symbol in symbols)
            for path, symbols in configured.items()
        }

    def inspect(
        self,
        *,
        before_snapshot: Mapping[str, bytes],
        after_snapshot: Mapping[str, bytes],
        changed_code_files: Sequence[str],
    ) -> MutationAdmission:
        if not changed_code_files:
            return MutationAdmission(
                admitted=False,
                failure_mode="no-op",
                reasons=("mutation changed no executable Python agent files",),
                protected_symbol_changes=(),
            )

        parsed_before: Dict[str, ast.AST] = {}
        parsed_after: Dict[str, ast.AST] = {}
        for relative_path in changed_code_files:
            content = after_snapshot.get(relative_path)
            if content is None:
                continue
            try:
                parsed_after[relative_path] = ast.parse(
                    content.decode("utf-8"),
                    filename=relative_path,
                )
            except (SyntaxError, UnicodeDecodeError) as exc:
                return MutationAdmission(
                    admitted=False,
                    failure_mode="invalid Python",
                    reasons=(f"{relative_path}: {exc}",),
                    protected_symbol_changes=(),
                )

        if not self.enabled:
            return MutationAdmission(
                admitted=True,
                failure_mode=None,
                reasons=(),
                protected_symbol_changes=(),
            )

        if self._is_import_only_change(
            before_snapshot=before_snapshot,
            parsed_after=parsed_after,
            changed_code_files=changed_code_files,
        ):
            return MutationAdmission(
                admitted=False,
                failure_mode="no-op",
                reasons=("mutation only changed imports and no executable behavior",),
                protected_symbol_changes=(),
            )

        protected_changes = []
        for relative_path, symbols in self.protected_symbols.items():
            if relative_path not in changed_code_files:
                continue
            before_content = before_snapshot.get(relative_path)
            after_tree = parsed_after.get(relative_path)
            if before_content is None or after_tree is None:
                protected_changes.extend(
                    f"{relative_path}:{symbol}" for symbol in symbols
                )
                continue
            try:
                before_tree = parsed_before.setdefault(
                    relative_path,
                    ast.parse(before_content.decode("utf-8"), filename=relative_path),
                )
            except (SyntaxError, UnicodeDecodeError) as exc:
                return MutationAdmission(
                    admitted=False,
                    failure_mode="invalid Python",
                    reasons=(f"parent {relative_path}: {exc}",),
                    protected_symbol_changes=(),
                )

            for symbol in symbols:
                before_node = self._find_symbol(before_tree, symbol)
                after_node = self._find_symbol(after_tree, symbol)
                if self._node_fingerprint(before_node) != self._node_fingerprint(after_node):
                    if self._is_safe_prompt_only_change(
                        symbol=symbol,
                        before_node=before_node,
                        after_node=after_node,
                    ):
                        continue
                    protected_changes.append(f"{relative_path}:{symbol}")

        if protected_changes:
            return MutationAdmission(
                admitted=False,
                failure_mode="completion/protocol failure",
                reasons=(
                    "mutation changed protected completion or benchmark protocol symbols",
                ),
                protected_symbol_changes=tuple(sorted(protected_changes)),
            )

        return MutationAdmission(
            admitted=True,
            failure_mode=None,
            reasons=(),
            protected_symbol_changes=(),
        )

    @staticmethod
    def _find_symbol(tree: ast.AST, qualified_name: str) -> Optional[ast.AST]:
        parts = qualified_name.split(".")
        body = getattr(tree, "body", ())
        current: Optional[ast.AST] = None
        for index, part in enumerate(parts):
            matching = [
                node
                for node in body
                if getattr(node, "name", None) == part
                and (
                    (index < len(parts) - 1 and isinstance(node, ast.ClassDef))
                    or (
                        index == len(parts) - 1
                        and isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                    )
                )
            ]
            if not matching:
                return None
            current = matching[0]
            body = getattr(current, "body", ())
        return current

    @staticmethod
    def _node_fingerprint(node: Optional[ast.AST]) -> Optional[str]:
        if node is None:
            return None
        return ast.dump(node, annotate_fields=True, include_attributes=False)

    @classmethod
    def _is_safe_prompt_only_change(
        cls,
        *,
        symbol: str,
        before_node: Optional[ast.AST],
        after_node: Optional[ast.AST],
    ) -> bool:
        """Allow prompt text additions without weakening completion structure."""
        if symbol != "Agent._build_system_message":
            return False
        if before_node is None or after_node is None:
            return False
        if cls._prompt_string_insensitive_fingerprint(
            before_node
        ) != cls._prompt_string_insensitive_fingerprint(after_node):
            return False
        after_text = "\n".join(
            node.value
            for node in ast.walk(after_node)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        )
        return all(marker in after_text for marker in PROMPT_PROTOCOL_MARKERS)

    @staticmethod
    def _prompt_string_insensitive_fingerprint(node: ast.AST) -> str:
        """Fingerprint code while ignoring only named prompt variable text."""

        class PromptTextNormalizer(ast.NodeTransformer):
            def visit_Assign(self, assignment: ast.Assign) -> ast.AST:
                assignment = self.generic_visit(assignment)
                prompt_target = any(
                    isinstance(target, ast.Name)
                    and target.id in {"base_instructions", "self_modification_instructions"}
                    for target in assignment.targets
                )
                if prompt_target:
                    assignment.value = PromptLiteralNormalizer().visit(
                        assignment.value
                    )
                return assignment

        class PromptLiteralNormalizer(ast.NodeTransformer):
            def visit_Constant(self, constant: ast.Constant) -> ast.AST:
                if isinstance(constant.value, str):
                    return ast.copy_location(ast.Constant(value="<PROMPT_TEXT>"), constant)
                return constant

        normalized = PromptTextNormalizer().visit(copy.deepcopy(node))
        ast.fix_missing_locations(normalized)
        return ast.dump(normalized, annotate_fields=True, include_attributes=False)

    @classmethod
    def _is_import_only_change(
        cls,
        *,
        before_snapshot: Mapping[str, bytes],
        parsed_after: Mapping[str, ast.AST],
        changed_code_files: Sequence[str],
    ) -> bool:
        compared = False
        for relative_path in changed_code_files:
            before_content = before_snapshot.get(relative_path)
            after_tree = parsed_after.get(relative_path)
            if before_content is None or after_tree is None:
                return False
            try:
                before_tree = ast.parse(
                    before_content.decode("utf-8"),
                    filename=relative_path,
                )
            except (SyntaxError, UnicodeDecodeError):
                return False
            compared = True
            if cls._without_imports_fingerprint(before_tree) != cls._without_imports_fingerprint(
                after_tree
            ):
                return False
        return compared

    @staticmethod
    def _without_imports_fingerprint(tree: ast.AST) -> str:
        if not isinstance(tree, ast.Module):
            return ast.dump(tree, annotate_fields=True, include_attributes=False)
        stripped = ast.Module(
            body=[
                node
                for node in tree.body
                if not isinstance(node, (ast.Import, ast.ImportFrom))
            ],
            type_ignores=[],
        )
        return ast.dump(stripped, annotate_fields=True, include_attributes=False)
