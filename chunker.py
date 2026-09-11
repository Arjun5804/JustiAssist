"""
JustiAssist Text Chunker - 2026-Ready MVP
Domain-aware chunking with content-type-specific parameters
"""

import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import tiktoken

from config import (
    DatasetType,
    CHUNKING_CONFIG,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    MAX_CONTEXT_TOKENS,
    CONTEXT_TRIM_PRIORITY,
    MIN_STATUTORY_CHUNKS
)


@dataclass
class TextChunk:
    """Represents a chunk of text with associated metadata"""
    chunk_id: str
    text: str
    law_type: str
    section_number: str
    source_dataset: str
    dataset_type: DatasetType = DatasetType.STATUTORY
    token_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "law_type": self.law_type,
            "section_number": self.section_number,
            "source_dataset": self.source_dataset,
            "dataset_type": self.dataset_type.value,
            "token_count": self.token_count,
            "metadata": self.metadata
        }


class TextChunker:
    """
    Domain-aware text chunker for legal documents.
    
    Features:
    - Content-type-specific chunk sizes (statutory, case_law, qa)
    - Token-based chunking with accurate counting
    - Overlap for context preservation
    - MAX_CONTEXT_TOKENS enforcement
    """
    
    def __init__(
        self, 
        chunk_size: int = None, 
        chunk_overlap: int = None,
        dataset_type: DatasetType = DatasetType.STATUTORY
    ):
        """
        Initialize chunker with optional override parameters.
        
        Args:
            chunk_size: Override chunk size (uses domain config if None)
            chunk_overlap: Override overlap (uses domain config if None)
            dataset_type: Default dataset type for chunking
        """
        self.dataset_type = dataset_type
        
        # Get domain-specific config or use overrides
        config = CHUNKING_CONFIG.get(dataset_type, CHUNKING_CONFIG[DatasetType.STATUTORY])
        self.chunk_size = chunk_size or config["chunk_size"]
        self.chunk_overlap = chunk_overlap or config["chunk_overlap"]
        
        # Use tiktoken for accurate token counting
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except:
            self.tokenizer = None
    
    @classmethod
    def for_dataset_type(cls, dtype: DatasetType) -> "TextChunker":
        """Factory method to create chunker for specific dataset type"""
        config = CHUNKING_CONFIG.get(dtype, CHUNKING_CONFIG[DatasetType.STATUTORY])
        return cls(
            chunk_size=config["chunk_size"],
            chunk_overlap=config["chunk_overlap"],
            dataset_type=dtype
        )
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        else:
            # Rough estimation: ~4 characters per token
            return len(text) // 4
    
    def chunk_text(self, text: str, dataset_type: DatasetType = None) -> List[str]:
        """
        Split text into chunks of approximately chunk_size tokens.
        Uses sentence boundaries when possible.
        """
        if not text or not text.strip():
            return []
        
        # Get type-specific chunking params if provided
        dtype = dataset_type or self.dataset_type
        config = CHUNKING_CONFIG.get(dtype, CHUNKING_CONFIG[DatasetType.STATUTORY])
        chunk_size = config["chunk_size"]
        chunk_overlap = config["chunk_overlap"]
        
        # If text is small enough, return as single chunk
        if self.count_tokens(text) <= chunk_size:
            return [text.strip()]
        
        # Split by sentence boundaries
        sentences = self._split_into_sentences(text)
        
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for sentence in sentences:
            sentence_tokens = self.count_tokens(sentence)
            
            # If single sentence exceeds chunk size, split it further
            if sentence_tokens > chunk_size:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
                    current_tokens = 0
                
                word_chunks = self._chunk_by_words(sentence, chunk_size)
                chunks.extend(word_chunks)
                continue
            
            # Check if adding this sentence exceeds limit
            if current_tokens + sentence_tokens > chunk_size:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                
                # Start new chunk with overlap
                overlap_sentences = self._get_overlap_sentences(current_chunk, chunk_overlap)
                current_chunk = overlap_sentences + [sentence]
                current_tokens = sum(self.count_tokens(s) for s in current_chunk)
            else:
                current_chunk.append(sentence)
                current_tokens += sentence_tokens
        
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return [c.strip() for c in chunks if c.strip()]
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences using regex"""
        # Handle common legal abbreviations
        text = re.sub(r'\bSec\.\s*', 'Section ', text)
        text = re.sub(r'\bArt\.\s*', 'Article ', text)
        text = re.sub(r'\bvs\.\s*', 'versus ', text)
        text = re.sub(r'\bv\.\s*', 'versus ', text)
        
        # Split on sentence endings
        sentence_pattern = r'(?<=[.!?])\s+(?=[A-Z\(\[])'
        sentences = re.split(sentence_pattern, text)
        
        return [s.strip() for s in sentences if s.strip()]
    
    def _chunk_by_words(self, text: str, chunk_size: int = None) -> List[str]:
        """Chunk long text by words when sentence splitting isn't enough"""
        words = text.split()
        chunks = []
        current_chunk = []
        current_tokens = 0
        max_tokens = chunk_size or self.chunk_size
        
        for word in words:
            word_tokens = self.count_tokens(word)
            
            if current_tokens + word_tokens > max_tokens:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                current_chunk = [word]
                current_tokens = word_tokens
            else:
                current_chunk.append(word)
                current_tokens += word_tokens
        
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return chunks
    
    def _get_overlap_sentences(self, sentences: List[str], overlap: int = None) -> List[str]:
        """Get sentences for overlap from the end of previous chunk"""
        if not sentences:
            return []
        
        max_overlap = overlap or self.chunk_overlap
        overlap_sentences = []
        overlap_tokens = 0
        
        for sentence in reversed(sentences):
            sentence_tokens = self.count_tokens(sentence)
            if overlap_tokens + sentence_tokens <= max_overlap:
                overlap_sentences.insert(0, sentence)
                overlap_tokens += sentence_tokens
            else:
                break
        
        return overlap_sentences
    
    def chunk_document(self, doc: "LegalDocument") -> List[TextChunk]:
        """
        Chunk a single LegalDocument into multiple TextChunks.
        Uses domain-aware chunking based on document type.
        """
        # Get dataset type from document
        dtype = getattr(doc, 'dataset_type', DatasetType.STATUTORY)
        
        text_chunks = self.chunk_text(doc.text, dtype)
        
        chunks = []
        for i, chunk_text in enumerate(text_chunks):
            chunk = TextChunk(
                chunk_id=f"{doc.section_number}_chunk_{i+1}",
                text=chunk_text,
                law_type=doc.law_type,
                section_number=doc.section_number,
                source_dataset=doc.source_dataset,
                dataset_type=dtype,
                token_count=self.count_tokens(chunk_text),
                metadata={
                    **doc.metadata,
                    "chunk_index": i,
                    "total_chunks": len(text_chunks),
                    "original_section": doc.section_number
                }
            )
            chunks.append(chunk)
        
        return chunks
    
    def chunk_documents(self, documents: List["LegalDocument"]) -> List[TextChunk]:
        """
        Chunk multiple documents using domain-aware settings.
        Returns a flat list of all chunks.
        """
        all_chunks = []
        
        for doc in documents:
            doc_chunks = self.chunk_document(doc)
            all_chunks.extend(doc_chunks)
        
        print(f"Created {len(all_chunks)} chunks from {len(documents)} documents")
        return all_chunks


