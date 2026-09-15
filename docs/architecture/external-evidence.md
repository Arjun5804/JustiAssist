# External Evidence Architecture

## Problem Statement
Relying strictly on local FAISS indexes often misses the latest judgments or newly introduced laws (e.g., BNS). However, naive web searching introduces catastrophic risks of hallucinations and authoritative collapse.

## The JustiAssist Solution
External evidence is strictly governed before it reaches the generative pipeline.

### Governance Rules
1. **Strict Triggers**: We only search externally when local confidence fails, domains mismatch, or specific triggers (Bail, New Laws) fire.
2. **Authority Determinism**: An LLM is never allowed to determine if a URL is "official". This is handled by a hardcoded, exact-match Python layer (`AuthorityClassifier`).
3. **No Fallback News**: If our legal news API fails, we use placeholder fallback news for the UI. These placeholders are explicitly blocked from entering the generative evidence context via `is_fallback`.
4. **Conflict Resolution**: The `ClaimVerifier` sees all available evidence. If an external source explicitly contradicts a local statutory provision, the LLM verifier will flag it as `CONFLICTING`. Unresolved conflicts result in safe abstention.
5. **No Hallucinated Citations**: External evidence chunks get IDs like `ext_web_1234abcd`. The LLM must cite these IDs exactly. We never trust LLM-generated URLs or court names.
