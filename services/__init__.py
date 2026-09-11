"""
JustiAssist Services - Backend Service Modules
"""

from .news_scraper import LegalNewsScraper
from .pipeline_events import PipelineEventEmitter
from .indian_kanoon import IndianKanoonAPI

__all__ = ['LegalNewsScraper', 'PipelineEventEmitter', 'IndianKanoonAPI']
