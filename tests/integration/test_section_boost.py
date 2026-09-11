"""Test IPC section retrieval with section boost fix"""
import sys
sys.path.insert(0, '.')

import pytest
from vector_store import VectorStore

@pytest.mark.integration
def test_section_retrieval():
    print("=" * 60)
    print("IPC SECTION RETRIEVAL TEST")
    print("=" * 60)
    
    vs = VectorStore()
    vs.load()
    
    # Test 1: Section extraction
    print("\n1. Testing section extraction from queries:")
    test_queries = [
        "Explain IPC 297",
        "What is section 297 of IPC",
        "IPC section 298",
        "CrPC 438 bail",
    ]
    
    for query in test_queries:
        section = vs._extract_section_from_query(query)
        print(f"   '{query}' -> {section}")
    
    # Test 2: Hybrid search with boost
    print("\n2. Testing hybrid search for 'Explain IPC 297':")
    results = vs.hybrid_search_statutory('Explain IPC 297', top_k=10)
    
    found_297 = False
    for i, r in enumerate(results):
        marker = ""
        if "297" in r.section_number:
            found_297 = True
            marker = " <-- TARGET"
        boost = r.metadata.get('section_boost', 0)
        print(f"   {i+1}. [{r.score:.3f}] {r.section_number} (boost={boost}){marker}")
    
    if found_297:
        print("\n✅ SUCCESS: IPC 297 found in results!")
    else:
        print("\n❌ FAILURE: IPC 297 not in top 10 results")
    
    # Test 3: Check if IPC_297 exists in metadata at all
    print("\n3. Checking if IPC_297 exists in index:")
    count = sum(1 for m in vs.statutory_metadata if 'IPC_297' in m.get('section_number', ''))
    print(f"   Found {count} chunks with IPC_297 in section_number")

if __name__ == "__main__":
    test_section_retrieval()
