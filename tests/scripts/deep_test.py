
print(f"Checking index.faiss file...")
import os
index_path = r'd:\project folder\justiassist\vector_stores\statutory\index.faiss'
if os.path.exists(index_path):
    print(f"Index file exists, size: {os.path.getsize(index_path)} bytes")
else:
    print("Index file MISSING")

print("\nRunning search test again with exact text...")
from vector_store import VectorStore
import asyncio

async def test():
    vs = VectorStore()
    vs.load()
    
    # Try searching for the exact text of Section 297 to see if semantic search finds it
    query = "trespassing on burial places offering indignity to human corpse section 297"
    print(f"Query: {query}")
    
    results = vs.hybrid_search_statutory(query, top_k=50)
    
    found = False
    for r in results:
        if "297" in r.section_number:
            print(f"FOUND: {r.section_number} (Score: {r.score})")
            print(f"Text: {r.text[:100]}...")
            found = True
            
    if not found:
        print("Still NOT found in search results")

if __name__ == "__main__":
    asyncio.run(test())
