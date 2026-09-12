"""
JustiAssist Evidence Validation Layer
Implements deterministic evidence validation, deduplication, and provenance verification.
"""

from typing import List, Dict, Set, Tuple
from retrieval.models import EvidenceSet, ValidatedEvidenceSet, SearchResult, Provenance, AuthorityLevel

class EvidenceValidator:
    """
    Validates and deduplicates EvidenceSets.
    Ensures that provenance is preserved and contradictory evidence is not discarded.
    """
    
    def validate(self, evidence: EvidenceSet) -> ValidatedEvidenceSet:
        """
        Validates the complete EvidenceSet.
        """
        val_statutory, stat_metadata = self._validate_results(evidence.statutory_results)
        val_case_law, case_metadata = self._validate_results(evidence.case_law_results)
        
        # Session documents are currently List[Dict], we pass them through unchanged for now
        # as they don't use SearchResult yet.
        val_session = evidence.session_documents
        
        validation_metadata = {
            "statutory": stat_metadata,
            "case_law": case_metadata,
        }
        
        return ValidatedEvidenceSet(
            statutory_results=val_statutory,
            case_law_results=val_case_law,
            session_documents=val_session,
            validation_metadata=validation_metadata
        )
        
    def _validate_results(self, results: List[SearchResult]) -> Tuple[List[SearchResult], Dict[str, int]]:
        """
        Validates a list of SearchResults.
        Performs deduplication and provenance checks.
        """
        deduplicated_results = []
        seen_signatures: Set[str] = set()
        
        missing_provenance_count = 0
        duplicates_removed = 0
        
        for result in results:
            # 1. Provenance Validation
            if not result.provenance:
                missing_provenance_count += 1
                result.provenance = Provenance() # Provide a safe default rather than fabricating
                
            # 2. Deduplication Signature
            # Two items are identical if they have the same text AND the same source provenance
            # (including the existing SearchResult source metadata)
            provenance_signature = (
                result.provenance.source_authority.value,
                result.provenance.source_date,
            )
            identity_signature = (
                result.chunk_id,
                result.text.strip(),
                result.source_dataset,
                result.section_number,
                provenance_signature
            )
            
            sig_hash = hash(identity_signature)
            
            if sig_hash in seen_signatures:
                duplicates_removed += 1
                continue
                
            seen_signatures.add(sig_hash)
            deduplicated_results.append(result)
            
        metadata = {
            "original_count": len(results),
            "validated_count": len(deduplicated_results),
            "duplicates_removed": duplicates_removed,
            "missing_provenance_count": missing_provenance_count
        }
        return deduplicated_results, metadata
