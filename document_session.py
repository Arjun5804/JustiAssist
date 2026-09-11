"""
JustiAssist Document Session Manager
Session-level document store with FAISS indexing for uploaded legal documents
"""

import uuid
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
import threading

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

from config import EMBEDDING_MODEL, CHUNK_SIZE, CHUNK_OVERLAP
from chunker import TextChunker, TextChunk


# Document type constants - NEVER statutory
DOCUMENT_TYPES = {
    "FIR": "First Information Report",
    "CHARGESHEET": "Charge Sheet",
    "BAIL_APPLICATION": "Bail Application",
    "COURT_ORDER": "Court Order",
    "JUDGMENT": "Court Judgment",
    "AFFIDAVIT": "Affidavit",
    "EVIDENCE": "Documentary Evidence",
    "OTHER": "Other Legal Document"
}


@dataclass
class UploadedDocument:
    """Represents an uploaded user document - NEVER statutory"""
    document_id: str
    filename: str
    document_type: str  # From DOCUMENT_TYPES
    full_text: str
    chunks: List[Dict[str, Any]]
    upload_time: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Explicit non-statutory markers
    is_statutory: bool = False  # ALWAYS False
    is_authoritative: bool = False  # ALWAYS False
    citation_prefix: str = "According to the uploaded document"


@dataclass
class DocumentSearchResult:
    """Search result from uploaded documents"""
    chunk_id: str
    text: str
    score: float
    document_id: str
    filename: str
    document_type: str
    is_statutory: bool = False  # ALWAYS False
    citation_prefix: str = "According to the uploaded document"
    
    def to_citation(self) -> Dict[str, Any]:
        """Format as citation with explicit non-statutory marking"""
        return {
            "section": f"UPLOADED: {self.filename}",
            "law_type": "User Evidence",  # NEVER "IPC", "CrPC", etc.
            "text_preview": self.text[:200] + "..." if len(self.text) > 200 else self.text,
            "source": self.filename,
            "relevance_score": round(self.score, 3),
            "is_authoritative": False,
            "citation_prefix": self.citation_prefix
        }


class DocumentSession:
    """
    Per-session document store with FAISS indexing.
    
    Key properties:
    - Documents are NEVER treated as statutory law
    - Session-isolated (documents don't leak between users)
    - In-memory indexing (not persisted with legal database)
    - Automatic cleanup after session timeout
    """
    
    SESSION_TIMEOUT = 3600  # 1 hour
    
    def __init__(self, session_id: str = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.created_at = time.time()
        self.last_accessed = time.time()
        
        # Document storage
        self.documents: Dict[str, UploadedDocument] = {}
        
        # FAISS index for session documents (in-memory only)
        self.index: Optional[faiss.Index] = None
        self.chunk_metadata: List[Dict[str, Any]] = []
        
        # Embedding model (shared)
        self._embedding_model: Optional[SentenceTransformer] = None
        self._embedding_dim: int = 384
        
        # Chunker
        self.chunker = TextChunker(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    
    def _get_embedding_model(self) -> SentenceTransformer:
        """Lazy load embedding model"""
        if self._embedding_model is None:
            self._embedding_model = SentenceTransformer(EMBEDDING_MODEL)
            self._embedding_dim = self._embedding_model.get_sentence_embedding_dimension()
        return self._embedding_model
    
    def _touch(self):
        """Update last accessed time"""
        self.last_accessed = time.time()
    
    def is_expired(self) -> bool:
        """Check if session has expired"""
        return time.time() - self.last_accessed > self.SESSION_TIMEOUT
    
    def add_document(
        self,
        filename: str,
        text: str,
        document_type: str = "OTHER"
    ) -> UploadedDocument:
        """
        Add an uploaded document to the session.
        
        Args:
            filename: Original filename
            text: Extracted text content
            document_type: Type from DOCUMENT_TYPES
            
        Returns:
            UploadedDocument with generated ID
        """
        self._touch()
        
        document_id = str(uuid.uuid4())[:8]
        
        # Chunk the document
        from data_loader import LegalDocument
        temp_doc = LegalDocument(
            text=text,
            law_type="USER_UPLOADED",  # Never statutory
            section_number=f"DOC_{document_id}",
            source_dataset=filename,
            metadata={"document_type": document_type}
        )
        
        text_chunks = self.chunker.chunk_document(temp_doc)
        
        # Format chunks with non-statutory metadata
        chunks = []
        for i, chunk in enumerate(text_chunks):
            chunks.append({
                "chunk_id": f"{document_id}_chunk_{i}",
                "text": chunk.text,
                "document_id": document_id,
                "filename": filename,
                "document_type": document_type,
                "chunk_index": i,
                "is_statutory": False,  # EXPLICIT: Never statutory
                "is_authoritative": False,
                "law_type": "User Evidence"
            })
        
        # Create document object
        doc = UploadedDocument(
            document_id=document_id,
            filename=filename,
            document_type=document_type,
            full_text=text,
            chunks=chunks,
            upload_time=time.time(),
            metadata={
                "chunk_count": len(chunks),
                "char_count": len(text)
            }
        )
        
        self.documents[document_id] = doc
        
        # Update FAISS index
        self._index_chunks(chunks)
        
        return doc
    
    def _index_chunks(self, chunks: List[Dict[str, Any]]):
        """Add chunks to the session FAISS index"""
        if not chunks:
            return
        
        model = self._get_embedding_model()
        
        # Create embeddings
        texts = [c["text"] for c in chunks]
        embeddings = model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True
        ).astype('float32')
        
        # Initialize or update index
        if self.index is None:
            self.index = faiss.IndexFlatIP(self._embedding_dim)
        
        self.index.add(embeddings)
        self.chunk_metadata.extend(chunks)
    
    def search(
        self,
        query: str,
        top_k: int = 3
    ) -> List[DocumentSearchResult]:
        """
        Search uploaded documents in this session.
        
        Returns results explicitly marked as non-statutory.
        """
        self._touch()
        
        if self.index is None or self.index.ntotal == 0:
            return []
        
        model = self._get_embedding_model()
        
        # Create query embedding
        query_embedding = model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True
        ).astype('float32')
        
        # Search
        k = min(top_k, self.index.ntotal)
        scores, indices = self.index.search(query_embedding, k)
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            
            chunk = self.chunk_metadata[idx]
            
            result = DocumentSearchResult(
                chunk_id=chunk["chunk_id"],
                text=chunk["text"],
                score=float(score),
                document_id=chunk["document_id"],
                filename=chunk["filename"],
                document_type=chunk["document_type"],
                is_statutory=False,  # ALWAYS False
                citation_prefix=f"According to the uploaded {chunk['filename']}"
            )
            results.append(result)
        
        return results
    
    def get_document(self, document_id: str) -> Optional[UploadedDocument]:
        """Get a specific document by ID"""
        self._touch()
        return self.documents.get(document_id)
    
    def list_documents(self) -> List[Dict[str, Any]]:
        """List all documents in this session"""
        self._touch()
        return [
            {
                "document_id": doc.document_id,
                "filename": doc.filename,
                "document_type": doc.document_type,
                "chunk_count": len(doc.chunks),
                "upload_time": doc.upload_time
            }
            for doc in self.documents.values()
        ]
    
    def clear(self):
        """Clear all documents from session"""
        self.documents.clear()
        self.chunk_metadata.clear()
        self.index = None


