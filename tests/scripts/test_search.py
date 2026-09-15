import sys
import os
import asyncio
# Add project root to path
sys.path.append(os.getcwd())

from vector_store import VectorStore
from reranker import LegalReranker
from agents.query_reformulator import QueryReformulator

async def test():
    print("Initializing VectorStore...")
    vs = VectorStore()
    vs.load()
    
    query = "Explain about IPC section 297"
    print(f"\nSearching for: '{query}'")
    
    # 1. Test Retrieval
    results = vs.hybrid_search_statutory(query, top_k=20)
    print(f"\nRaw Results found: {len(results)}")
    
    found_297 = False
    for r in results:
        print(f" - [{r.score:.3f}] {r.section_number}: {r.text[:50]}...")
        if "297" in r.section_number and "IPC" in r.section_number:
            found_297 = True
            
    if found_297:
        print("\n✅ IPC 297 found in retrieval results.")
    else:
        print("\n❌ IPC 297 NOT found in retrieval results.")

    # 2. Test Reformulator (maybe it's not extracting the section?)
    print("\nTesting Query Reformulator...")
    qr = QueryReformulator()
    from agents.query_reformulator import ReformulatedQuery
    # Mocking the LLM call or just testing text extraction if possible
    # We'll just check what extract_section_references does
    extracted = qr._extract_sections(query)
    print(f"Extracted sections: {extracted}")

    # 3. Test Reranker
    if results and found_297:
        print("\nTesting Reranker...")
        reranker = LegalReranker()
        reranked = reranker.rerank(results, requested_sections=extracted)
        print(f"Reranked results: {len(reranked)}")
        for r in reranked:
             print(f" - [{r.score:.3f}] {r.section_number}\n")

if __name__ == "__main__":
    asyncio.run(test())
