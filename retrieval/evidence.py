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
        missing_id_count = 0
        duplicates_removed = 0
        
        for result in results:
            # 3. ID Validation
            if not result.chunk_id:
                missing_id_count += 1
                # Reject items without valid canonical chunk_ids
                continue
                
            # 1. Provenance Validation without mutation
            safe_provenance = result.provenance
            if not safe_provenance:
                missing_provenance_count += 1
                safe_provenance = Provenance() # Use a safe default
                
            # 2. Deduplication Signature
            # Two items are identical if they have the same text AND the same source provenance
            # We explicitly exclude chunk_id from the identity signature so that we catch true duplicates
            # regardless of underlying vector index ID differences.
            provenance_signature = (
                safe_provenance.source_authority.value,
                safe_provenance.source_date,
                safe_provenance.effective_from,
                safe_provenance.effective_until,
            )
            
            identity_signature = (
                result.text.strip(),
                result.source_dataset,
                result.dataset_type,
                result.law_type,
                result.section_number,
                provenance_signature
            )
            
            if identity_signature in seen_signatures:
                duplicates_removed += 1
                continue
                
            seen_signatures.add(identity_signature)
            
            # Create a shallow copy with the validated provenance if it was missing
            # to avoid mutating the original SearchResult object
            validated_result = result
            if not result.provenance:
                from dataclasses import replace
                validated_result = replace(result, provenance=safe_provenance)
                
            deduplicated_results.append(validated_result)
            
        metadata = {
            "original_count": len(results),
            "validated_count": len(deduplicated_results),
            "duplicates_removed": duplicates_removed,
            "missing_provenance_count": missing_provenance_count,
            "missing_id_count": missing_id_count
        }
        return deduplicated_results, metadata
