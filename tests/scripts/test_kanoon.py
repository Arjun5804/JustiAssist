
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from services.indian_kanoon import get_kanoon_api

async def test_kanoon():
    print("Initializing Indian Kanoon API...")
    try:
        api = get_kanoon_api()
        if not api.api_key:
            print("ERROR: API key not found in environment!")
            return

        query = "bail Section 437 CrPC"
        print(f"Searching for: '{query}'...")
        
        result = await api.search(query)
        
        print(f"\nSearch complete!")
        print(f"Total results: {result.total_results}")
        print(f"Docs found: {len(result.documents)}")
        print("-" * 50)
        
        for i, doc in enumerate(result.documents[:3]):
            print(f"{i+1}. {doc.title}")
            print(f"   Court: {doc.court}")
            print(f"   Date: {doc.date}")
            print(f"   Citation: {doc.citation}")
            print(f"   URL: {doc.url}")
            print("-" * 30)
            
        if result.documents:
            print("\n✅ Indian Kanoon API is WORKING!")
        else:
            print("\n⚠️ API returned no results (key might be invalid or query too specific)")
            
    except Exception as e:
        print(f"\n❌ API Check FAILED: {e}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(test_kanoon())
