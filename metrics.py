"""
JustiAssist Metrics Collection
Track key production metrics for observability
"""

from collections import defaultdict
from datetime import datetime
from typing import Dict, Any
import threading


class MetricsCollector:
    """Thread-safe metrics collection for production monitoring"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._counters = defaultdict(int)
        self._histograms = defaultdict(list)
        self._window_start = datetime.utcnow()
    
    def incr(self, metric: str, value: int = 1):
        """Increment counter"""
        with self._lock:
            self._counters[metric] += value
            
    def decr(self, metric: str, value: int = 1, ensure_non_negative: bool = False):
        """Decrement counter (used for gauges like active connections)"""
        with self._lock:
            if ensure_non_negative:
                self._counters[metric] = max(0, self._counters[metric] - value)
            else:
                self._counters[metric] -= value
    
    def observe(self, metric: str, value: float):
        """Record histogram observation"""
        with self._lock:
            self._histograms[metric].append(value)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics snapshot"""
        with self._lock:
            total_queries = self._counters.get("queries_total", 0)
            
            return {
                "window_start": self._window_start.isoformat(),
                "window_duration_seconds": (datetime.utcnow() - self._window_start).total_seconds(),
                
                # Volume metrics
                "queries_total": total_queries,
                "queries_legal": self._counters.get("queries_legal", 0),
                "queries_bail": self._counters.get("queries_bail", 0),
                
                # Retrieval metrics
                "retrieval_hit_rate": self._safe_rate("retrieval_hits", total_queries),
                "retrieval_avg_score": self._safe_avg("retrieval_scores"),
                "hybrid_search_count": self._counters.get("hybrid_searches", 0),
                "statutory_results_total": self._counters.get("statutory_results_total", 0),
                "case_law_results_total": self._counters.get("case_law_results_total", 0),
                "external_results_total": self._counters.get("external_results_total", 0),
                "session_document_results_total": self._counters.get("session_document_results_total", 0),
                
                # Verification & Generation metrics
                "verifications_supported": self._counters.get("verifications_supported", 0),
                "verifications_rejected": self._counters.get("verifications_rejected", 0),
                "answers_abstained": self._counters.get("answers_abstained", 0),
                
                # Response metrics
                "grounded_response_rate": self._safe_rate("responses_grounded", total_queries),
                "fallback_rate": self._safe_rate("responses_fallback", total_queries),
                
                # SSE metrics
                "sse_active_connections": self._counters.get("sse_active_connections", 0),
                "sse_completed_total": self._counters.get("sse_completed_total", 0),
                "sse_errors_total": self._counters.get("sse_errors_total", 0),
                
                # Citation metrics
                "citation_validity_rate": self._safe_avg("citation_validity"),
                "citation_warnings": self._counters.get("citation_warnings", 0),
                
                # Confidence distribution
                "confidence_high": self._counters.get("confidence_high", 0),
                "confidence_medium": self._counters.get("confidence_medium", 0),
                "confidence_low": self._counters.get("confidence_low", 0),
                "confidence_very_low": self._counters.get("confidence_very_low", 0),
                
                # Latency
                "avg_latency_ms": self._safe_avg("latency_ms"),
                "p95_latency_ms": self._percentile("latency_ms", 0.95),
            }
    
    def _safe_rate(self, numerator_key: str, denominator: int) -> float:
        if denominator == 0:
            return 0.0
        return round(self._counters.get(numerator_key, 0) / denominator, 3)
    
    def _safe_avg(self, key: str) -> float:
        values = self._histograms.get(key, [])
        if not values:
            return 0.0
        return round(sum(values) / len(values), 3)
    
    def _percentile(self, key: str, p: float) -> float:
        values = sorted(self._histograms.get(key, []))
        if not values:
            return 0.0
        idx = int(len(values) * p)
        return round(values[min(idx, len(values) - 1)], 1)
    
    def reset(self):
        """Reset all metrics (for new monitoring window)"""
        with self._lock:
            self._counters.clear()
            self._histograms.clear()
            self._window_start = datetime.utcnow()


# Global instance
metrics = MetricsCollector()
