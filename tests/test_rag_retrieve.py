import sys
import os
sys.path.append(os.getcwd())

from vector_store import VectorStore
from config import VECTOR_STORE_PATH

print("Initializing Vector Store...")
vs = VectorStore()
vs.load()

query = "Who has the power to grant bail police or court"
print(f"\nQuery: {query}")
print("-" * 50)

# Search statutory index
results = vs.search_statutory(query, top_k=5)

found_relevant = False
for i, res in enumerate(results):
    print(f"\nResult {i+1}:")
    print(f"Source: {res.source_dataset}")
    print(f"Text: {res.text[:300]}...")
    
    # Check for key sections
    text_lower = res.text.lower()
    if '437' in text_lower or '439' in text_lower or '436' in text_lower or '480' in text_lower:
        found_relevant = True

print("-" * 50)
if found_relevant:
    print("SUCCESS: Retrieved relevant bail sections (CrPC 436/437/439 or BNSS 480)")
else:
    print("WARNING: Did not find specific bail sections in top 5 results")
