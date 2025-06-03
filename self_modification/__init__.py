"""
Self-modification components for the Darwin Gödel Machine.

This module contains components for performance diagnosis, modification proposal,
and implementation of agent improvements.
"""

from .performance_diagnosis import PerformanceDiagnosis, DiagnosisReport
from .modification_proposal import ModificationProposer, ModificationProposal, CodeChange
from .implementation import ImplementationManager

__all__ = [
    'PerformanceDiagnosis',
    'DiagnosisReport',
    'ModificationProposer',
    'ModificationProposal',
    'CodeChange',
    'ImplementationManager'
]