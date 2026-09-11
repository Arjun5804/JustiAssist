"""
JustiAssist Agents Package — v2.0 with CrewAI
"""

from .query_classifier import QueryClassifier, QueryType
from .query_reformulator import QueryReformulator
from .bail_evaluator import BailEvaluator, BailEvaluation
from .feedback_evaluator import FeedbackEvaluator, EvaluationResult
from .crew_orchestrator import JustiAssistCrew, CrewResult

__all__ = [
    'QueryClassifier',
    'QueryType', 
    'QueryReformulator',
    'BailEvaluator',
    'BailEvaluation',
    'FeedbackEvaluator',
    'EvaluationResult',
    'JustiAssistCrew',
    'CrewResult',
]