class ContextTrimmer:
    """
    Trims retrieved context to fit within MAX_CONTEXT_TOKENS.
    Uses priority-based trimming as per configuration.
    """
    
    def __init__(self):
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except:
            self.tokenizer = None
    
    def count_tokens(self, text: str) -> int:
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        return len(text) // 4
    
    def trim_context(
        self,
        statutory_chunks: List[TextChunk],
        case_law_chunks: List[TextChunk],
        session_chunks: List[TextChunk] = None,
        max_tokens: int = MAX_CONTEXT_TOKENS
    ) -> Dict[str, List[TextChunk]]:
        """
        Trim context to fit within max_tokens.
        
        Priority (trim first to last):
        1. Session/uploaded docs
        2. Case law
        3. Statutory (never below MIN_STATUTORY_CHUNKS)
        """
        session_chunks = session_chunks or []
        
        # Calculate current totals
        def total_tokens(chunks):
            return sum(c.token_count or self.count_tokens(c.text) for c in chunks)
        
        current_total = (
            total_tokens(statutory_chunks) +
            total_tokens(case_law_chunks) +
            total_tokens(session_chunks)
        )
        
        if current_total <= max_tokens:
            return {
                "statutory": statutory_chunks,
                "case_law": case_law_chunks,
                "session": session_chunks
            }
        
        # Need to trim
        trimmed = {
            "statutory": list(statutory_chunks),
            "case_law": list(case_law_chunks),
            "session": list(session_chunks)
        }
        
        # Priority 1: Trim session docs first
        while total_tokens(trimmed["session"]) > 0 and self._total(trimmed) > max_tokens:
            if trimmed["session"]:
                trimmed["session"].pop()
        
        # Priority 2: Trim case law
        while len(trimmed["case_law"]) > 0 and self._total(trimmed) > max_tokens:
            trimmed["case_law"].pop()
        
        # Priority 3: Trim statutory (but keep minimum)
        while len(trimmed["statutory"]) > MIN_STATUTORY_CHUNKS and self._total(trimmed) > max_tokens:
            trimmed["statutory"].pop()
        
        return trimmed
    
    def _total(self, trimmed: Dict[str, List[TextChunk]]) -> int:
        """Calculate total tokens in trimmed context"""
        total = 0
        for chunks in trimmed.values():
            for c in chunks:
                total += c.token_count or self.count_tokens(c.text)
        return total


