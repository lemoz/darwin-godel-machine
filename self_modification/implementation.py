"""
Implementation module for applying code modifications.

This module provides functionality to implement modification proposals,
including backup creation, code changes, and verification.
"""

import ast
import importlib.util
import shutil
import tempfile
import datetime
import asyncio
import traceback
from typing import Dict, List, Any, Optional
from pathlib import Path


class ImplementationManager:
    """
    Manages the implementation of code modifications.
    
    This class handles the actual application of proposed changes,
    including safety measures like backups and verification.
    """
    
    def __init__(self):
        """Initialize the implementation manager."""
        self.backup_dir = None
        self.changes_applied = []
        self.verification_results = []
    
    async def implement_proposal(
        self,
        proposal: 'ModificationProposal',
        agent_path: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Implement a modification proposal.
        
        Args:
            proposal: The modification proposal to implement
            agent_path: Path to the agent code
            dry_run: If True, simulate changes without applying
            
        Returns:
            Dict containing implementation results
        """
        results = {
            'success': False,
            'changes_applied': [],
            'errors': [],
            'backup_path': None,
            'verification': None
        }
        
        try:
            # Create backup unless dry run
            if not dry_run:
                self.backup_dir = self._create_backup(agent_path)
                results['backup_path'] = str(self.backup_dir)
            
            # Apply each change
            for change in proposal.code_changes:
                try:
                    success = await self._apply_code_change(
                        change,
                        agent_path,
                        dry_run
                    )
                    if success:
                        results['changes_applied'].append({
                            'file': change.file_path,
                            'type': change.change_type,
                            'description': change.description
                        })
                        self.changes_applied.append(change)
                except Exception as e:
                    error_msg = f"Failed to apply change '{change.description}': {str(e)}"
                    results['errors'].append(error_msg)
                    
                    # Rollback on error unless dry run
                    if not dry_run and self.backup_dir:
                        self._rollback_changes(agent_path)
                        results['success'] = False
                        return results
            
            # Verify changes unless dry run
            if not dry_run:
                verification = await self._verify_modifications(agent_path)
                results['verification'] = verification
                
                if not verification['valid']:
                    # Rollback if verification fails
                    self._rollback_changes(agent_path)
                    results['errors'].extend(verification['errors'])
                    results['success'] = False
                    return results
            
            results['success'] = True
            
        except Exception as e:
            results['errors'].append(f"Implementation failed: {str(e)}")
            if not dry_run and self.backup_dir:
                self._rollback_changes(agent_path)
        
        return results
    
    def _create_backup(self, agent_path: str) -> Path:
        """
        Create a backup of the agent code.
        
        Args:
            agent_path: Path to agent code
            
        Returns:
            Path to backup directory
        """
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = Path(tempfile.mkdtemp(prefix=f"agent_backup_{timestamp}_"))
        
        # Copy entire agent directory
        src_path = Path(agent_path)
        if src_path.exists():
            shutil.copytree(src_path, backup_path / "agent", dirs_exist_ok=True)
        
        return backup_path
    
    async def _apply_code_change(
        self,
        change: 'CodeChange',
        agent_path: str,
        dry_run: bool
    ) -> bool:
        """
        Apply a single code change.
        
        Args:
            change: The code change to apply
            agent_path: Path to agent code
            dry_run: If True, simulate without applying
            
        Returns:
            bool: True if successful
        """
        file_path = Path(agent_path) / change.file_path
        
        if dry_run:
            # In dry run mode, simulate success for all valid operations
            if change.change_type == 'add':
                # For add operations, always succeed (can add to existing or new files)
                return True
            elif change.change_type in ['modify', 'delete'] and file_path.exists():
                return True
            elif change.change_type in ['modify', 'delete'] and not file_path.exists():
                # Cannot modify/delete non-existent files
                return False
            return True  # Default to success for other cases
        
        # Ensure directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        if change.change_type == 'add':
            return self._apply_add_change(file_path, change)
        elif change.change_type == 'modify':
            return self._apply_modify_change(file_path, change)
        elif change.change_type == 'delete':
            return self._apply_delete_change(file_path, change)
        
        return False
    
    def _apply_add_change(self, file_path: Path, change: 'CodeChange') -> bool:
        """Apply an 'add' type change."""
        if not file_path.exists():
            # Create new file
            if change.new_code:
                file_path.write_text(change.new_code)
                return True
        else:
            # Add to existing file
            content = file_path.read_text()
            
            if change.location == 'imports' and change.new_code:
                # Add imports at the top
                lines = content.split('\n')
                import_line = None
                
                # Find where to insert imports
                for i, line in enumerate(lines):
                    if line.strip() and not line.startswith('#') and not line.startswith('"""'):
                        import_line = i
                        break
                
                if import_line is not None:
                    lines.insert(import_line, change.new_code)
                    file_path.write_text('\n'.join(lines))
                    return True
            
            elif change.location == '__init__' and change.new_code:
                # Add to __init__ method
                lines = content.split('\n')
                in_init = False
                indent_level = None
                insert_line = None
                
                for i, line in enumerate(lines):
                    if 'def __init__' in line:
                        in_init = True
                        # Determine indent level
                        indent_level = len(line) - len(line.lstrip())
                    elif in_init and line.strip() and indent_level is not None:
                        # Check if we're still in __init__
                        current_indent = len(line) - len(line.lstrip())
                        if current_indent <= indent_level:
                            # We've left __init__
                            insert_line = i
                            break
                
                if insert_line:
                    # Insert before the line that ends __init__
                    lines.insert(insert_line, change.new_code)
                    file_path.write_text('\n'.join(lines))
                    return True
            
            else:
                # Default: append to end
                content += f"\n\n{change.new_code}"
                file_path.write_text(content)
                return True
        
        return False
    
    def _apply_modify_change(self, file_path: Path, change: 'CodeChange') -> bool:
        """
        Apply a 'modify' type change.

        Requires exactly one occurrence of ``change.old_code`` in the file.
        Zero occurrences → raises RuntimeError (old_code not found).
        More than one → raises RuntimeError (ambiguous match).
        """
        if not file_path.exists():
            return False

        if not (change.old_code and change.new_code):
            # Nothing to do without both sides of the replacement.
            return False

        content = file_path.read_text()
        occurrences = content.count(change.old_code)

        if occurrences == 0:
            raise RuntimeError(
                f"old_code not found in {file_path}: no occurrences of the search text"
            )
        if occurrences > 1:
            raise RuntimeError(
                f"Ambiguous match in {file_path}: {occurrences} occurrences found; "
                "provide more context to make the match unique"
            )

        # Exactly one occurrence — safe to replace.
        new_content = content.replace(change.old_code, change.new_code, 1)
        file_path.write_text(new_content)
        return True
    
    def _apply_delete_change(self, file_path: Path, change: 'CodeChange') -> bool:
        """Apply a 'delete' type change."""
        if file_path.exists():
            if change.old_code:
                # Delete specific content
                content = file_path.read_text()
                if change.old_code in content:
                    content = content.replace(change.old_code, '')
                    file_path.write_text(content)
                    return True
            else:
                # Delete entire file
                file_path.unlink()
                return True
        
        return False
    
    def _rollback_changes(self, agent_path: str) -> None:
        """
        Rollback changes using backup.
        
        Args:
            agent_path: Path to agent code
        """
        if not self.backup_dir:
            return
        
        # Remove current agent directory
        agent_dir = Path(agent_path)
        if agent_dir.exists():
            shutil.rmtree(agent_dir)
        
        # Restore from backup
        backup_agent_dir = self.backup_dir / "agent"
        if backup_agent_dir.exists():
            shutil.copytree(backup_agent_dir, agent_dir)
    
    async def _verify_modifications(self, agent_path: str) -> Dict[str, Any]:
        """
        Verify that modifications are valid.
        
        Args:
            agent_path: Path to agent code
            
        Returns:
            Dict with verification results
        """
        results = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        # Check Python syntax
        agent_files = Path(agent_path).rglob("*.py")
        for file_path in agent_files:
            try:
                content = file_path.read_text()
                ast.parse(content)
            except SyntaxError as e:
                results['valid'] = False
                results['errors'].append(f"Syntax error in {file_path}: {str(e)}")
            except Exception as e:
                results['warnings'].append(f"Failed to parse {file_path}: {str(e)}")
        
        # Check imports
        try:
            # Simple import check - could be enhanced
            import_errors = self._check_imports(agent_path)
            if import_errors:
                results['errors'].extend(import_errors)
                results['valid'] = False
        except Exception as e:
            results['warnings'].append(f"Import verification failed: {str(e)}")
        
        return results
    
    def _check_imports(self, agent_path: str) -> List[str]:
        """
        Check that every top-level import in modified Python files can be resolved.

        For each ``.py`` file under *agent_path* the function:
        1. Parses the source with :mod:`ast` to extract top-level ``import``
           and ``from … import`` statements.
        2. Calls :func:`importlib.util.find_spec` for each top-level module
           name to verify it is resolvable.

        Relative imports (``from . import …``) are skipped because they
        require a package context.

        Args:
            agent_path: Path to agent code

        Returns:
            List of import-error strings (empty when everything resolves)
        """
        errors: List[str] = []

        for py_file in Path(agent_path).rglob("*.py"):
            try:
                source = py_file.read_text()
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                # Syntax errors are caught separately in _verify_modifications.
                continue
            except Exception as exc:
                errors.append(f"Could not read {py_file}: {exc}")
                continue

            for node in ast.walk(tree):
                # Only examine top-level statements.
                if not isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue

                if isinstance(node, ast.Import):
                    module_names = [alias.name.split(".")[0] for alias in node.names]
                else:  # ImportFrom
                    if node.level and node.level > 0:
                        # Relative import — skip.
                        continue
                    module_names = (
                        [node.module.split(".")[0]] if node.module else []
                    )

                for module_name in module_names:
                    if not module_name:
                        continue
                    try:
                        spec = importlib.util.find_spec(module_name)
                        if spec is None:
                            errors.append(
                                f"{py_file}: cannot resolve import '{module_name}'"
                            )
                    except (ModuleNotFoundError, ValueError):
                        errors.append(
                            f"{py_file}: cannot resolve import '{module_name}'"
                        )

        return errors
    
    def cleanup(self) -> None:
        """Clean up temporary files and backups."""
        if self.backup_dir and self.backup_dir.exists():
            shutil.rmtree(self.backup_dir)
            self.backup_dir = None