"""
Pipeline Event Emitter for SSE (Server-Sent Events)

Emits real-time updates for each stage of the query processing pipeline.
"""

import asyncio
import json
import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional, AsyncGenerator
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

@dataclass
class PipelineEvent:
    """Represents a pipeline processing event"""
    type: str  # 'stage', 'complete', 'error'
    stage: Optional[str] = None
    status: Optional[str] = None  # 'pending', 'active', 'complete', 'error'
    time: Optional[int] = None  # milliseconds
    data: Optional[Dict] = None
    message: Optional[str] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
    
    def to_sse(self) -> str:
        """Format as Server-Sent Event"""
        return f"data: {json.dumps(asdict(self))}\n\n"


class PipelineEventEmitter:
    """
    Manages SSE event emission for query processing pipeline.
    
    Usage:
        async with PipelineEventEmitter() as emitter:
            await emitter.emit_stage('classify', 'active')
            # ... do classification
            await emitter.emit_stage('classify', 'complete', time=45)
    """
    
    STAGES = [
        'classify',      # Query classification
        'reformulate',   # Query reformulation/expansion
        'retrieve',      # Vector search + BM25 retrieval
        'rerank',        # Result reranking
        'score',         # Confidence scoring
        'generate',      # LLM response generation
    ]
    
    def __init__(self):
        self._events = asyncio.Queue()
        self._start_times: Dict[str, float] = {}
        self._active = True
    
    async def emit_stage(
        self, 
        stage: str, 
        status: str, 
        elapsed: Optional[int] = None,
        data: Optional[Dict] = None
    ) -> None:
        """
        Emit a stage status update.
        
        Args:
            stage: One of STAGES
            status: 'pending', 'active', 'complete', 'error'
            elapsed: Processing time in milliseconds
            data: Additional data for the event
        """
        if stage == status == 'active':
            self._start_times[stage] = time.time() if elapsed is None else None
        
        if status == 'complete' and elapsed is None and stage in self._start_times:
            elapsed_ms = int((time.time() - self._start_times[stage]) * 1000)
            elapsed = elapsed_ms
        
        event = PipelineEvent(
            type='stage',
            stage=stage,
            status=status,
            time=elapsed,
            data=data
        )
        await self._events.put(event)
        logger.debug(f"Pipeline event: {stage} -> {status}")
    
    async def emit_complete(self, response: Dict) -> None:
        """Emit final completion event with response"""
        event = PipelineEvent(
            type='complete',
            data={'response': response}
        )
        await self._events.put(event)
        self._active = False
    
    async def emit_error(self, message: str, stage: Optional[str] = None) -> None:
        """Emit error event"""
        event = PipelineEvent(
            type='error',
            stage=stage,
            status='error',
            message=message
        )
        await self._events.put(event)
        self._active = False
    
    async def get_events(self) -> AsyncGenerator[str, None]:
        """
        Async generator that yields SSE-formatted events.
        
        Yields:
            SSE-formatted event strings
        """
        while self._active:
            try:
                event = await asyncio.wait_for(self._events.get(), timeout=30.0)
                yield event.to_sse()
            except asyncio.TimeoutError:
                # Send keepalive
                yield ": keepalive\n\n"
    
    def start_stage(self, stage: str) -> 'StageTimer':
        """
        Start timing a stage. Returns a context manager.
        
        Usage:
            with emitter.start_stage('classify') as timer:
                # do work
            # automatically emits complete with time
        """
        return StageTimer(self, stage)
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await self.emit_error(str(exc_val))
        return False


class StageTimer:
    """Context manager for timing pipeline stages"""
    
    def __init__(self, emitter: PipelineEventEmitter, stage: str):
        self._emitter = emitter
        self._stage = stage
        self._start_time = None
    
    async def __aenter__(self):
        self._start_time = time.time()
        await self._emitter.emit_stage(self._stage, 'active')
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        elapsed_ms = int((time.time() - self._start_time) * 1000)
        
        if exc_type:
            await self._emitter.emit_stage(self._stage, 'error', time=elapsed_ms)
        else:
            await self._emitter.emit_stage(self._stage, 'complete', time=elapsed_ms)
        
        return False


class SyncPipelineEmitter:
    """
    Synchronous version that collects events for batch delivery.
    Use when SSE is not available and we need to return timing info in response.
    """
    
    def __init__(self):
        self.stages: Dict[str, Dict] = {}
        self._start_times: Dict[str, float] = {}
    
    def start(self, stage: str) -> None:
        """Mark stage as started"""
        self._start_times[stage] = time.time()
        self.stages[stage] = {'status': 'active', 'time': None}
    
    def complete(self, stage: str, data: Dict = None) -> None:
        """Mark stage as completed"""
        elapsed_ms = int((time.time() - self._start_times.get(stage, time.time())) * 1000)
        self.stages[stage] = {
            'status': 'complete',
            'time': elapsed_ms,
            'data': data
        }
    
    def error(self, stage: str, message: str) -> None:
        """Mark stage as error"""
        elapsed_ms = int((time.time() - self._start_times.get(stage, time.time())) * 1000)
        self.stages[stage] = {
            'status': 'error',
            'time': elapsed_ms,
            'message': message
        }
    
    def get_summary(self) -> Dict:
        """Get summary of all stage timings"""
        return {
            'stages': self.stages,
            'total_time': sum(s.get('time', 0) for s in self.stages.values() if s.get('time'))
        }
