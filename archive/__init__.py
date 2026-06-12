"""
Archive management for the Darwin Gödel Machine.

Exports AgentArchive + ArchivedAgent (from agent_archive) and
ParentSelector (from parent_selector).  archive_manager and
novelty_calculator are deleted dead code.
"""

from .agent_archive import AgentArchive, ArchivedAgent
from .lineage_visualizer import render_archive_lineage_html, render_archive_lineage_svg
from .parent_selector import ParentSelector

__all__ = [
    'AgentArchive',
    'ArchivedAgent',
    'ParentSelector',
    'render_archive_lineage_html',
    'render_archive_lineage_svg',
]
