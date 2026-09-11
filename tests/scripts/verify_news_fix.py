import sys
import os
sys.path.append(os.getcwd())

from services.news_scraper import get_news_scraper
from pathlib import Path

# Initialize
scraper = get_news_scraper()
print(f"Scraper initialized. GNews available: {scraper._gnews is not None}")

# Test 1: Generic news (cached or fresh)
print("\n--- Test 1: Generic News ---")
news = scraper.get_news()
if news:
    print(f"Title: {news[0]['title']}")
    print(f"Source: {news[0]['source']}")
    if news[0]['source'] == 'Unknown':
        print("FAIL: Source is Unknown")
    else:
        print("PASS: Source is present")
else:
    print("No news returned")

# Test 2: Specific query
print("\n--- Test 2: Specific Query ('Bail') ---")
query_news = scraper.get_news("Bail India")
if query_news:
    print(f"Fetched {len(query_news)} articles for 'Bail India'")
    print(f"Title: {query_news[0]['title']}")
    print(f"Source: {query_news[0]['source']}")
    # Check relevance roughly
    relevant = any('bail' in n['title'].lower() for n in query_news)
    print(f"Relevance Check: {'PASS' if relevant else 'FAIL'}")
else:
    print("No query news returned")