if __name__ == "__main__":
    # Test the chunker
    from data_loader import DataLoader, LegalDocument
    
    loader = DataLoader()
    
    # Test with statutory documents (default chunker)
    print("\n" + "=" * 60)
    print("Testing STATUTORY chunking (350-400 tokens)")
    print("=" * 60)
    statutory_chunker = TextChunker.for_dataset_type(DatasetType.STATUTORY)
    statutory_docs = loader.load_all_statutory()
    statutory_chunks = statutory_chunker.chunk_documents(statutory_docs)
    print(f"Statutory: {len(statutory_docs)} docs -> {len(statutory_chunks)} chunks")
    
    if statutory_chunks:
        sample = statutory_chunks[0]
        print(f"\nSample statutory chunk:")
        print(f"  ID: {sample.chunk_id}")
        print(f"  Tokens: {sample.token_count}")
        print(f"  Type: {sample.dataset_type.value}")
    
    # Test with case law documents
    print("\n" + "=" * 60)
    print("Testing CASE LAW chunking (500-600 tokens)")
    print("=" * 60)
    case_law_chunker = TextChunker.for_dataset_type(DatasetType.CASE_LAW)
    case_law_docs = loader.load_case_law()
    case_law_chunks = case_law_chunker.chunk_documents(case_law_docs)
    print(f"Case Law: {len(case_law_docs)} docs -> {len(case_law_chunks)} chunks")
    
    if case_law_chunks:
        sample = case_law_chunks[0]
        print(f"\nSample case law chunk:")
        print(f"  ID: {sample.chunk_id}")
        print(f"  Tokens: {sample.token_count}")
        print(f"  Type: {sample.dataset_type.value}")
    
    # Test context trimmer
    print("\n" + "=" * 60)
    print("Testing Context Trimmer")
    print("=" * 60)
    trimmer = ContextTrimmer()
    trimmed = trimmer.trim_context(
        statutory_chunks[:10],
        case_law_chunks[:5],
        max_tokens=2000
    )
    print(f"Trimmed: statutory={len(trimmed['statutory'])}, case_law={len(trimmed['case_law'])}")
