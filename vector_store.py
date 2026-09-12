"""
JustiAssist Vector Store - 2026-Ready MVP
FAISS-based dual index with separate statutory and case law indices
"""

import pickle
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi

from config import (
    EMBEDDING_MODEL,
    VECTOR_STORE_PATH,
    STATUTORY_INDEX_PATH,
    CASE_LAW_INDEX_PATH,
    TOP_K_STATUTORY,
    TOP_K_CASE_LAW,
    DatasetType,
    CHUNKING_CONFIG
)
from chunker import TextChunk


from retrieval.models import SearchResult


class VectorStore:
    """
    Dual FAISS vector store for legal documents.
    
    Separate indices (NEVER mixed):
    1. Statutory Index: IPC, CrPC, BNS, Constitution, QA datasets
    2. Case Law Index: Bail judgments, Supreme Court judgments
    """
    
    def __init__(self, embedding_model: str = EMBEDDING_MODEL):
        self.embedding_model_name = embedding_model
        self.embedding_model: SentenceTransformer = None
        self.embedding_dim: int = 384  # Default for MiniLM
        
        # FAISS indices (explicitly separate)
        self.statutory_index: Optional[faiss.Index] = None
        self.case_law_index: Optional[faiss.Index] = None
        
        # Backward compatibility alias
        self.bail_index: Optional[faiss.Index] = None
        
        # Metadata storage (explicitly separate)
        self.statutory_metadata: List[Dict[str, Any]] = []
        self.case_law_metadata: List[Dict[str, Any]] = []
        self.bail_metadata: List[Dict[str, Any]] = []  # Alias
        
        # BM25 indices for hybrid search
        self.statutory_bm25: Optional[BM25Okapi] = None
        self.statutory_corpus: List[List[str]] = []
        self.case_law_bm25: Optional[BM25Okapi] = None
        self.case_law_corpus: List[List[str]] = []
        
        # Track loaded embedding model
        self._loaded_embedding_model: str = None
    
    def _load_embedding_model(self):
        """Lazy load embedding model with change detection"""
        if self.embedding_model is None or self._loaded_embedding_model != self.embedding_model_name:
            print(f"Loading embedding model: {self.embedding_model_name}")
            self.embedding_model = SentenceTransformer(self.embedding_model_name)
            self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
            self._loaded_embedding_model = self.embedding_model_name
            print(f"Embedding dimension: {self.embedding_dim}")
    
    def _create_embeddings(self, texts: List[str], show_progress: bool = True) -> np.ndarray:
        """Create embeddings for text list"""
        self._load_embedding_model()
        
        embeddings = self.embedding_model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=show_progress,
            normalize_embeddings=True  # For cosine similarity
        )
        return embeddings.astype('float32')
    
    def _create_faiss_index(self, embeddings: np.ndarray) -> faiss.Index:
        """Create FAISS index from embeddings"""
        index = faiss.IndexFlatIP(self.embedding_dim)  # Inner product (cosine with normalized vectors)
        index.add(embeddings)
        return index
    
    def _tokenize_legal(self, text: str) -> List[str]:
        """
        Legal-aware tokenizer preserving section numbers.
        Handles patterns like '167(2)(a)', 'IPC 302', 'CrPC_437'
        """
        # Preserve subsection patterns: 167(2)(a) -> 167_2_a
        text = re.sub(r'(\d+)\((\w+)\)', r'\1_\2', text)
        # Tokenize on word boundaries
        tokens = re.findall(r'\b[\w_]+\b', text.lower())
        return tokens
    
    def _extract_section_from_query(self, query: str) -> Optional[str]:
        """
        Extract specific section reference from query.
        Returns normalized section string like 'IPC_297' or 'CrPC_438'.
        """
        query_upper = query.upper()
        
        # Pattern: "IPC 297", "IPC-297", "IPC_297", "Section 297 IPC", "IPC Section 297"
        patterns = [
            r'\b(IPC|CRPC|BNS|BNSS)\s*[-_]?\s*(\d+[A-Z]?)\b',  # IPC 297, IPC-297
            r'\b(IPC|CRPC|BNS|BNSS)\s+SECTION\s*(\d+[A-Z]?)\b',  # IPC Section 297
            r'\bSECTION\s*(\d+[A-Z]?)\s+(IPC|CRPC|BNS|BNSS)\b',  # Section 297 IPC
            r'\bSECTION\s*(\d+[A-Z]?)\s+OF\s+(IPC|CRPC|BNS|BNSS)\b',  # Section 297 of IPC
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query_upper)
            if match:
                groups = match.groups()
                if len(groups) == 2:
                    # Handle both orders (LAW NUM) and (NUM LAW)
                    if groups[0] in ('IPC', 'CRPC', 'BNS', 'BNSS'):
                        law, num = groups
                    else:
                        num, law = groups
                    return f"{law}_{num}"
        
        return None
    
    def build_statutory_index(self, chunks: List[TextChunk]):
        """Build FAISS + BM25 index for statutory documents (laws, sections, QA)"""
        if not chunks:
            print("No statutory chunks provided")
            return
        
        print(f"\n[STATUTORY INDEX] Building with {len(chunks)} chunks...")
        
        texts = [chunk.text for chunk in chunks]
        self.statutory_metadata = [chunk.to_dict() for chunk in chunks]
        
        # Build FAISS semantic index
        embeddings = self._create_embeddings(texts)
        self.statutory_index = self._create_faiss_index(embeddings)
        
        # Build BM25 keyword index
        self.statutory_corpus = [self._tokenize_legal(text) for text in texts]
        self.statutory_bm25 = BM25Okapi(self.statutory_corpus)
        
        print(f"[STATUTORY INDEX] Built: {self.statutory_index.ntotal} vectors + BM25")
    
    def build_case_law_index(self, chunks: List[TextChunk]):
        """Build index for case law (judgments, precedents)"""
        if not chunks:
            print("No case law chunks provided")
            return
        
        print(f"\n[CASE LAW INDEX] Building with {len(chunks)} chunks...")
        
        texts = [chunk.text for chunk in chunks]
        self.case_law_metadata = [chunk.to_dict() for chunk in chunks]
        
        embeddings = self._create_embeddings(texts)
        self.case_law_index = self._create_faiss_index(embeddings)
        
        # Backward compatibility
        self.bail_index = self.case_law_index
        self.bail_metadata = self.case_law_metadata
        
        print(f"[CASE LAW INDEX] Built: {self.case_law_index.ntotal} vectors")
    
    # Backward compatibility alias
    def build_bail_index(self, chunks: List[TextChunk]):
        """Alias for build_case_law_index"""
        return self.build_case_law_index(chunks)
    
    def search_statutory(
        self,
        query: str,
        top_k: int = TOP_K_STATUTORY,
        law_type_filter: Optional[str] = None
    ) -> List[SearchResult]:
        """Search statutory index"""
        if self.statutory_index is None:
            return []
        
        self._load_embedding_model()
        
        query_embedding = self.embedding_model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True
        ).astype('float32')
        
        # Search more if filtering
        search_k = top_k * 3 if law_type_filter else top_k
        search_k = min(search_k, self.statutory_index.ntotal)
        
        scores, indices = self.statutory_index.search(query_embedding, search_k)
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            
            meta = self.statutory_metadata[idx]
            
            # Apply filter if specified
            if law_type_filter and meta.get('law_type', '').upper() != law_type_filter.upper():
                continue
            
            result = SearchResult(
                chunk_id=meta.get('chunk_id', ''),
                text=meta.get('text', ''),
                score=float(score),
                law_type=meta.get('law_type', ''),
                section_number=meta.get('section_number', ''),
                source_dataset=meta.get('source_dataset', ''),
                dataset_type=meta.get('dataset_type', 'statutory'),
                metadata=meta.get('metadata', {})
            )
            results.append(result)
            
            if len(results) >= top_k:
                break
        
        return results
    
    def hybrid_search_statutory(
        self,
        query: str,
        top_k: int = TOP_K_STATUTORY,
        semantic_weight: float = 0.6,
        bm25_weight: float = 0.4,
        section_boost: float = 2.0,
        law_type_boost: float = 1.5
    ) -> List[SearchResult]:
        """
        Hybrid search combining semantic (FAISS) + keyword (BM25) signals.
        Uses weighted score fusion for better retrieval of exact legal references.
        
        When a specific section is detected in the query (e.g., 'IPC 297'),
        applies a section boost to matching results to ensure exact matches
        appear at the top.
        
        Args:
            query: Search query
            top_k: Number of results to return
            semantic_weight: Weight for semantic similarity (default 0.6)
            bm25_weight: Weight for BM25 keyword match (default 0.4)
            section_boost: Bonus score for exact section matches (default 2.0)
            law_type_boost: Bonus score for chunks matching the explicitly requested law type (default 0.5)
            
        Returns:
            List of SearchResult with fused scores
        """
        # Fallback to semantic-only if BM25 not available
        if self.statutory_index is None:
            return []
        
        self._load_embedding_model()
        
        # Extract specific section reference FIRST (e.g., "IPC_297")
        target_section = self._extract_section_from_query(query)
        if target_section:
            print(f"[HYBRID] Detected section: {target_section} - will apply section boost")
            
        # Extract general law type reference if no exact section
        target_law_type = None
        query_lower = query.lower()
        if "bns" in query_lower or "bharatiya nyaya sanhita" in query_lower:
            target_law_type = "BNS"
        elif "ipc" in query_lower or "indian penal code" in query_lower:
            target_law_type = "IPC"
        elif "crpc" in query_lower or "code of criminal procedure" in query_lower:
            target_law_type = "CrPC"
        elif "constitution" in query_lower:
            target_law_type = "Constitution"
            
        if target_law_type and not target_section:
            print(f"[HYBRID] Detected requested law type: {target_law_type} - will apply law_type boost")
        
        # If no BM25 but section detected, use semantic + section boost
        if self.statutory_bm25 is None:
            print("[HYBRID] No BM25 - using semantic search with section boost")
            # Get semantic results
            semantic_results = self.search_statutory(query, top_k * 2)
            
            # If section detected, find matching chunks and boost them
            if target_section:
                section_matches = []
                other_results = []
                
                # First, get all indices matching the section directly from metadata
                for idx, meta in enumerate(self.statutory_metadata):
                    section_num = meta.get('section_number', '').upper()
                    if target_section.upper() in section_num:
                        # Create result for direct section match with high score
                        section_matches.append(SearchResult(
                            chunk_id=meta.get('chunk_id', ''),
                            text=meta.get('text', ''),
                            score=1.0 + section_boost,  # Boost above all semantic results
                            law_type=meta.get('law_type', ''),
                            section_number=meta.get('section_number', ''),
                            source_dataset=meta.get('source_dataset', ''),
                            dataset_type=meta.get('dataset_type', 'statutory'),
                            metadata={**meta.get('metadata', {}), 'search_type': 'section_boost'}
                        ))
                
                print(f"[HYBRID] Found {len(section_matches)} direct section matches for {target_section}")
                
                # Add semantic results that don't duplicate section matches
                section_ids = {r.section_number for r in section_matches}
                for r in semantic_results:
                    if r.section_number not in section_ids:
                        other_results.append(r)
                
                # Combine: section matches first, then other results
                return section_matches[:top_k] if len(section_matches) >= top_k else (section_matches + other_results)[:top_k]
            else:
                return semantic_results[:top_k]
        
        # 1. Semantic search (over-retrieve for fusion)
        query_embedding = self.embedding_model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True
        ).astype('float32')
        
        retrieve_k = min(top_k * 3, self.statutory_index.ntotal)
        semantic_scores, semantic_indices = self.statutory_index.search(query_embedding, retrieve_k)
        
        # Build semantic score map {index: score}
        semantic_map = {}
        for score, idx in zip(semantic_scores[0], semantic_indices[0]):
            if idx != -1:
                semantic_map[idx] = float(score)
        
        # 2. BM25 search
        tokenized_query = self._tokenize_legal(query)
        bm25_scores_raw = self.statutory_bm25.get_scores(tokenized_query)
        
        # Normalize BM25 scores to 0-1 range
        max_bm25 = max(bm25_scores_raw) if max(bm25_scores_raw) > 0 else 1.0
        bm25_map = {
            i: score / max_bm25 
            for i, score in enumerate(bm25_scores_raw) 
            if score > 0.05  # Filter noise
        }
        
        # 3. If section detected, find ALL indices that match that section
        #    (even if not in semantic/BM25 results)
        section_match_indices = set()
        if target_section:
            for idx, meta in enumerate(self.statutory_metadata):
                section_num = meta.get('section_number', '').upper()
                if target_section.upper() in section_num:
                    section_match_indices.add(idx)
            print(f"[HYBRID] Found {len(section_match_indices)} chunks matching {target_section}")
        
        # 4. Fuse scores from all sources
        all_indices = set(semantic_map.keys()) | set(bm25_map.keys()) | section_match_indices
        
        fused_results = []
        for idx in all_indices:
            sem_score = semantic_map.get(idx, 0.0)
            bm25_score = bm25_map.get(idx, 0.0)
            
            # Weighted fusion
            fused_score = (semantic_weight * sem_score) + (bm25_weight * bm25_score)
            
            # Apply section boost if this result matches target section
            meta = self.statutory_metadata[idx]
            section_num = meta.get('section_number', '').upper()
            has_section_boost = False
            if target_section and target_section.upper() in section_num:
                fused_score += section_boost
                has_section_boost = True
                
            has_law_type_boost = False
            if target_law_type and not target_section:
                if meta.get('law_type', '').upper() == target_law_type.upper():
                    fused_score += law_type_boost
                    has_law_type_boost = True
                else:
                    # Penalize non-matching law types when a specific one was requested
                    fused_score -= law_type_boost * 0.5
            
            # Additional logic to determine search_type label
            search_type = 'hybrid'
            if has_section_boost:
                search_type = 'hybrid_section_boosted'
            elif has_law_type_boost:
                search_type = 'hybrid_law_type_boosted'
            
            result = SearchResult(
                chunk_id=meta.get('chunk_id', ''),
                text=meta.get('text', ''),
                score=fused_score,
                law_type=meta.get('law_type', ''),
                section_number=meta.get('section_number', ''),
                source_dataset=meta.get('source_dataset', ''),
                dataset_type=meta.get('dataset_type', 'statutory'),
                metadata={
                    **meta.get('metadata', {}),
                    'semantic_score': round(sem_score, 3),
                    'bm25_score': round(bm25_score, 3),
                    'section_boost': section_boost if has_section_boost else 0.0,
                    'law_type_boost': law_type_boost if has_law_type_boost else 0.0,
                    'search_type': search_type
                }
            )
            fused_results.append(result)
        
        # Sort by fused score and return top_k
        fused_results.sort(key=lambda x: x.score, reverse=True)
        return fused_results[:top_k]

    
    def search_case_law(
        self,
        query: str,
        top_k: int = TOP_K_CASE_LAW
    ) -> List[SearchResult]:
        """Search case law index"""
        if self.case_law_index is None:
            return []
        
        self._load_embedding_model()
        
        query_embedding = self.embedding_model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True
        ).astype('float32')
        
        k = min(top_k, self.case_law_index.ntotal)
        scores, indices = self.case_law_index.search(query_embedding, k)
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            
            meta = self.case_law_metadata[idx]
            result = SearchResult(
                chunk_id=meta.get('chunk_id', ''),
                text=meta.get('text', ''),
                score=float(score),
                law_type=meta.get('law_type', 'Judgment'),
                section_number=meta.get('section_number', ''),
                source_dataset=meta.get('source_dataset', ''),
                dataset_type=meta.get('dataset_type', 'case_law'),
                metadata=meta.get('metadata', {})
            )
            results.append(result)
        
        return results
    
    # Backward compatibility alias
    def search_bail(self, query: str, top_k: int = TOP_K_CASE_LAW) -> List[SearchResult]:
        """Alias for search_case_law"""
        return self.search_case_law(query, top_k)
    
    def save(self, base_path: Path = VECTOR_STORE_PATH):
        """Save indices and metadata to disk"""
        base_path.mkdir(parents=True, exist_ok=True)
        
        # Save statutory index
        if self.statutory_index is not None:
            statutory_path = base_path / "statutory"
            statutory_path.mkdir(exist_ok=True)
            
            faiss.write_index(self.statutory_index, str(statutory_path / "index.faiss"))
            with open(statutory_path / "metadata.pkl", 'wb') as f:
                pickle.dump(self.statutory_metadata, f)
            with open(statutory_path / "embedding_model.txt", 'w') as f:
                f.write(self.embedding_model_name)
            # Save BM25 corpus for hybrid search
            if self.statutory_corpus:
                with open(statutory_path / "bm25_corpus.pkl", 'wb') as f:
                    pickle.dump(self.statutory_corpus, f)
            print(f"Saved statutory index to {statutory_path}")
        
        # Save case law index
        if self.case_law_index is not None:
            case_law_path = base_path / "case_law"
            case_law_path.mkdir(exist_ok=True)
            
            faiss.write_index(self.case_law_index, str(case_law_path / "index.faiss"))
            with open(case_law_path / "metadata.pkl", 'wb') as f:
                pickle.dump(self.case_law_metadata, f)
            with open(case_law_path / "embedding_model.txt", 'w') as f:
                f.write(self.embedding_model_name)
            print(f"Saved case law index to {case_law_path}")
    
    def load(self, base_path: Path = VECTOR_STORE_PATH) -> bool:
        """Load indices from disk with embedding model verification"""
        self._load_embedding_model()
        
        loaded = False
        
        # Load statutory index
        statutory_path = base_path / "statutory"
        if (statutory_path / "index.faiss").exists():
            # Check embedding model match
            if (statutory_path / "embedding_model.txt").exists():
                with open(statutory_path / "embedding_model.txt", 'r') as f:
                    saved_model = f.read().strip()
                if saved_model != self.embedding_model_name:
                    print(f"WARNING: Index was built with {saved_model}, current model is {self.embedding_model_name}")
                    print("Consider rebuilding indices with: python vector_store.py")
            
            self.statutory_index = faiss.read_index(str(statutory_path / "index.faiss"))
            with open(statutory_path / "metadata.pkl", 'rb') as f:
                self.statutory_metadata = pickle.load(f)
            # Load BM25 corpus for hybrid search
            if (statutory_path / "bm25_corpus.pkl").exists():
                with open(statutory_path / "bm25_corpus.pkl", 'rb') as f:
                    self.statutory_corpus = pickle.load(f)
                self.statutory_bm25 = BM25Okapi(self.statutory_corpus)
                print(f"Loaded statutory index: {self.statutory_index.ntotal} vectors + BM25")
            else:
                print(f"Loaded statutory index: {self.statutory_index.ntotal} vectors (no BM25)")
            loaded = True
        
        # Load case law index
        case_law_path = base_path / "case_law"
        if (case_law_path / "index.faiss").exists():
            self.case_law_index = faiss.read_index(str(case_law_path / "index.faiss"))
            with open(case_law_path / "metadata.pkl", 'rb') as f:
                self.case_law_metadata = pickle.load(f)
            
            # Backward compatibility
            self.bail_index = self.case_law_index
            self.bail_metadata = self.case_law_metadata
            
            print(f"Loaded case law index: {self.case_law_index.ntotal} vectors")
            loaded = True
        
        # Legacy: try loading old "bail" folder
        bail_path = base_path / "bail"
        if not loaded and (bail_path / "index.faiss").exists():
            self.case_law_index = faiss.read_index(str(bail_path / "index.faiss"))
            with open(bail_path / "metadata.pkl", 'rb') as f:
                self.case_law_metadata = pickle.load(f)
            self.bail_index = self.case_law_index
            self.bail_metadata = self.case_law_metadata
            print(f"Loaded legacy bail index: {self.case_law_index.ntotal} vectors")
            loaded = True
        
        return loaded
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get index statistics"""
        return {
            "statutory": {
                "total_vectors": self.statutory_index.ntotal if self.statutory_index else 0,
                "metadata_count": len(self.statutory_metadata),
                "index_type": "STATUTORY"
            },
            "case_law": {
                "total_vectors": self.case_law_index.ntotal if self.case_law_index else 0,
                "metadata_count": len(self.case_law_metadata),
                "index_type": "CASE_LAW"
            },
            "embedding_model": self.embedding_model_name
        }


def build_indices() -> VectorStore:
    """
    Build vector indices from all auto-discovered datasets.
    This is the main entry point for index construction.
    """
    from data_loader import DataLoader
    from chunker import TextChunker
    from config import DatasetType
    
    print("=" * 60)
    print("BUILDING VECTOR INDICES")
    print("=" * 60)
    
    # Initialize
    loader = DataLoader()
    vector_store = VectorStore()
    
    # Load and chunk statutory documents
    print("\n--- Processing STATUTORY Documents ---")
    statutory_docs = loader.load_all_statutory()
    print(f"Loaded {len(statutory_docs)} statutory documents")
    
    statutory_chunker = TextChunker.for_dataset_type(DatasetType.STATUTORY)
    statutory_chunks = statutory_chunker.chunk_documents(statutory_docs)
    print(f"Created {len(statutory_chunks)} statutory chunks")
    
    # Load and chunk case law documents
    print("\n--- Processing CASE LAW Documents ---")
    case_law_docs = loader.load_case_law()
    print(f"Loaded {len(case_law_docs)} case law documents")
    
    case_law_chunker = TextChunker.for_dataset_type(DatasetType.CASE_LAW)
    case_law_chunks = case_law_chunker.chunk_documents(case_law_docs)
    print(f"Created {len(case_law_chunks)} case law chunks")
    
    # Build indices (SEPARATE - never mixed)
    print("\n--- Building Indices ---")
    vector_store.build_statutory_index(statutory_chunks)
    vector_store.build_case_law_index(case_law_chunks)
    
    # Save
    print("\n--- Saving Indices ---")
    vector_store.save()
    
    print("\n" + "=" * 60)
    print("INDEX BUILDING COMPLETE")
    print("=" * 60)
    stats = vector_store.get_statistics()
    print(f"Statutory: {stats['statutory']['total_vectors']} vectors")
    print(f"Case Law: {stats['case_law']['total_vectors']} vectors")
    print(f"Embedding Model: {stats['embedding_model']}")
    
    return vector_store


if __name__ == "__main__":
    # Build indices when run directly
    build_indices()