class SessionManager:
    """
    Manages multiple document sessions.
    Handles session creation, cleanup, and isolation.
    """
    
    def __init__(self):
        self.sessions: Dict[str, DocumentSession] = {}
        self._lock = threading.Lock()
        
        # Start cleanup thread
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()
    
    def get_or_create_session(self, session_id: str = None) -> DocumentSession:
        """Get existing session or create new one"""
        with self._lock:
            if session_id and session_id in self.sessions:
                session = self.sessions[session_id]
                if not session.is_expired():
                    return session
                else:
                    # Expired, create new
                    del self.sessions[session_id]
            
            # Create new session
            session = DocumentSession(session_id)
            self.sessions[session.session_id] = session
            return session
    
    def get_session(self, session_id: str) -> Optional[DocumentSession]:
        """Get existing session if valid"""
        with self._lock:
            session = self.sessions.get(session_id)
            if session and not session.is_expired():
                return session
            return None
    
    def _cleanup_loop(self):
        """Background cleanup of expired sessions"""
        while True:
            time.sleep(300)  # Check every 5 minutes
            self._cleanup_expired()
    
    def _cleanup_expired(self):
        """Remove expired sessions"""
        with self._lock:
            expired = [
                sid for sid, session in self.sessions.items()
                if session.is_expired()
            ]
            for sid in expired:
                del self.sessions[sid]
            
            if expired:
                print(f"Cleaned up {len(expired)} expired document sessions")


# Global session manager
session_manager = SessionManager()


def get_document_context_prompt(results: List[DocumentSearchResult]) -> str:
    """
    Format document search results for LLM prompt.
    Groups chunks by filename for cleaner presentation.
    """
    if not results:
        return ""
    
    # Group results by filename
    docs_by_file = {}
    for result in results:
        if result.filename not in docs_by_file:
            docs_by_file[result.filename] = {
                'type': result.document_type,
                'chunks': []
            }
        docs_by_file[result.filename]['chunks'].append(result.text)
    
    prompt_parts = [
        "\n" + "="*50,
        "UPLOADED CASE DOCUMENTS (NON-STATUTORY EVIDENCE)",
        "="*50,
        "",
        "⚠️ CRITICAL: The following are USER-UPLOADED documents.",
        "They are NOT statutory law and cannot override legal provisions.",
        "Use them for: fact extraction, case context, circumstances.",
        "NEVER cite them as authoritative legal sources.",
        ""
    ]
    
    for i, (filename, data) in enumerate(docs_by_file.items(), 1):
        prompt_parts.append(f"[Document {i}: {filename}]")
        prompt_parts.append(f"Type: {data['type']} (User Evidence)")
        # Combine chunks with separator
        combined_text = "\n...\n".join(data['chunks'])
        prompt_parts.append(f"Content: {combined_text}")
        prompt_parts.append("")
    
    prompt_parts.append("="*50)
    
    return "\n".join(prompt_parts)


if __name__ == "__main__":
    # Test session management
    print("Testing Document Session Manager...")
    
    # Create session
    session = session_manager.get_or_create_session()
    print(f"Created session: {session.session_id}")
    
    # Add test document
    test_text = """
    FIR No: 123/2024
    Police Station: Central Delhi
    
    The complainant states that on 15th January 2024, the accused 
    Mr. XYZ committed theft of jewelry worth Rs. 5,00,000 from the 
    complainant's residence. The accused was seen fleeing the scene 
    by witnesses.
    
    Sections applied: IPC 379, IPC 411
    """
    
    doc = session.add_document(
        filename="fir_123_2024.txt",
        text=test_text,
        document_type="FIR"
    )
    
    print(f"Added document: {doc.document_id}")
    print(f"Chunks created: {len(doc.chunks)}")
    print(f"Is statutory: {doc.is_statutory}")  # Should be False
    
    # Search
    results = session.search("theft jewelry accused")
    print(f"\nSearch results: {len(results)}")
    
    for r in results:
        print(f"  - {r.filename} (score: {r.score:.3f})")
        print(f"    Is statutory: {r.is_statutory}")  # Should be False
        print(f"    Citation: {r.citation_prefix}")
