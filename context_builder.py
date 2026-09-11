"""
Justi Assist Context Builder
Evidence-aware context structuring for LLM prompts
"""

from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class ContextGroup:
    """Group of related legal content chunks"""
    group_type: str  # 'statutory', 'case_law', 'explanatory'
    law_type: str  # 'IPC', 'CrPC', etc.
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    
    def add_chunk(self, chunk: Dict[str, Any]):
        """Add chunk to this group"""
        self.chunks.append(chunk)
    
    def get_preview(self, max_chars: int = 500) -> str:
        """Get preview of chunks in this group"""
        previews = []
        for chunk in self.chunks[:3]:  # First 3 chunks
            text = chunk.get('text', '')
            section = chunk.get('section_number', 'N/A')
            preview = f"[{section}] {text[:200]}"
            previews.append(preview)
        return "\n".join(previews)


class ContextBuilder:
    """
    Builds structured, evidence-aware context for LLM prompts.
    
    Groups retrieved chunks by:1. Evidence type (statutory vs case law vs explanatory)
    2. Law type (IPC, CrPC, BNS, etc.)
    3. Relevance (higher scores first)
    
    Benefits:
    - LLM can distinguish authoritative law from supporting material
    - Easier to maintain citation accuracy
    - Better explainability
    """
    
    # Group priorities (higher = more important)
    GROUP_PRIORITIES = {
        'statutory_ipc': 10,
        'statutory_crpc': 9,
        'statutory_bns': 8,
        'statutory_bnss': 7,
        'statutory_constitution': 6,
        'case_law_supreme_court': 5,
        'case_law_high_court': 4,
        'case_law_other': 3,
        'explanatory': 2,
        'other': 1,
    }
    
    def build_structured_context(
        self,
        statutory_results: List[Any],
        case_law_results: List[Any] = None,
        uploaded_docs: List[Any] = None,
        max_tokens: int = 3000
    ) -> str:
        """
        Build structured context from search results.
        
        Args:
            statutory_results: Results from statutory index search
            case_law_results: Results from case law index search (optional)
            uploaded_docs: User-uploaded document chunks (optional)
            max_tokens: Maximum context length in tokens (approximate by chars * 0.25)
            
        Returns:
            Formatted context string with clear evidence grouping
        """
        # Group chunks by evidence type and law type
        groups = self._group_chunks(statutory_results, case_law_results, uploaded_docs)
        
        # Sort groups by priority
        sorted_groups = sorted(
            groups.values(),
            key=lambda g: self.GROUP_PRIORITIES.get(f"{g.group_type}_{g.law_type.lower()}", 0),
            reverse=True
        )
        
        # Build formatted context
        context_parts = []
        total_chars = 0
        max_chars = max_tokens * 4  # Rough approximation
        
        for group in sorted_groups:
            group_header = self._format_group_header(group)
            group_content = self._format_group_content(group)
            
            # Check if adding this group would exceed limit
            group_text = f"{group_header}\n{group_content}\n"
            if total_chars + len(group_text) > max_chars:
                # Try to add at least one chunk from this group
                if context_parts:  # If we already have some content
                    break
            
            context_parts.append(group_text)
            total_chars += len(group_text)
        
        # Assemble final context
        if not context_parts:
            return "No relevant legal context found."
        
        # Detect contradictions
        contradictions = self.detect_contradictions(groups)
        
        structured_context = "\n\n".join(context_parts)
        
        # Add metadata footer
        footer = self._generate_context_footer(groups)
        structured_context += f"\n\n{footer}"
        
        # Add contradiction warnings if any
        if contradictions:
            warnings = "\n\nCRITICAL CONTRADICTION WARNINGS:\n- " + "\n- ".join(contradictions)
            warnings += "\n\nNote: Please analyze these discrepancies carefully and mention them in your answer."
            structured_context += warnings
        
        return structured_context
    
    def _group_chunks(
        self,
        statutory_results: List[Any],
        case_law_results: List[Any] = None,
        uploaded_docs: List[Any] = None
    ) -> Dict[str, ContextGroup]:
        """Group chunks by evidence type and law type"""
        groups = {}
        
        # Process statutory results
        if statutory_results:
            for result in statutory_results:
                law_type = getattr(result, 'law_type', 'Unknown')
                dataset_type = getattr(result, 'dataset_type', 'statutory')
                
                group_key = f"statutory_{law_type}"
                if group_key not in groups:
                    groups[group_key] = ContextGroup(
                        group_type='statutory',
                        law_type=law_type
                    )
                
                groups[group_key].add_chunk({
                    'section_number': getattr(result, 'section_number', 'N/A'),
                    'text': getattr(result, 'text', ''),
                    'source': getattr(result, 'source_dataset', 'Unknown'),
                    'score': getattr(result, 'score', 0.0),
                    'is_authoritative': True,
                })
        
        # Process case law results
        if case_law_results:
            for result in case_law_results:
                law_type = getattr(result, 'law_type', 'Other')
                
                # Determine court level from metadata or source
                court_level = self._determine_court_level(result)
                group_key = f"case_law_{court_level}"
                
                if group_key not in groups:
                    groups[group_key] = ContextGroup(
                        group_type='case_law',
                        law_type=court_level.replace('_', ' ').title()
                    )
                
                groups[group_key].add_chunk({
                    'section_number': getattr(result, 'section_number', 'Case'),
                    'text': getattr(result, 'text', ''),
                    'source': getattr(result, 'source_dataset', 'Unknown'),
                    'score': getattr(result, 'score', 0.0),
                    'metadata': getattr(result, 'metadata', {}),
                    'is_authoritative': False,
                })
        
        # Process uploaded documents (NON-STATUTORY)
        if uploaded_docs:
            group_key = "uploaded_documents"
            if group_key not in groups:
                groups[group_key] = ContextGroup(
                    group_type='uploaded',
                    law_type='User Evidence'
                )
            
            for doc in uploaded_docs:
                groups[group_key].add_chunk({
                    'section_number': f"UPLOADED: {doc.get('filename', 'Document')}",
                    'text': doc.get('text', ''),
                    'source': doc.get('filename', 'Unknown'),
                    'score': doc.get('score', 0.0),
                    'is_authoritative': False,
                    'is_statutory': False,
                })
        
        return groups
    
    def _determine_court_level(self, result: Any) -> str:
        """Determine court level from result metadata or text"""
        text = getattr(result, 'text', '').lower()
        metadata = getattr(result, 'metadata', {})
        
        if 'supreme court' in text or 'sc' in metadata.get('court', '').lower():
            return 'supreme_court'
        elif 'high court' in text or 'hc' in metadata.get('court', '').lower():
            return 'high_court'
        else:
            return 'other'
    
    def detect_contradictions(self, groups: Dict[str, ContextGroup]) -> List[str]:
        """
        Detect potential contradictions in retrieved context.
        Focuses on conflicting punishment terms or conditions for the same section.
        """
        contradictions = []
        section_map = defaultdict(list)
        
        # Map chunks by section
        for group in groups.values():
            for chunk in group.chunks:
                section = chunk.get('section_number', 'N/A')
                if section != 'N/A':
                    section_map[section].append(chunk)
        
        # Check for conflicts within same section
        for section, chunks in section_map.items():
            if len(chunks) < 2:
                continue
            
            # 1. Punishment Term Conflicts (e.g. "3 years" vs "7 years")
            import re
            years_pattern = r'(\d+)\s+years'
            terms = set()
            for chunk in chunks:
                matches = re.findall(years_pattern, chunk['text'], re.IGNORECASE)
                terms.update(matches)
            
            if len(terms) > 1:
                contradictions.append(
                    f"Conflicting punishment terms found for {section}: {', '.join(terms)} years. "
                    "Check if updated amendments are conflicting with older laws."
                )
                
            # 2. Bailable vs Non-bailable
            bailable_status = set()
            for chunk in chunks:
                text_lower = chunk['text'].lower()
                if 'non-bailable' in text_lower:
                    bailable_status.add('non-bailable')
                elif 'bailable' in text_lower and 'non-bailable' not in text_lower:
                    bailable_status.add('bailable')
            
            if len(bailable_status) > 1:
                contradictions.append(
                    f"Conflicting bail status found for {section}: {', '.join(bailable_status)}. "
                    "Verify current legal status."
                )
                
        return contradictions

    def _format_group_header(self, group: ContextGroup) -> str:
        """Format group header for display"""
        if group.group_type == 'statutory':
            header = f"═══ STATUTORY PROVISIONS: {group.law_type.upper()} ═══"
        elif group.group_type == 'case_law':
            header = f"═══ CASE LAW PRECEDENTS: {group.law_type} ═══"
        elif group.group_type == 'uploaded':
            header = f"═══ USER-UPLOADED DOCUMENTS (NON-STATUTORY EVIDENCE) ═══"
        else:
            header = f"═══ {group.group_type.upper()}: {group.law_type} ═══"
        
        return header
    
    def _format_group_content(self, group: ContextGroup) -> str:
        """Format chunks within a group"""
        content_parts = []
        
        for i, chunk in enumerate(group.chunks, 1):
            section = chunk.get('section_number', 'N/A')
            text = chunk.get('text', '')
            source = chunk.get('source', 'Unknown')
            score = chunk.get('score', 0.0)
            
            # Format individual chunk
            chunk_text = f"[{i}. {section}] (Relevance: {score:.2f})\n{text}\n"
            
            # Add source attribution
            if group.group_type == 'uploaded':
                chunk_text += f"(Source: User-uploaded - {source})\n"
            
            content_parts.append(chunk_text)
        
        return "\n".join(content_parts)
    
    def _generate_context_footer(self, groups: Dict[str, ContextGroup]) -> str:
        """Generate metadata footer about context composition"""
        total_chunks = sum(len(g.chunks) for g in groups.values())
        statutory_count = sum(len(g.chunks) for g in groups.values() if g.group_type == 'statutory')
        case_law_count = sum(len(g.chunks) for g in groups.values() if g.group_type == 'case_law')
        uploaded_count = sum(len(g.chunks) for g in groups.values() if g.group_type == 'uploaded')
        
        footer = f"─── Context Summary ───\n"
        footer += f"Total Chunks: {total_chunks} "
        footer += f"(Statutory: {statutory_count}, Case Law: {case_law_count}"
        if uploaded_count > 0:
            footer += f", User Docs: {uploaded_count}"
        footer += ")"
        
        return footer
    
    def build_flat_context(
        self,
        results: List[Any],
        max_chunks: int = 20,
        max_chars: int = 8000
    ) -> str:
        """
        Build traditional flat context (backward compatibility).
        
        Args:
            results: Search results
            max_chunks: Maximum number of chunks
            max_chars: Maximum character count
            
        Returns:
            Formatted context string
        """
        formatted_parts = []
        total_chars = 0
        
        for i, result in enumerate(results[:max_chunks]):
            law_type = getattr(result, 'law_type', 'Law')
            section = getattr(result, 'section_number', 'Section')
            text = getattr(result, 'text', '')
            
            part = f"[{i+1}. {law_type} - {section}]\n{text}"
            
            if total_chars + len(part) > max_chars:
                break
            
            formatted_parts.append(part)
            total_chars += len(part)
        
        return "\n\n".join(formatted_parts) if formatted_parts else "No relevant context found."


if __name__ == "__main__":
    print("=" * 60)
    print("CONTEXT BUILDER TEST")
    print("=" * 60)
    
    # Test with mock results
    from dataclasses import dataclass
    
    @dataclass
    class MockResult:
        law_type: str
        section_number: str
        text: str
        source_dataset: str
        dataset_type: str
        score: float
        metadata: dict
    
    statutory_results = [
        MockResult(
            law_type="IPC",
            section_number="IPC_302",
            text="Section 302: Whoever commits murder shall be punished with death or imprisonment for life...",
            source_dataset="ipc_sections.csv",
            dataset_type="statutory",
            score=0.95,
            metadata={}
        ),
        MockResult(
            law_type="CrPC",
            section_number="CrPC_437",
            text="Section 437: Bail in non-bailable offences. When any person accused of...",
            source_dataset="crpc_sections.csv",
            dataset_type="statutory",
            score=0.88,
            metadata={}
        ),
    ]
    
    builder = ContextBuilder()
    structured = builder.build_structured_context(statutory_results, None, None)
    
    print("\nStructured Context:")
    print(structured)
