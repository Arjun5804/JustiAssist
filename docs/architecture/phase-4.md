# Phase 4: Grounded Generation, Claim Verification & Abstention

## Architectural Goal
Establish a deterministic and bounded verification loop for the LLM response generation to ensure that every factual or legal claim in the final answer is verifiably supported by the canonical retrieval evidence.

## Key Principles
1. **Separation of Generation and Verification:** The LLM generator is strictly responsible for producing a JSON structure of claims (`GeneratedResponse`), while an independent verifier performs the deterministic and semantic checks.
2. **Canonical Evidence Preservation:** We rely strictly on the `ValidatedEvidenceSet` produced by Phase 3. The generator outputs `evidence_ids` corresponding to canonical chunk IDs, mitigating hallucinated citations.
3. **Claim-Level Granularity:** Verification happens at the claim level. An answer is deemed supported only if all constituent claims are supported.
4. **Bounded Revision Loops:** Unsupported claims trigger a feedback loop. To prevent infinite agentic stalling, the revision is strictly bounded to a maximum of 2 retries.
5. **Explicit Abstention:** If the verifier rejects claims post-retries, or if the initial evidence is insufficient, the system explicitly abstains rather than silently falling back to unverified legal assumptions.

## Core Models (`generation/models.py`)

```python
class ClaimVerification:
    claim_id: str
    verdict: VerificationVerdict
    evidence_ids: List[str]
    reason: Optional[str]

class GeneratedResponse:
    answer: str
    claims: List[Claim]
    is_abstention: bool
    abstention_reason: Optional[str]

class VerificationVerdict(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    INVALID_REFERENCE = "INVALID_REFERENCE"
```

## Pipeline Flow (`generation/pipeline.py`)

1. **Input:** `ValidatedEvidenceSet`
2. **Generate:** `GroundedGenerator` yields a `GeneratedResponse` containing `answer` and `claims`.
3. **Verify:** `ClaimVerifier` performs deterministic ID verification and semantic verification via an isolated LLM evaluator.
4. **Evaluate:** If any claim is `UNSUPPORTED`, `PARTIALLY_SUPPORTED`, or `INVALID_REFERENCE`:
    - If `retries < max_retries`, feedback is appended and sent back to **Generate**.
    - If `retries == max_retries`, the pipeline abstains.
5. **Accept/Abstain:** Output the final supported answer or an explicit abstention.

## Streaming Invariant
The token streaming happens *after* the entire Grounded Generation pipeline successfully concludes (or the original stage-based SSE architecture is preserved, yielding the final answer upon pipeline completion). Unverified answers are *never* streamed directly to the user.

## Relationship with Phase 3
This pipeline relies entirely on the output from Phase 3 (`ValidatedEvidenceSet`). Retrieval weighting, Reranking logic, FAISS integrations, and context structuring are entirely decoupled from this layer.
